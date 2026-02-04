# PHASE B — AML Customer Risk Scoring & Enriched Queue

## Codename: `party-aml-score`

## Objective

Assign every party (customer/entity) a composite **AML Risk Score** derived from
pipeline results, transaction enrichment data (`extra_info.csv`), and network
behaviour.  Persist scores as a first-class artifact so downstream systems
(case management, regulatory reporting) can consume them.

---

## Data Sources

| File | Rows | Key Columns |
|------|------|-------------|
| `party.csv` | 855,382 | `partyId, partyType` |
| `transactions.csv` | 9,504,852 | `tran_id, tx_type, base_amt, src, dst` |
| `extra_info.csv` | 9,504,852 | `Is_laundering, Laundering_type, Payment_currency, Received_currency, Sender_bank_location, Receiver_bank_location` |
| `alert_transactions.csv` | ~3,300 | `alert_id, alert_type, is_sar, tran_id` |
| Phase A `risk_queue.parquet` | 855,382 | `entity_id, is_sar, degree, risk_score, tier` |

---

## AML Score Formula

Each party gets a composite score from **5 signal groups**, weighted and summed:

```
aml_score = (
    W_SAR   * sar_signal          # SAR label from alerts
  + W_LAUN  * laundering_signal   # links to Is_laundering=1 txns
  + W_NET   * network_signal      # degree, fan-in/fan-out ratio
  + W_GEO   * geo_signal          # cross-border / multi-currency
  + W_VOL   * volume_signal       # transaction volume anomalies
)
```

### Signal Definitions

| Signal | Formula | Range | Default Weight |
|--------|---------|-------|----------------|
| **sar_signal** | `1.0 if is_sar else 0.0` | 0–1 | W_SAR = 3.0 |
| **laundering_signal** | `min(1.0, laundering_txn_count / 5)` — fraction of party's txns flagged `Is_laundering=1`, capped | 0–1 | W_LAUN = 2.5 |
| **network_signal** | `0.5 * log1p(degree) / log1p(max_degree) + 0.5 * fanout_ratio` | 0–1 | W_NET = 1.5 |
| **geo_signal** | `0.6 * (cross_border_rate) + 0.4 * (unique_jurisdictions / max_jurisdictions)` | 0–1 | W_GEO = 1.0 |
| **volume_signal** | `min(1.0, total_amt / p99_amt)` — ratio to 99th-percentile volume | 0–1 | W_VOL = 0.5 |

Final AML score normalized to **0–100** scale:

```
aml_score_100 = (raw_score / max_possible_score) * 100
```

### Risk Bands

| Band | AML Score Range | Label |
|------|----------------|-------|
| Critical | 80–100 | Immediate escalation |
| High | 60–79 | Priority review |
| Medium | 30–59 | Standard monitoring |
| Low | 0–29 | Periodic review |

---

## Implementation Plan

### Step 1 — Enrichment Loader (`app/pipeline_runner/enrichment.py`)

New module to load and aggregate `extra_info.csv` per party.

```
def load_enrichment(data_dir: Path) -> pd.DataFrame
```

Produces a per-party dataframe with columns:

| Column | Description |
|--------|-------------|
| `party_id` | Entity identifier |
| `txn_count` | Total transactions (as sender + receiver) |
| `total_amt` | Sum of `base_amt` across all txns |
| `laundering_txn_count` | Count of txns where `Is_laundering=1` |
| `laundering_types` | Set of distinct `Laundering_type` values |
| `cross_border_count` | Txns where sender_location != receiver_location |
| `cross_currency_count` | Txns where payment_currency != received_currency |
| `unique_jurisdictions` | Distinct bank locations (sender + receiver side) |
| `unique_currencies` | Distinct currencies involved |

Logic:
- Join `transactions.csv` (src/dst) with `extra_info.csv` (on tran_id)
- Group by party_id (union of src and dst roles)
- Aggregate counts and sums
- Handle memory: process in chunks if > 5M rows

### Step 2 — AML Score Calculator (`app/pipeline_runner/aml_scoring.py`)

New module that takes Phase A queue + enrichment and produces final scores.

```
def compute_aml_scores(
    risk_queue_path: Path,
    enrichment_df: pd.DataFrame,
    edges_path: Path,
    weights: dict = None,
) -> pd.DataFrame
```

