"""
Risk Ranking & Tiered Queue Builder

Produces a ranked risk queue per pipeline run from alert_nodes and
optional edge data.  Outputs are written to <artifacts_dir>/queues/.

Risk score v1:
    risk_score = 2.0 * is_sar + 0.5 * log1p(degree)

Tier defaults (by percentile):
    T1: top 0.5%   (percentile ≤ 0.5)
    T2: 0.5–2%     (0.5 < percentile ≤ 2.0)
    T3: 2–5%       (2.0 < percentile ≤ 5.0)
    T4: rest
"""

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Column-name candidates for source/target in edge files
_SRC_DST_PAIRS: List[Tuple[str, str]] = [
    ("source", "target"),
    ("src", "dst"),
    ("from", "to"),
]

DEFAULT_TIER_THRESHOLDS = {
    "T1": 0.5,
    "T2": 2.0,
    "T3": 5.0,
}

RISK_SCORE_FORMULA = "2.0*is_sar + 0.5*log1p(degree)"

# Label-sparse thresholds (configurable)
LABEL_SPARSE_MIN_COUNT = 50
LABEL_SPARSE_MIN_RATE_PCT = 0.05


def _detect_edge_columns(columns: List[str]) -> Optional[Tuple[str, str]]:
    """Return (src_col, dst_col) if a known pair is found, else None."""
    cols_lower = {c.lower(): c for c in columns}
    for src_key, dst_key in _SRC_DST_PAIRS:
        if src_key in cols_lower and dst_key in cols_lower:
            return cols_lower[src_key], cols_lower[dst_key]
    return None


def _compute_degree(edges_path: Path) -> pd.Series:
    """
    Compute undirected degree per node from an edge file.

    Returns a Series indexed by node id with integer degree values.
    """
    edges_df = pd.read_csv(edges_path)
    pair = _detect_edge_columns(edges_df.columns.tolist())
    if pair is None:
        logger.warning(
            f"Could not detect source/target columns in {edges_path.name}. "
            f"Columns found: {edges_df.columns.tolist()}"
        )
        return pd.Series(dtype=int)

    src_col, dst_col = pair
    logger.info(f"Using edge columns: {src_col}, {dst_col}")

    # Count undirected: each node's degree = appearances as source + as target
    src_counts = edges_df[src_col].value_counts()
    dst_counts = edges_df[dst_col].value_counts()
    degree = src_counts.add(dst_counts, fill_value=0).astype(int)
    degree.name = "degree"
    return degree


def _assign_tier(percentile: float, thresholds: Dict[str, float]) -> str:
    """Assign tier label based on percentile (lower = higher risk)."""
    if percentile <= thresholds.get("T1", 0.5):
        return "T1"
    if percentile <= thresholds.get("T2", 2.0):
        return "T2"
    if percentile <= thresholds.get("T3", 5.0):
        return "T3"
    return "T4"


