# PHASE A — Risk Ranking & Tiered Queues: Implementation Report

## Codename: `risk-tier-queue`

## Status: COMPLETE

Branch: `v3-enhance` | Base: `release/v2.0.0-aml-dashboard`

---

## Objective

Assign every entity in a pipeline run a **risk score**, rank them, bucket into
**tiered investigation queues** (T1–T4), and expose through API + Streamlit UI
with full filtering, pagination, and CSV export.

---

## What Was Built

### 1. Risk Ranking Engine — `app/pipeline_runner/risk_ranking.py` (NEW)

Core function: `build_risk_queue(run_dir, tier_thresholds=None) -> dict`

**Risk Score Formula:**
```
risk_score = 2.0 * is_sar + 0.5 * log1p(degree)
```

**Percentile Formula (Option B):**
```
percentile = ((rank - 1) / total) * 100
```
- Rank 1 (highest risk) → percentile 0.0%
- Last rank → percentile ~100%

**Tier Assignment (no gaps, no overlaps):**

| Tier | Percentile Range | Purpose |
|------|-----------------|---------|
| T1 | 0.0% – 0.5% | Immediate investigation |
| T2 | 0.5% – 2.0% | Priority review |
| T3 | 2.0% – 5.0% | Enhanced monitoring |
| T4 | > 5.0% | Standard monitoring |

**Features:**
- Auto-detects edge column names (`source/target`, `src/dst`, `from/to`)
- Computes undirected degree from `edges_td.csv` (optional)
- Merges full node universe from `node_td.csv` (so no entity types are excluded)
- Builds human-readable `reasons` column (e.g. `SAR_LABEL`, `HIGH_DEGREE:45`)
- Outputs Parquet (primary) with CSV fallback

**Output files:**
- `queues/risk_queue.parquet` — full ranked queue
- `queues/queue_summary.json` — aggregate statistics

**Queue columns:**
```
entity_id, entity_type, is_sar, degree, risk_score, rank, percentile, tier, reasons
```

### 2. Orchestrator Integration — `app/pipeline_runner/orchestrator.py` (MODIFIED)

- Added `self.queues_dir = self.artifacts_dir / "queues"` to run directory setup
- `queues/` directory created alongside `data/`, `models/`, `plots/`, etc.
- `build_risk_queue()` called after `_build_artifact_index()` completes
- Artifact index is **rebuilt** after queue creation so queue files are indexed
- Wrapped in try/except — queue failure does not break the pipeline
- Queue summary stored in `self.results["risk_queue"]`

### 3. Package Exports — `app/pipeline_runner/__init__.py` (MODIFIED)

- `build_risk_queue` added to public imports and `__all__`

### 4. Artifact Indexer — `app/pipeline_runner/artifacts_index.py` (MODIFIED)

- Added `queues` category to `FILE_CATEGORIES`:
  - Extensions: `.parquet`, `.csv`, `.json`
  - Subdirectory: `queues/`
- Added path-based detection: any file with `queues` in its path → `queues` category

### 5. API Endpoints — `app/api/routes/runs.py` (MODIFIED)

#### `GET /runs/{run_id}/risk-summary`
Returns `queue_summary.json` — tier counts, score range, SAR count, etc.

#### `GET /runs/{run_id}/risk-queue`
Returns paginated, server-side filtered queue rows.

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Page size (default 100) |
| `offset` | int | Skip rows (default 0) |
| `max_percentile` | float | Capacity filter — top X% (applied FIRST) |
| `tier` | List[str] | Tier filter, repeated params: `?tier=T1&tier=T2` |
| `entity_type` | List[str] | Entity type filter, repeated params |
| `is_sar` | int | 0 or 1 |
| `search` | str | Substring match on entity_id |

**Filter order (capacity-first):**
1. `max_percentile` — capacity cut
2. `tier` — tier selection
3. `entity_type` — type filter
4. `is_sar` — SAR filter
5. `search` — text search

**Response:**
```json
{
  "total": 4277,
  "limit": 100,
  "offset": 0,
  "rows": [
    {
      "entity_id": "a1b2c3d4",
      "entity_type": "1",
      "is_sar": 1,
      "degree": 45,
      "risk_score": 2.8959,
      "rank": 1,
      "percentile": 0.0,
      "tier": "T1",
      "reasons": "SAR_LABEL, HIGH_DEGREE:45"
    }
  ]
}
```