Steps:
1. Load Phase A `risk_queue.parquet` (has: entity_id, is_sar, degree, risk_score)
2. Merge with enrichment_df on entity_id = party_id
3. Compute each of the 5 signals
4. Apply weights, sum, normalize to 0–100
5. Assign risk band (Critical/High/Medium/Low)
6. Build reasons list (e.g. `["SAR_LABEL", "LAUNDERING_LINK:Structuring", "CROSS_BORDER:3_jurisdictions"]`)

Output columns:
```
party_id, party_type, is_sar, degree, txn_count, total_amt,
laundering_txn_count, cross_border_count, cross_currency_count,
sar_signal, laundering_signal, network_signal, geo_signal, volume_signal,
aml_score, risk_band, reasons
```

Output files:
- `queues/party_aml_scores.parquet` — full scored table
- `queues/party_aml_scores.csv` — CSV fallback
- `queues/aml_score_summary.json` — aggregate stats

Summary JSON structure:
```json
{
  "total_parties": 855382,
  "score_range": {"min": 0.0, "max": 95.2, "mean": 12.4, "median": 8.1},
  "band_counts": {"Critical": 45, "High": 312, "Medium": 8500, "Low": 846525},
  "sar_count": 32,
  "laundering_linked_count": 5200,
  "cross_border_count": 120000,
  "weights_used": {"W_SAR": 3.0, "W_LAUN": 2.5, "W_NET": 1.5, "W_GEO": 1.0, "W_VOL": 0.5},
  "signals_available": ["sar", "laundering", "network", "geo", "volume"]
}
```

### Step 3 — Orchestrator Hook

In `orchestrator.py`, after the Phase A `build_risk_queue()` call:

```python
# Build AML party scores (Phase B)
try:
    from .enrichment import load_enrichment
    from .aml_scoring import compute_aml_scores

    enrichment_df = load_enrichment(self.artifacts_dir / "data")
    scores_df = compute_aml_scores(
        risk_queue_path=self.artifacts_dir / "queues" / "risk_queue.parquet",
        enrichment_df=enrichment_df,
        edges_path=self.artifacts_dir / "data" / "edges_td.csv",
    )
    # Save
    scores_df.to_parquet(self.queues_dir / "party_aml_scores.parquet", index=False)
    scores_df.to_csv(self.queues_dir / "party_aml_scores.csv", index=False)
    # Save summary
    aml_summary = _build_aml_summary(scores_df)
    (self.queues_dir / "aml_score_summary.json").write_text(json.dumps(aml_summary, indent=2))
    self.results["aml_scores"] = aml_summary
    logger.info(f"AML scores computed for {len(scores_df):,} parties")

    # Rebuild artifact index
    self._build_artifact_index()
except Exception as e:
    logger.warning(f"Failed to compute AML scores: {e}")
```

### Step 4 — API Endpoints (`app/api/routes/runs.py`)

Two new endpoints:

#### `GET /runs/{run_id}/aml-summary`
Returns `aml_score_summary.json` contents.

#### `GET /runs/{run_id}/aml-scores`
Returns paginated, filtered party scores.

Query params:
- `limit`, `offset` — pagination
- `band: List[str]` — filter by risk band (repeated params: `?band=Critical&band=High`)
- `min_score: float` — minimum AML score
- `max_score: float` — maximum AML score
- `is_sar: int` — 0 or 1
- `has_laundering: int` — 0 or 1 (parties with laundering_txn_count > 0)
- `search: str` — substring match on party_id
- `sort_by: str` — column to sort (default: `aml_score`)
- `sort_order: str` — `asc` or `desc` (default: `desc`)

Response:
```json
{
  "total": 312,
  "limit": 100,
  "offset": 0,
  "rows": [
    {
      "party_id": "abc123",
      "party_type": "Individual",
      "aml_score": 87.3,
      "risk_band": "Critical",
      "is_sar": 1,
      "laundering_txn_count": 4,
      "cross_border_count": 12,
      "degree": 45,
      "total_amt": 1250000.0,
      "reasons": "SAR_LABEL, LAUNDERING_LINK:Structuring, CROSS_BORDER:3_jurisdictions"
    }
  ]
}
```

### Step 5 — Streamlit Tab: "AML Scores"

New tab (8th) in `streamlit_app.py`: **"🏦 AML Scores"**

Layout:

