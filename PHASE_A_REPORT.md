# PHASE A + A.1 — Risk Ranking & Tiered Queues: Implementation Report

## Branch: `v3-enhance` | Base: `release/v2.0.0-aml-dashboard`

---

## PHASE A — Risk Ranking & Tiered Queues

### Codename: `risk-tier-queue` | Status: COMPLETE

### Objective

Assign every entity in a pipeline run a **risk score**, rank them, bucket into
**tiered investigation queues** (T1–T4), and expose through API + Streamlit UI
with full filtering, pagination, and CSV export.

---

### What Was Built

#### 1. Risk Ranking Engine — `app/pipeline_runner/risk_ranking.py` (NEW)

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
- Builds human-readable `reasons` column (e.g. `SAR_LABEL`, `HIGH_CONNECTIVITY(deg=45)`)
- Outputs Parquet (primary) with CSV fallback

**Output files:**
- `queues/risk_queue.parquet` — full ranked queue
- `queues/queue_summary.json` — aggregate statistics + audit metadata

**Queue columns:**
```
entity_id, entity_type, is_sar, degree, risk_score, rank, percentile, tier, reasons
```

#### 2. Orchestrator Integration — `app/pipeline_runner/orchestrator.py` (MODIFIED)

- Added `self.queues_dir = self.artifacts_dir / "queues"` to run directory setup
- `queues/` directory created alongside `data/`, `models/`, `plots/`, etc.
- `build_risk_queue()` called after `_build_artifact_index()` completes
- Artifact index is **rebuilt** after queue creation so queue files are indexed
- Wrapped in try/except — queue failure does not break the pipeline
- Queue summary stored in `self.results["risk_queue"]`

#### 3. Package Exports — `app/pipeline_runner/__init__.py` (MODIFIED)

- `build_risk_queue` added to public imports and `__all__`

#### 4. Artifact Indexer — `app/pipeline_runner/artifacts_index.py` (MODIFIED)

- Added `queues` category to `FILE_CATEGORIES`:
  - Extensions: `.parquet`, `.csv`, `.json`
  - Subdirectory: `queues/`
- Added path-based detection: any file with `queues` in its path → `queues` category

#### 5. API Endpoints — `app/api/routes/runs.py` (MODIFIED)

##### `GET /runs/{run_id}/risk-summary`
Returns `queue_summary.json` — tier counts, score range, SAR count, audit metadata, etc.

