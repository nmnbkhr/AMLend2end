# PHASE B — Audit Report

## Codename: `party-aml-score`

Audit Date: 2026-02-04

---

## 1. Scope

Full code-level audit of Phase B implementation against the specification
in `PHASE_B_PLAN.md`.  Includes dry-run validation on the pre-computed
demo artifacts (`artifacts/runs/4b36a26a-...`).

### Files Audited

| File | Type | Lines |
|------|------|-------|
| `app/pipeline_runner/enrichment.py` | NEW | 245 |
| `app/pipeline_runner/aml_scoring.py` | NEW | 377 |
| `app/pipeline_runner/__init__.py` | MODIFIED | 25 |
| `app/pipeline_runner/orchestrator.py` | MODIFIED | removed scoring block |
| `app/api/routes/runs.py` | MODIFIED | +145 lines (3 endpoints) |
| `app/ui/streamlit_app.py` | MODIFIED | +300 lines (AML Scores tab) |

---

## 2. Architecture Deviation from Plan

The plan called for scoring to run **inside** the main pipeline
orchestrator (Step 3).  During implementation, the scoring was
**extracted** into a standalone pipeline that runs independently:

| Aspect | Plan | Implementation |
|--------|------|----------------|
| Trigger | Automatic in orchestrator | On-demand via API / UI button |
| Entry point | Orchestrator post-processing | `run_aml_scoring(artifacts_dir)` |
| API | GET only | GET + POST `/aml-scores/compute` |
| UI | Passive display | Compute + Recompute buttons |

**Rationale**: User requested separation so AML scoring does not couple
to the main pipeline execution.  Scores can be computed, tuned, and
recomputed independently after any completed run.

---

## 3. Bugs Found and Fixed

### 3.1 CRITICAL — Score Denominator Penalizes Missing Signals

**Location**: `aml_scoring.py:172`

**Problem**: The composite score divided the raw weighted sum by
`max_possible = W_SAR + W_LAUN + W_NET + W_GEO + W_VOL = 8.5`.  When
enrichment data is absent (no `extra_info.csv`), laundering, geo, and
volume signals are all zero -- not because the entities are clean, but
because there is no data.  The denominator still included all 5 weights.

**Impact**: Maximum achievable score was `(3.0 + 1.5) / 8.5 * 100 =
52.9`.  No entity could ever reach High (60+) or Critical (80+) band
when enrichment was missing.  All 79 SAR entities in the demo run were
capped at Medium (max 49.19).

**Fix**: Normalize against only the sum of weights for signals that
actually have data:

```python
has_laundering_data = scored["laundering_signal"].sum() > 0
has_geo_data = scored["geo_signal"].sum() > 0
has_volume_data = scored["volume_signal"].sum() > 0

active_weight = w["W_SAR"] + w["W_NET"]
if has_laundering_data:
    active_weight += w["W_LAUN"]
# ... etc.

scored["aml_score"] = ((raw_score / active_weight) * 100).round(2)
```

**Result after fix**: Critical: 47, High: 32, max score: 92.91

### 3.2 MINOR — SettingWithCopyWarning in Streamlit Tab

**Location**: `streamlit_app.py:3248`

**Problem**: `df_display = df[display_cols]` creates a view, then
`.round()` modifies it in place, triggering a pandas
`SettingWithCopyWarning`.

**Fix**: Added `.copy()` when creating the display DataFrame.

### 3.3 CLEANUP — Unused Function Parameter

**Location**: `aml_scoring.py:339`

**Problem**: `_compute_fanout_ratio(edges_path, entity_ids)` accepted an
`entity_ids` parameter that was never used inside the function.
Filtering was done at the call site via `.map()`.

**Fix**: Removed the unused parameter and updated the call site.

### 3.4 CLEANUP — Unused Import

**Location**: `enrichment.py:17`

**Problem**: `import numpy as np` was never referenced in the module.

**Fix**: Removed the import.

---

## 4. Dry-Run Validation

Scoring was executed against the demo run artifacts to verify
end-to-end correctness.

### 4.1 Input Data

| Artifact | Path | Records |
|----------|------|---------|
| Risk queue | `queues/risk_queue.parquet` | 7,347 entities |
| Edges | `data/edges_td.csv` | 20,084 transactions |
| Enrichment | (none -- no `extra_info.csv`) | 0 rows |

### 4.2 Risk Queue Schema