```
┌─────────────────────────────────────────────────────┐
│  Run Selector                                       │
├─────────────────────────────────────────────────────┤
│  [Band Filter] [Score Slider] [SAR] [Laundering]    │
│  [Search box]                                       │
├──────────┬──────────┬──────────┬────────────────────┤
│ Total    │ Critical │ High     │ Avg Score          │
│ Parties  │ Count    │ Count    │                    │
├──────────┴──────────┴──────────┴────────────────────┤
│  Band Distribution Bar (color-coded proportional)   │
├─────────────────────────────────────────────────────┤
│  Sortable Dataframe                                 │
│  party_id | type | aml_score | band | is_sar | ...  │
├─────────────────────────────────────────────────────┤
│  [Download CSV]                                     │
├─────────────────────────────────────────────────────┤
│  Score Distribution Histogram (by band)             │
├─────────────────────────────────────────────────────┤
│  Signal Radar Chart (top 10 Critical parties)       │
│  — shows relative strength of each signal           │
├─────────────────────────────────────────────────────┤
│  Geo Heatmap (jurisdiction breakdown)               │
└─────────────────────────────────────────────────────┘
```

Components:
- **Band filter**: multiselect (Critical, High, Medium, Low)
- **Score range slider**: 0–100
- **SAR radio**: All / SAR Only / Non-SAR
- **Laundering radio**: All / Laundering-linked / Clean
- **KPI cards**: total parties, critical count, high count, avg score
- **Band distribution bar**: color-coded (Critical=red, High=orange, Medium=blue, Low=gray)
- **Dataframe**: sortable, formatted, paginated
- **Download**: filtered CSV export
- **Score histogram**: plotly histogram colored by band
- **Radar chart**: plotly scatterpolar showing 5 signal strengths for top critical entities
- **Geo heatmap**: bar chart of jurisdiction counts for filtered entities

### Step 6 — Notebook 1 Update (sample_size handling)

Update notebook 1 (`1_create_feature_groups.ipynb`) to also carry `extra_info.csv`
columns through to the artifact output, so they're available at scoring time.

Add after the transaction sampling cell:
- Join sampled transactions with `extra_info.csv` on `tran_id`
- Save enriched edges as `data/edges_enriched_td.csv` (adds: Is_laundering,
  Laundering_type, cross-border flags)

This way `aml_scoring.py` can read from the already-sampled enriched edges
instead of needing the full 767MB `extra_info.csv` at scoring time.

### Step 7 — Artifact Index Update

Add to `artifacts_index.py` FILE_CATEGORIES detection:
- `party_aml_scores.parquet` → `queues`
- `aml_score_summary.json` → `queues`
- `edges_enriched_td.csv` → `data`

(Already covered by existing `queues` category glob, but add explicit mention
in description.)

---

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `app/pipeline_runner/enrichment.py` | CREATE | Load & aggregate extra_info.csv per party |
| `app/pipeline_runner/aml_scoring.py` | CREATE | Compute 5-signal AML score per party |
| `app/pipeline_runner/orchestrator.py` | MODIFY | Hook scoring after Phase A queue build |
| `app/pipeline_runner/__init__.py` | MODIFY | Export new functions |
| `app/api/routes/runs.py` | MODIFY | Add aml-summary + aml-scores endpoints |
| `app/ui/streamlit_app.py` | MODIFY | Add "AML Scores" tab (8th tab) |
| `1_create_feature_groups.ipynb` | MODIFY | Carry extra_info columns through pipeline |
| `app/pipeline_runner/artifacts_index.py` | MODIFY | Update descriptions |

---

## Dependencies

- No new pip packages required (uses pandas, numpy, json, math — all existing)
- Requires Phase A `risk_queue.parquet` to exist (run pipeline first)
- `extra_info.csv` is optional — if missing, laundering/geo signals default to 0

---

## Estimated Data Flow

```
party.csv (855K parties)
    │
    ▼
transactions.csv (9.5M txns)  ──► sample(N) ──► edges_td.csv
    │                                               │
extra_info.csv (9.5M rows)    ──► join on tran_id ──┤
    │                                               │
    ▼                                               ▼
enrichment.py                              risk_ranking.py (Phase A)
  per-party aggregates                       risk_queue.parquet
    │                                               │
    └──────────────┬────────────────────────────────┘
                   ▼
            aml_scoring.py
              5-signal composite
                   │
                   ▼
        party_aml_scores.parquet
        aml_score_summary.json
                   │
                   ▼
            API + Streamlit
```