##### `GET /runs/{run_id}/risk-queue`
Returns paginated, server-side filtered queue rows.

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Page size (default 200) |
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
      "reasons": "SAR_LABEL;HIGH_CONNECTIVITY(deg=45)"
    }
  ]
}
```

#### 6. Streamlit Tab — `app/ui/streamlit_app.py` (MODIFIED)

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
- CSV download of filtered results (includes reasons column)
- Risk score distribution histogram (overlaid by tier, Plotly)

---

## PHASE A.1 — Hardening: Audit, Operating Point & Reasons Visibility

### Codename: `risk-tier-hardening` | Status: COMPLETE

### Objective

Harden the Phase A implementation with audit traceability, persisted operating
points, reasons-based filtering, and a label-sparsity early warning — all
**backward-compatible** with existing artifacts and endpoints.

---

### What Was Added

#### A) Audit Metadata in `queue_summary.json`

**File:** `app/pipeline_runner/risk_ranking.py`

Added the following **additive fields** to the summary (existing fields unchanged):

| New Field | Type | Description |
|-----------|------|-------------|
| `run_id` | string | Run directory name (UUID) |
| `generated_at` | string | UTC ISO-8601 timestamp of queue generation |
| `risk_score_formula` | string | Human-readable formula: `"2.0*is_sar + 0.5*log1p(degree)"` |
| `data_sources_used` | object | Which data files were available: `alert_nodes_td`, `edges_td`, `node_td` (each `true`/`false`) |
| `tier_thresholds_percentile` | object | Explicit copy of tier boundaries: `{"T1": 0.5, "T2": 2.0, "T3": 5.0}` |
| `sar_label_stats` | object | SAR count, rate %, and `label_sparse` boolean |

**Label-sparse definition** (configurable constants at module top):
```python
LABEL_SPARSE_MIN_COUNT = 50        # fewer than 50 SAR labels
LABEL_SPARSE_MIN_RATE_PCT = 0.05   # OR rate below 0.05%
```
`label_sparse = True` if **either** threshold is breached.

**Example output** (from SAML-D test run):
```json
{
  "total_entities": 855382,
  "tier_thresholds": {"T1": 0.5, "T2": 2.0, "T3": 5.0},
  "tier_counts": {"T4": 812612, "T3": 25662, "T2": 12831, "T1": 4277},
  "top_types_per_tier": {"T1": {"1": 4277}, "T2": {"1": 12831}, ...},
  "sar_count": 32,
  "has_degree": true,
  "score_range": {"min": 0.0, "max": 2.896, "mean": 0.015},
  "run_id": "6b455e7e-a633-4f07-9e4e-dee4df01af9d",
  "generated_at": "2026-02-04T09:36:19.658624+00:00",
  "risk_score_formula": "2.0*is_sar + 0.5*log1p(degree)",
  "data_sources_used": {"alert_nodes_td": true, "edges_td": true, "node_td": true},
  "tier_thresholds_percentile": {"T1": 0.5, "T2": 2.0, "T3": 5.0},
  "sar_label_stats": {"sar_count": 32, "sar_rate_pct": 0.0037, "label_sparse": true}
}
```

---

#### B) Operating Point Persistence

**File:** `app/api/routes/runs.py`

New artifact: `queues/operating_point.json` — saves the analyst's current
filter configuration so it can be reloaded across sessions.

##### `POST /runs/{run_id}/operating-point`

**Request body** (Pydantic-validated):
```json
{
  "top_percent": 2.0,
  "tiers": ["T1", "T2"],
  "entity_types": [],
  "sar_filter": "All",
  "search": ""
}
```

**Validation rules:**
- `top_percent`: must be > 0 and ≤ 100
- `tiers`: must be non-empty; each value must be one of `T1, T2, T3, T4`
- `sar_filter`: must be one of `All`, `SAR Only`, `Non-SAR`

**Persisted format** (`queues/operating_point.json`):
```json
{
  "run_id": "6b455e7e-...",
  "saved_at": "2026-02-04T10:15:00.000000+00:00",
  "payload": {
    "top_percent": 2.0,
    "tiers": ["T1", "T2"],
    "entity_types": [],
    "sar_filter": "All",
    "search": ""
  }
}
```

##### `GET /runs/{run_id}/operating-point`

Returns the saved operating point JSON, or **404** if none exists.

**Artifact indexing:** Automatically categorized under `queues` by the existing
path-based detection in `artifacts_index.py` — no changes needed.

---

#### C) Streamlit UI Enhancements

**File:** `app/ui/streamlit_app.py` — Tier Queue tab

Three additions to the existing tab:

##### 1. Label Sparse Warning

Shown at the top of the tab when `sar_label_stats.label_sparse` is `true`:

```
⚠ Labels are sparse: Only 32 SAR-labelled entities (0.004% of total).
  Risk ranking relies primarily on network connectivity (degree).
  Consider enriching labels or using a larger sample size for more
  robust scoring.