```
entity_id     object    (e.g. "c9b585a4")
entity_type   object    (0 or 1)
is_sar        int64     (0 or 1)
degree        int64     (0-22)
risk_score    float64   (Phase A score)
reasons       object
rank          int64
percentile    float64
tier          object    (T1-T4)
```

### 4.3 Edges Schema

```
source    object    (entity ID)
target    object    (entity ID)
tran_id   int64
tx_type   int64     (0-4)
base_amt  float64
```

Column detection: `source` matched via `_SRC_CANDIDATES`, `target` via
`_DST_CANDIDATES`.

### 4.4 Results (After Bug Fix)

```
Total scored:       7,347 parties
Score range:        0.00 - 92.91
Active signals:     sar, network (2 of 5)
Active weight:      4.5 (W_SAR=3.0 + W_NET=1.5)

Band Distribution:
  Critical:  47  (0.6%)
  High:      32  (0.4%)
  Medium:     0  (0.0%)
  Low:     7,268 (98.9%)
```

### 4.5 Top 5 Entities

| Entity ID | SAR | Degree | AML Score | Band | Reasons |
|-----------|-----|--------|-----------|------|---------|
| 65752867 | 1 | 10 | 92.91 | Critical | SAR_LABEL, HIGH_CONNECTIVITY(deg=10) |
| 9d04cf26 | 1 | 9 | 92.28 | Critical | SAR_LABEL, HIGH_CONNECTIVITY(deg=9) |
| bb2d35ed | 1 | 5 | 91.73 | Critical | SAR_LABEL, HIGH_CONNECTIVITY(deg=5) |
| 56e9fc25 | 1 | 11 | 90.44 | Critical | SAR_LABEL, HIGH_CONNECTIVITY(deg=11) |
| 75178e11 | 1 | 9 | 90.42 | Critical | SAR_LABEL, HIGH_CONNECTIVITY(deg=9) |

### 4.6 JSON Serialization

Summary JSON serializes cleanly.  No NaN or Infinity values present in
the output.

---

## 5. Module-by-Module Review

### 5.1 enrichment.py

| Check | Status | Notes |
|-------|--------|-------|
| File search priority | OK | `edges_enriched_td.csv` > `extra_info.csv` > demodata fallback |
| Case-insensitive column matching | OK | `_find_col()` normalizes to lowercase |
| Missing file graceful fallback | OK | Returns empty DataFrame with correct columns |
| Edge join via tran_id | OK | Falls back to row-index alignment if no key column |
| Per-party aggregation | OK | Explodes src+dst, groups by party_id |
| Cross-border detection | OK | sender_bank_location != receiver_bank_location |
| Cross-currency detection | OK | payment_currency != received_currency |
| Unused import removed | FIXED | `numpy` was unused |

### 5.2 aml_scoring.py

| Check | Status | Notes |
|-------|--------|-------|
| Risk queue loading | OK | Tries .parquet then .csv |
| Column normalization | OK | Strips whitespace, lowercases |
| Entity ID detection | OK | Tries `entity_id` then falls back to `id` |
| Missing column defaults | OK | `is_sar=0`, `degree=0`, `entity_type="unknown"` |
| Enrichment merge | OK | Left join on entity_id=party_id, handles empty enrichment |
| NaN fill for enrichment cols | OK | Missing columns created as 0, existing NaN filled |
| Fan-out ratio computation | OK | out_degree / (in_degree + out_degree) from edges |
| SAR signal | OK | Binary clip to [0,1] |
| Laundering signal | OK | Fraction capped at 1.0, handles zero txn_count |
| Network signal | OK | 0.5 * log-normalized degree + 0.5 * fanout |
| Geo signal | OK | 0.6 * cross-border rate + 0.4 * jurisdiction diversity |
| Volume signal | OK | Ratio to p99, capped at 1.0 |
| Composite score denominator | FIXED | Now normalizes against active signals only |
| Risk band assignment | OK | Boundaries correct, no gaps |
| Reasons generation | OK | Human-readable, includes degree and jurisdiction counts |
| Output column selection | OK | Filters to only existing columns |
| Standalone runner | OK | `run_aml_scoring()` handles full lifecycle |
| Artifact index rebuild | OK | Called after scoring, wrapped in try/except |
| Unused parameter removed | FIXED | `entity_ids` in `_compute_fanout_ratio` |

### 5.3 orchestrator.py

| Check | Status | Notes |
|-------|--------|-------|
| AML scoring block removed | OK | Clean removal, no residual references |
| Cases block intact | OK | Lines 770-781 unchanged |
| Report generation intact | OK | Follows immediately after cases |
| Pipeline flow unchanged | OK | Start -> notebooks -> risk_queue -> cases -> report |