### 6. Streamlit Tab — `app/ui/streamlit_app.py` (MODIFIED)

Added **7th tab**: "⚡ Tier Queue"

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Run Selector (completed runs only)                 │
├──────────┬──────────┬──────────┬─────────┬──────────┤
│ Tier     │ Top X%   │ Entity   │ SAR     │ Search   │
│ Multisel │ Slider   │ Types    │ Radio   │ Input    │
├──────────┼──────────┼──────────┼─────────┴──────────┤
│ Total    │ Filtered │ SAR      │ Top Type           │
│ Entities │ Results  │ Labelled │ (filtered)         │
├──────────┴──────────┴──────────┴────────────────────┤
│  T1 (red)  │  T2 (amber)  │  T3 (blue)  │  T4 (gray) │
│  count/%   │  count/%     │  count/%    │  count/%    │
├─────────────────────────────────────────────────────┤
│  Sortable Dataframe (500 row limit)                 │
│  rank | tier | entity_id | type | SAR | score | ... │
├─────────────────────────────────────────────────────┤
│  [Download Filtered Queue (CSV)]                    │
├─────────────────────────────────────────────────────┤
│  Risk Score Distribution Histogram (by tier color)  │
└─────────────────────────────────────────────────────┘
```

**Features:**
- 5 filter controls in a single row
- 4 KPI metric cards
- Color-coded tier breakdown bar with counts and percentages
- Column-configured dataframe with formatted numbers
- CSV download of filtered results
- Risk score distribution histogram (overlaid by tier, Plotly)

---

## Test Results — SAML-D Run

Tested against: `6b455e7e-a633-4f07-9e4e-dee4df01af9d`

**Dataset:**
- Source: SAML-D / Elliptic++ demodata
- Raw transactions: 9,504,852
- Sample size used: 20,000 (standard profile)
- Sampled transactions: 19,886
- Total entities: 855,382

**Queue Output:**

| Metric | Value |
|--------|-------|
| Total entities | 855,382 |
| T1 (≤ 0.5%) | 4,277 |
| T2 (≤ 2.0%) | 12,831 |
| T3 (≤ 5.0%) | 25,662 |
| T4 (> 5.0%) | 812,612 |
| SAR-labelled | 32 |
| Has degree data | Yes |
| Score min | 0.0 |
| Score max | 2.896 |
| Score mean | 0.015 |
| Output file size | 17 MB (Parquet) |

**Observations:**
- All 32 SAR-labelled entities ranked in T1 (highest tier)
- 31,600 entities have non-zero degree (from sampled edges)
- 823,782 entities have degree=0 and is_sar=0 (score=0.0, ranked in T4)
- Entity type is uniformly "1" (Individual) — this dataset has no Organization entities
- The `sample_size=20000` samples transactions not nodes, so most nodes lose edges

**Syntax checks:** All 6 modified files pass `py_compile`

---

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/pipeline_runner/risk_ranking.py` | CREATED | ~220 |
| `app/pipeline_runner/orchestrator.py` | MODIFIED | +20 |
| `app/pipeline_runner/__init__.py` | MODIFIED | +2 |
| `app/pipeline_runner/artifacts_index.py` | MODIFIED | +10 |
| `app/api/routes/runs.py` | MODIFIED | +80 |
| `app/ui/streamlit_app.py` | MODIFIED | +200 |

---

## Architecture

```
Pipeline Run
    │
    ├── data/
    │   ├── alert_nodes_td.csv   ◄── entities + is_sar flag
    │   ├── node_td.csv          ◄── full node universe (merged in)
    │   └── edges_td.csv         ◄── transactions → degree calculation
    │
    ▼
risk_ranking.py::build_risk_queue()
    │
    ├── Load alert_nodes + merge node_td
    ├── Compute degree from edges
    ├── Score: 2.0 * is_sar + 0.5 * log1p(degree)
    ├── Rank (descending score)
    ├── Percentile: ((rank-1) / total) * 100
    ├── Tier: T1/T2/T3/T4 by percentile thresholds
    └── Save → queues/risk_queue.parquet + queue_summary.json
    │
    ▼
orchestrator.py (post-pipeline hook)
    │
    ▼
API Layer                          Streamlit UI
  /risk-summary  ──────────────►  KPI cards + tier bar
  /risk-queue?filters  ────────►  Filtered dataframe + histogram
                                  CSV download
```

---