def build_risk_queue(
    run_dir: Path,
    tier_thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Build a ranked risk queue for a completed pipeline run.

    Args:
        run_dir: Root artifact directory for the run
                 (e.g. artifacts/runs/<run_id>)
        tier_thresholds: Optional override for tier percentile boundaries.
                         Keys: T1, T2, T3.  Values: upper percentile bound.

    Returns:
        Summary dict (also persisted as queue_summary.json).
    """
    thresholds = dict(DEFAULT_TIER_THRESHOLDS)
    if tier_thresholds:
        thresholds.update(tier_thresholds)

    data_dir = run_dir / "data"
    queues_dir = run_dir / "queues"
    queues_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load alert nodes (REQUIRED) ──
    alert_path = data_dir / "alert_nodes_td.csv"
    if not alert_path.exists():
        raise FileNotFoundError(f"Required file missing: {alert_path}")

    alert_df = pd.read_csv(alert_path)
    logger.info(f"Loaded {len(alert_df):,} alert nodes from {alert_path.name}")

    # Normalise column names
    alert_df.columns = [c.strip().lower() for c in alert_df.columns]
    if "id" not in alert_df.columns:
        raise ValueError(f"alert_nodes_td.csv must contain 'id' column. Found: {list(alert_df.columns)}")

    # Ensure is_sar exists (default 0 if absent)
    if "is_sar" not in alert_df.columns:
        alert_df["is_sar"] = 0

    # Ensure type exists
    if "type" not in alert_df.columns:
        alert_df["type"] = "unknown"

    # ── 1b. Merge full node universe from node_td.csv (OPTIONAL) ──
    # alert_nodes_td.csv may only contain a subset of entity types.
    # node_td.csv has the full set — merge so all types appear in the queue.
    node_path = data_dir / "node_td.csv"
    if node_path.exists():
        try:
            node_df = pd.read_csv(node_path)
            node_df.columns = [c.strip().lower() for c in node_df.columns]
            if "id" in node_df.columns:
                # Find nodes in node_td that are NOT in alert_nodes
                alert_ids = set(alert_df["id"].astype(str))
                node_df["id"] = node_df["id"].astype(str)
                missing = node_df[~node_df["id"].isin(alert_ids)].copy()
                if len(missing) > 0:
                    if "type" not in missing.columns:
                        missing["type"] = "unknown"
                    missing["is_sar"] = 0
                    # Keep only the columns we need
                    missing = missing[["id", "type", "is_sar"]]
                    alert_df = pd.concat([alert_df, missing], ignore_index=True)
                    logger.info(
                        f"Merged {len(missing):,} additional nodes from node_td.csv "
                        f"(total: {len(alert_df):,})"
                    )
        except Exception as e:
            logger.warning(f"Failed to merge node_td.csv: {e}")

    # ── 2. Compute degree from edges (OPTIONAL) ──
    edges_path = data_dir / "edges_td.csv"
    if edges_path.exists():
        try:
            degree_series = _compute_degree(edges_path)
            logger.info(f"Computed degree for {len(degree_series):,} nodes from edges")
        except Exception as e:
            logger.warning(f"Failed to compute degree from edges: {e}")
            degree_series = pd.Series(dtype=int)
    else:
        logger.info("No edges_td.csv found — degree will be 0 for all nodes")
        degree_series = pd.Series(dtype=int)

    # ── 3. Build queue dataframe ──
    queue = pd.DataFrame({
        "entity_id": alert_df["id"].astype(str),
        "entity_type": alert_df["type"].astype(str),
        "is_sar": alert_df["is_sar"].astype(int),
    })

    # Merge degree
    if not degree_series.empty:
        queue["degree"] = queue["entity_id"].map(degree_series).fillna(0).astype(int)
    else:
        queue["degree"] = 0

    # ── 4. Compute risk score ──
    queue["risk_score"] = (
        2.0 * queue["is_sar"]
        + 0.5 * queue["degree"].apply(lambda d: math.log1p(d))
    )

    # ── 5. Build reasons ──
    def _build_reasons(row) -> str:
        reasons = []
        if row["is_sar"] == 1:
            reasons.append("SAR_LABEL")
        if row["degree"] > 0:
            reasons.append(f"HIGH_CONNECTIVITY(deg={row['degree']})")
        return ";".join(reasons) if reasons else ""

    queue["reasons"] = queue.apply(_build_reasons, axis=1)

    # ── 6. Rank and percentile ──
    queue = queue.sort_values("risk_score", ascending=False).reset_index(drop=True)
    total = len(queue)
    queue["rank"] = range(1, total + 1)
    # Option B: rank 1 → percentile 0.0 (cleanest at the very top)
    queue["percentile"] = ((queue["rank"] - 1) / total) * 100

    # ── 7. Assign tiers (no gaps: ≤ boundaries, strict ordering) ──
    queue["tier"] = queue["percentile"].apply(lambda p: _assign_tier(p, thresholds))

    # ── 8. Save queue ──
    queue_path_parquet = queues_dir / "risk_queue.parquet"
    queue_path_csv = queues_dir / "risk_queue.csv"
    try:
        queue.to_parquet(queue_path_parquet, index=False)
        logger.info(f"Saved risk queue to {queue_path_parquet}")
    except Exception as e:
        logger.warning(f"Parquet save failed ({e}), falling back to CSV")
        queue.to_csv(queue_path_csv, index=False)
        logger.info(f"Saved risk queue to {queue_path_csv}")

    # ── 9. Build summary ──
    tier_counts = queue["tier"].value_counts().to_dict()
    # Ensure all tiers present
    for t in ("T1", "T2", "T3", "T4"):
        tier_counts.setdefault(t, 0)

    # Top entity types per tier
    top_types_per_tier = {}
    for tier in ("T1", "T2", "T3", "T4"):
        tier_slice = queue[queue["tier"] == tier]
        if not tier_slice.empty:
            top_types_per_tier[tier] = (
                tier_slice["entity_type"]
                .value_counts()
                .head(5)
                .to_dict()
            )
        else:
            top_types_per_tier[tier] = {}

    sar_count = int(queue["is_sar"].sum())
    sar_rate_pct = (sar_count / total * 100) if total > 0 else 0.0
    has_degree = bool(not degree_series.empty)
    has_node_td = node_path.exists()

    summary = {
        # ── Existing fields (unchanged) ──
        "total_entities": total,
        "tier_thresholds": thresholds,
        "tier_counts": tier_counts,
        "top_types_per_tier": top_types_per_tier,
        "sar_count": sar_count,
        "has_degree": has_degree,
        "score_range": {
            "min": float(queue["risk_score"].min()),
            "max": float(queue["risk_score"].max()),
            "mean": float(queue["risk_score"].mean()),
        },
        # ── Audit metadata (Phase A.1) ──
        "run_id": run_dir.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "risk_score_formula": RISK_SCORE_FORMULA,
        "data_sources_used": {
            "alert_nodes_td": True,
            "edges_td": has_degree,
            "node_td": has_node_td,
        },
        "tier_thresholds_percentile": {
            "T1": thresholds.get("T1", 0.5),
            "T2": thresholds.get("T2", 2.0),
            "T3": thresholds.get("T3", 5.0),
        },
        "sar_label_stats": {
            "sar_count": sar_count,
            "sar_rate_pct": round(sar_rate_pct, 4),
            "label_sparse": (
                sar_count < LABEL_SPARSE_MIN_COUNT
                or sar_rate_pct < LABEL_SPARSE_MIN_RATE_PCT
            ),
        },
    }

    summary_path = queues_dir / "queue_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Saved queue summary to {summary_path}")

    return summary