### 5.4 API Endpoints (runs.py)

| Check | Status | Notes |
|-------|--------|-------|
| GET /aml-summary | OK | Reads `aml_score_summary.json`, 404 if missing |
| GET /aml-scores (pagination) | OK | limit/offset, default limit=200 |
| GET /aml-scores (band filter) | OK | `Optional[List[str]]` for repeated params |
| GET /aml-scores (score range) | OK | min_score / max_score float filters |
| GET /aml-scores (SAR filter) | OK | is_sar = 0 or 1 |
| GET /aml-scores (laundering) | OK | has_laundering=1 filters laundering_txn_count > 0 |
| GET /aml-scores (search) | OK | Case-insensitive substring on entity_id |
| GET /aml-scores (sort) | OK | sort_by (any column) + sort_order (asc/desc) |
| POST /aml-scores/compute | OK | Validates risk queue exists, returns summary |
| Error handling | OK | 404 for missing run/data, 400 for missing prereq, 500 for failure |
| Import pattern | OK | Consistent with existing endpoints |

### 5.5 Streamlit Tab

| Check | Status | Notes |
|-------|--------|-------|
| Run selector | OK | Same pattern as Tier Queue tab |
| Compute button (no scores) | OK | Shows when summary 404, triggers POST, reruns on success |
| Recompute button | OK | Available next to KPI cards |
| Band filter multiselect | OK | Shows counts in labels |
| Score range slider | OK | 0-100, step 1.0 |
| SAR radio | OK | All / SAR Only / Non-SAR |
| Laundering radio | OK | All / Has Laundering |
| Search text input | OK | Substring match |
| Sort controls | OK | Sort by any signal + asc/desc |
| KPI cards | OK | Total, Filtered, Mean, Critical+High, Median |
| Band breakdown boxes | OK | Color-coded, percentage shown |
| Data table | OK | Column configs with proper formatting |
| CSV download | OK | Filtered data, run-prefixed filename |
| Score histogram | OK | Colored by risk band |
| Radar chart | OK | Top 5 entities, 5 signal axes, closed polygon |
| Summary key alignment | OK | `total_scored`, `mean_score`, `median_score`, `band_distribution` |
| Copy warning | FIXED | `.copy()` added for df_display |
| width parameter | OK | `width="stretch"` replacing deprecated `use_container_width=True` |

### 5.6 __init__.py

| Check | Status | Notes |
|-------|--------|-------|
| Imports | OK | `load_enrichment`, `compute_aml_scores`, `build_aml_summary`, `run_aml_scoring` |
| `__all__` list | OK | All 4 new symbols included |

---

## 6. Plan vs Implementation Checklist

| Plan Step | Status | Deviation |
|-----------|--------|-----------|
| Step 1 — enrichment.py | DONE | None |
| Step 2 — aml_scoring.py | DONE | Added `run_aml_scoring()` standalone runner |
| Step 3 — Orchestrator hook | CHANGED | Removed from orchestrator; standalone pipeline instead |
| Step 4 — API endpoints | DONE | Added POST compute endpoint beyond plan |
| Step 5 — Streamlit tab | DONE | Added Compute/Recompute buttons; tab is 9th (not 8th) |
| Step 6 — Notebook 1 update | SKIPPED | No `extra_info.csv` in demodata; enrichment module handles graceful fallback |
| Step 7 — Artifact index | AUTO | Existing `queues` category glob auto-detects new files |

---

## 7. Output Files

When AML scoring is executed, it produces:

```
queues/
  party_aml_scores.parquet    # Full scored table (7,347 rows x 17 cols)
  party_aml_scores.csv        # CSV fallback
  aml_score_summary.json      # Aggregate statistics
```

**Directory placement note**: AML score files currently live in `queues/`
alongside the Phase A risk queue.  Semantically these are different
artifacts (risk ranking queue vs composite scores).  A future refactor
could move scores to a dedicated `scores/` directory for clearer
separation.  The current placement works because the artifact indexer
auto-detects files under `queues/`, and both the API and UI reference
`queues/` paths.  Changing this later is low-effort (update 3 path
references in `aml_scoring.py`, `runs.py`, and `run_aml_scoring`).

### Summary JSON Structure (actual output)