```

##### 2. Reasons Filter

New `st.multiselect` control below the existing filter row:

```
Filter by Reasons: [ SAR_LABEL ] [ HIGH_CONNECTIVITY ]
```

- Client-side filter: rows are included if their `reasons` string contains
  **any** of the selected reason tags
- When no reasons are selected, all rows pass through (no filter)
- CSV download includes the full `reasons` column

##### 3. Operating Point Panel

Added between the download button and the score distribution chart:

```
┌─────────────────────────────────────────────────────┐
│  Operating Point                                    │
│                                                     │
│  Saved: 2026-02-04T10:15Z | Top 2.0% |             │
│  Tiers: T1, T2 | SAR: All     [Save Operating Point]│
│                                                     │
│  — or —                                             │
│  No operating point saved for this run yet.         │
└─────────────────────────────────────────────────────┘
```

- **Load:** On tab render, fetches `GET /runs/{run_id}/operating-point` and
  displays the saved configuration if it exists
- **Save:** Button sends `POST /runs/{run_id}/operating-point` with the
  current filter state (top %, tiers, entity types, SAR filter, search)
- Shows `st.success` toast on save, `st.error` on failure

**Updated tab layout:**
```
┌─────────────────────────────────────────────────────┐
│  Run Selector                                       │
├─────────────────────────────────────────────────────┤
│  ⚠ Labels are sparse... (if label_sparse=true)     │
├──────────┬──────────┬──────────┬─────────┬──────────┤
│ Tier     │ Top X%   │ Entity   │ SAR     │ Search   │
│ Multisel │ Slider   │ Types    │ Radio   │ Input    │
├─────────────────────────────────────────────────────┤
│ Filter by Reasons: [SAR_LABEL] [HIGH_CONNECTIVITY]  │
├──────────┬──────────┬──────────┬────────────────────┤
│ Total    │ Filtered │ SAR      │ Top Type           │
├──────────┴──────────┴──────────┴────────────────────┤
│  T1 | T2 | T3 | T4  (tier breakdown bar)           │
├─────────────────────────────────────────────────────┤
│  Sortable Dataframe (with reasons column)           │
├─────────────────────────────────────────────────────┤
│  [Download Filtered Queue (CSV)]                    │
├─────────────────────────────────────────────────────┤
│  Operating Point: [saved info]  [Save button]       │
├─────────────────────────────────────────────────────┤
│  Risk Score Distribution Histogram                  │
└─────────────────────────────────────────────────────┘
```

---

### Backward Compatibility

| Concern | Status |
|---------|--------|
| Existing `queue_summary.json` fields | Unchanged — new fields are additive |
| `risk_queue.parquet` schema | Unchanged — no new columns |
| `GET /risk-summary` response | Superset — old consumers see same keys |
| `GET /risk-queue` response | Unchanged — same structure and filters |
| Streamlit tab layout | Extended — no existing controls removed |
| `operating_point.json` | New file — does not overwrite any existing artifact |
| No breaking API changes | All new endpoints are additive (`POST` + `GET` operating-point) |

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
| SAR rate | 0.0037% |
| Label sparse | **true** |
| Has degree data | Yes |
| Score min | 0.0 |
| Score max | 2.896 |
| Score mean | 0.015 |
| Output file size | 17 MB (Parquet) |

**Audit fields verified:**
- `run_id`: `6b455e7e-a633-4f07-9e4e-dee4df01af9d`
- `generated_at`: `2026-02-04T09:36:19.658624+00:00`
- `risk_score_formula`: `2.0*is_sar + 0.5*log1p(degree)`
- `data_sources_used`: all three files present (`true`)
- `label_sparse`: `true` (32 < 50 count threshold, 0.0037% < 0.05% rate threshold)

**Observations:**
- All 32 SAR-labelled entities ranked in T1 (highest tier)
- 31,600 entities have non-zero degree (from sampled edges)
- 823,782 entities have degree=0 and is_sar=0 (score=0.0, ranked in T4)
- Entity type uniformly "1" (Individual) — dataset has no Organization entities
- `sample_size=20000` samples transactions not nodes, so most nodes lose edges

**Syntax checks:** All modified files pass `py_compile`

---

## Files Changed (Cumulative: Phase A + A.1)

| File | Action | Lines | Phase |
|------|--------|-------|-------|
| `app/pipeline_runner/risk_ranking.py` | CREATED | ~297 | A + A.1 |
| `app/pipeline_runner/orchestrator.py` | MODIFIED | +20 | A |
| `app/pipeline_runner/__init__.py` | MODIFIED | +2 | A |
| `app/pipeline_runner/artifacts_index.py` | MODIFIED | +10 | A |
| `app/api/routes/runs.py` | MODIFIED | +175 | A + A.1 |
| `app/ui/streamlit_app.py` | MODIFIED | +250 | A + A.1 |

---

## Output Artifacts (per run)

```
<artifacts_dir>/queues/
├── risk_queue.parquet          # Full ranked queue (Phase A)
├── queue_summary.json          # Summary stats + audit metadata (A + A.1)
└── operating_point.json        # Saved filter configuration (A.1, created on save)
```

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
    ├── Reasons: SAR_LABEL, HIGH_CONNECTIVITY(deg=N)
    ├── Audit: run_id, timestamp, formula, data sources, label stats
    └── Save → queues/risk_queue.parquet
             + queues/queue_summary.json
    │
    ▼
orchestrator.py (post-pipeline hook)
    │
    ▼
API Layer                              Streamlit UI
  GET  /risk-summary  ─────────────►  KPI cards + tier bar
  GET  /risk-queue?filters  ────────►  Filtered dataframe + histogram
  POST /operating-point  ◄─────────   [Save Operating Point] button
  GET  /operating-point  ──────────►  Saved config display
                                       Reasons filter multiselect
                                       Label sparse warning
                                       CSV download (with reasons)
```

---

## Next Phases

| Phase | Codename | Description | Status |
|-------|----------|-------------|--------|
| A | `risk-tier-queue` | Risk ranking + tiered queues | COMPLETE |
| A.1 | `risk-tier-hardening` | Audit, operating point, reasons, label warning | COMPLETE |
| B | `party-aml-score` | Composite AML score per party using extra_info.csv enrichment | PLANNED |

See [PHASE_B_PLAN.md](PHASE_B_PLAN.md) for Phase B details.