```json
{
  "total_scored": 7347,
  "mean_score": 1.46,
  "median_score": 0.0,
  "min_score": 0.0,
  "max_score": 92.91,
  "band_distribution": {
    "Low": 7268,
    "Critical": 47,
    "High": 32,
    "Medium": 0
  },
  "sar_count": 79,
  "laundering_linked_count": 0,
  "cross_border_count": 0,
  "weights_used": {
    "W_SAR": 3.0,
    "W_LAUN": 2.5,
    "W_NET": 1.5,
    "W_GEO": 1.0,
    "W_VOL": 0.5
  },
  "signals_available": ["sar", "network"],
  "generated_at": "2026-02-04T..."
}
```

Note: `laundering_linked_count` and `cross_border_count` are 0 because
no enrichment data (`extra_info.csv`) exists in the demo dataset.  When
enrichment data is provided, all 5 signals become active and the full
score range is utilized.

---

## 8. Signal Behavior Without Enrichment

When `extra_info.csv` is absent, the system operates in degraded mode
with 2 of 5 signals:

| Signal | Active | Weight | Behavior |
|--------|--------|--------|----------|
| SAR | Yes | 3.0 | Binary from `is_sar` label |
| Network | Yes | 1.5 | Log-degree + fan-out from edges |
| Laundering | No | -- | Excluded from denominator |
| Geo | No | -- | Excluded from denominator |
| Volume | No | -- | Excluded from denominator |

Active weight denominator: 4.5 (not 8.5)

Score formula effectively becomes:

```
aml_score = ((3.0 * sar_signal + 1.5 * network_signal) / 4.5) * 100
```

- SAR entity with high connectivity: ~93 (Critical)
- SAR entity with low connectivity: ~70 (High)
- Non-SAR entity with high connectivity: ~22 (Low)
- Non-SAR entity with no connections: 0 (Low)

---

## 9. Post-Audit Improvements (Applied)

Three improvements applied after initial audit findings:

### 9.1 Degraded Mode Warning Banner

The Streamlit AML Scores tab now displays a warning when not all 5
signals are active:

> **Degraded scoring mode:** 2/5 signals active (sar, network).
> Missing signals (geo, laundering, volume) require enrichment data
> (`extra_info.csv`). Band distribution may show empty bands.

This prevents analysts from misinterpreting empty Medium/High bands as
"no entities at that risk level" when data is simply unavailable.

### 9.2 Per-Entity Signal Contribution Breakdown

Added an interactive entity inspector below the data table:

- Entity selector (top 50 from current filter/sort)
- Horizontal bar chart showing each signal's strength (0-1) with
  color coding (SAR=red, Laundering=amber, Network=purple, Geo=blue,
  Volume=green)
- Side panel with entity metadata: AML score, band, SAR status,
  degree, and itemized reasons

This satisfies the explainability requirement — analysts can see
**why** an entity received its score, not just the final number.

### 9.3 Directory Placement Note

Documented in Section 7 that `queues/` is the current storage location
for scores.  A future `scores/` directory would provide cleaner semantic
separation (3 path changes needed).

---

## 10. Recommendations

1. **Provide enrichment data**: Adding `extra_info.csv` to demodata
   would activate all 5 signals and demonstrate the full scoring range
   including Medium band entities.

2. **Weight tuning UI**: Consider adding signal weight sliders to the
   Streamlit tab so analysts can adjust weights and recompute in
   real-time.

3. **Score history**: Track score changes across runs to show trending
   (entity X moved from Medium to Critical).

4. **Batch export**: Add endpoint for full unfiltered CSV/parquet
   download for integration with external case management systems.

5. **Directory separation**: Move score artifacts from `queues/` to
   `scores/` for clearer semantic separation from Phase A risk queue.

---

## 11. Business Alignment (RBA / FATF)

| Capability | Status | Relevance |
| ---------- | ------ | --------- |
| Risk-based prioritization | Done | Composite score + bands create a defendable investigation queue |
| Explainability | Done | Per-entity signal breakdown + reasons list |
| Governance | Done | Summary JSON logs weights used, active signals, and timestamp |
| Degraded mode transparency | Done | Explicit signal availability warning in UI |
| Audit trail | Done | Scores persisted as versioned run artifacts |

---

## 12. Conclusion

Phase B implementation is **functional and verified**.  The critical
scoring denominator bug was found and fixed during audit.  The system
correctly handles the degraded mode (no enrichment data) and produces
meaningful risk differentiation using available signals.  Post-audit
improvements add degraded mode warnings and per-entity explainability.
All API endpoints, Streamlit UI components, and data flow paths have been
validated against the demo run artifacts.
