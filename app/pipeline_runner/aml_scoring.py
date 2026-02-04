"""
AML Score Calculator — Phase B

Assigns every party a composite AML Risk Score (0–100) derived from
5 signal groups:

    1. SAR signal       — is this entity SAR-labelled?
    2. Laundering signal — linked to Is_laundering=1 transactions
    3. Network signal    — degree centrality + fan-out ratio
    4. Geo signal        — cross-border / multi-jurisdiction activity
    5. Volume signal     — transaction volume relative to population

Each signal is normalised to [0, 1] then weighted and summed.  The raw
sum is rescaled to 0–100 and assigned a risk band.
"""

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default signal weights
DEFAULT_WEIGHTS: Dict[str, float] = {
    "W_SAR": 3.0,
    "W_LAUN": 2.5,
    "W_NET": 1.5,
    "W_GEO": 1.0,
    "W_VOL": 0.5,
}

# Risk band boundaries (on the 0-100 scale)
RISK_BANDS = [
    (80, 100, "Critical"),
    (60, 80, "High"),
    (30, 60, "Medium"),
    (0, 30, "Low"),
]


def _assign_band(score: float) -> str:
    for lo, hi, label in RISK_BANDS:
        if lo <= score <= hi:
            return label
    return "Low"


def compute_aml_scores(
    risk_queue_path: Path,
    enrichment_df: pd.DataFrame,
    edges_path: Path,
    weights: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Compute composite AML scores for all parties.

    Args:
        risk_queue_path: Path to Phase A ``risk_queue.parquet`` (or .csv).
        enrichment_df: Per-party enrichment from ``enrichment.load_enrichment()``.
                       May be empty — laundering/geo signals default to 0.
        edges_path: Path to ``edges_td.csv`` (for fan-out ratio computation).
        weights: Override signal weights.  Keys: W_SAR, W_LAUN, W_NET, W_GEO, W_VOL.

    Returns:
        DataFrame with one row per party and columns::

            party_id, entity_type, is_sar, degree, txn_count, total_amt,
            laundering_txn_count, cross_border_count, cross_currency_count,
            sar_signal, laundering_signal, network_signal, geo_signal,
            volume_signal, aml_score, risk_band, reasons
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    # ── 1. Load Phase A risk queue ──
    if risk_queue_path.with_suffix(".parquet").exists():
        queue = pd.read_parquet(risk_queue_path.with_suffix(".parquet"))
    elif risk_queue_path.with_suffix(".csv").exists():
        queue = pd.read_csv(risk_queue_path.with_suffix(".csv"))
    else:
        raise FileNotFoundError(f"Risk queue not found at {risk_queue_path}")

    queue.columns = [c.strip().lower() for c in queue.columns]
    logger.info(f"Loaded risk queue: {len(queue):,} entities")

    # Normalise id column
    id_col = "entity_id" if "entity_id" in queue.columns else "id"
    if id_col != "entity_id":
        queue = queue.rename(columns={id_col: "entity_id"})
    queue["entity_id"] = queue["entity_id"].astype(str)

    # Ensure required columns
    if "is_sar" not in queue.columns:
        queue["is_sar"] = 0
    if "degree" not in queue.columns:
        queue["degree"] = 0
    if "entity_type" not in queue.columns:
        queue["entity_type"] = "unknown"

    # ── 2. Merge enrichment ──
    if not enrichment_df.empty and "party_id" in enrichment_df.columns:
        enrichment_df["party_id"] = enrichment_df["party_id"].astype(str)
        scored = queue.merge(enrichment_df, left_on="entity_id", right_on="party_id", how="left")
        scored = scored.drop(columns=["party_id"], errors="ignore")
    else:
        scored = queue.copy()

    # Fill NaN enrichment columns with 0
    enrich_cols = [
        "txn_count", "total_amt", "laundering_txn_count",
        "cross_border_count", "cross_currency_count",
        "unique_jurisdictions", "unique_currencies",
    ]
    for col in enrich_cols:
        if col not in scored.columns:
            scored[col] = 0
        else:
            scored[col] = scored[col].fillna(0)

    if "laundering_types" not in scored.columns:
        scored["laundering_types"] = ""
    else:
        scored["laundering_types"] = scored["laundering_types"].fillna("")

    # ── 3. Compute fan-out ratio from edges ──
    fanout_ratio = _compute_fanout_ratio(edges_path)
    scored["fanout_ratio"] = scored["entity_id"].map(fanout_ratio).fillna(0.0)

    # ── 4. Compute signals ──

    # SAR signal: binary
    scored["sar_signal"] = scored["is_sar"].astype(float).clip(0, 1)

    # Laundering signal: fraction of party txns flagged, capped at 1.0
    scored["laundering_signal"] = np.where(
        scored["txn_count"] > 0,
        (scored["laundering_txn_count"] / scored["txn_count"].clip(lower=1)).clip(0, 1),
        np.where(scored["laundering_txn_count"] > 0, 1.0, 0.0),
    )

    # Network signal: 0.5 * normalised_degree + 0.5 * fanout_ratio
    max_degree = max(scored["degree"].max(), 1)
    scored["network_signal"] = (
        0.5 * scored["degree"].apply(lambda d: math.log1p(d)) / math.log1p(max_degree)
        + 0.5 * scored["fanout_ratio"]
    ).clip(0, 1)

    # Geo signal: 0.6 * cross_border_rate + 0.4 * jurisdiction_diversity
    scored["_cb_rate"] = np.where(
        scored["txn_count"] > 0,
        scored["cross_border_count"] / scored["txn_count"].clip(lower=1),
        0.0,
    )
    max_jurisdictions = max(scored["unique_jurisdictions"].max(), 1)
    scored["geo_signal"] = (
        0.6 * scored["_cb_rate"]
        + 0.4 * (scored["unique_jurisdictions"] / max_jurisdictions)
    ).clip(0, 1)

    # Volume signal: ratio to 99th-percentile volume, capped at 1.0
    p99_amt = scored["total_amt"].quantile(0.99) if scored["total_amt"].max() > 0 else 1.0
    p99_amt = max(p99_amt, 1.0)  # avoid division by zero
    scored["volume_signal"] = (scored["total_amt"] / p99_amt).clip(0, 1)

    # ── 5. Composite score ──
    # Normalise against only the weights of signals that have data.
    # When enrichment is empty, laundering/geo/volume are 0 because
    # data is absent, not because entities are clean.  Using all 5
    # weights would cap scores at ~53 and make High/Critical unreachable.
    has_laundering_data = scored["laundering_signal"].sum() > 0
    has_geo_data = scored["geo_signal"].sum() > 0
    has_volume_data = scored["volume_signal"].sum() > 0

    active_weight = w["W_SAR"] + w["W_NET"]
    if has_laundering_data:
        active_weight += w["W_LAUN"]
    if has_geo_data:
        active_weight += w["W_GEO"]
    if has_volume_data:
        active_weight += w["W_VOL"]

    scored["_raw_score"] = (
        w["W_SAR"] * scored["sar_signal"]
        + (w["W_LAUN"] * scored["laundering_signal"] if has_laundering_data else 0)
        + w["W_NET"] * scored["network_signal"]
        + (w["W_GEO"] * scored["geo_signal"] if has_geo_data else 0)
        + (w["W_VOL"] * scored["volume_signal"] if has_volume_data else 0)
    )
    scored["aml_score"] = ((scored["_raw_score"] / active_weight) * 100).round(2)

    # ── 6. Risk band ──
    scored["risk_band"] = scored["aml_score"].apply(_assign_band)

    # ── 7. Reasons ──
    scored["reasons"] = scored.apply(_build_reasons, axis=1)

    # ── 8. Clean up and return ──
    output_cols = [
        "entity_id", "entity_type", "is_sar", "degree",
        "txn_count", "total_amt", "laundering_txn_count",
        "cross_border_count", "cross_currency_count",
        "sar_signal", "laundering_signal", "network_signal",
        "geo_signal", "volume_signal",
        "aml_score", "risk_band", "reasons",
    ]
    # Keep only columns that exist
    output_cols = [c for c in output_cols if c in scored.columns]
    result = scored[output_cols].sort_values("aml_score", ascending=False).reset_index(drop=True)

    logger.info(
        f"AML scores computed: {len(result):,} parties, "
        f"bands: {result['risk_band'].value_counts().to_dict()}"
    )
    return result


def build_aml_summary(scores_df: pd.DataFrame, weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Build the summary JSON for AML scores."""
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    band_counts = scores_df["risk_band"].value_counts().to_dict()
    for band in ["Critical", "High", "Medium", "Low"]:
        band_counts.setdefault(band, 0)

    sar_count = int(scores_df["is_sar"].sum()) if "is_sar" in scores_df.columns else 0
    laun_linked = int((scores_df["laundering_txn_count"] > 0).sum()) if "laundering_txn_count" in scores_df.columns else 0
    cb_count = int((scores_df["cross_border_count"] > 0).sum()) if "cross_border_count" in scores_df.columns else 0

    return {
        "total_scored": len(scores_df),
        "mean_score": round(float(scores_df["aml_score"].mean()), 2),
        "median_score": round(float(scores_df["aml_score"].median()), 2),
        "min_score": round(float(scores_df["aml_score"].min()), 2),
        "max_score": round(float(scores_df["aml_score"].max()), 2),
        "band_distribution": band_counts,
        "sar_count": sar_count,
        "laundering_linked_count": laun_linked,
        "cross_border_count": cb_count,
        "weights_used": w,
        "signals_available": _detect_available_signals(scores_df),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _detect_available_signals(df: pd.DataFrame) -> list:
    """Detect which signals have non-zero variance (i.e. are informative)."""
    signals = []
    for col, name in [
        ("sar_signal", "sar"),
        ("laundering_signal", "laundering"),
        ("network_signal", "network"),
        ("geo_signal", "geo"),
        ("volume_signal", "volume"),
    ]:
        if col in df.columns and df[col].sum() > 0:
            signals.append(name)
    return signals


def _build_reasons(row) -> str:
    """Build a human-readable reasons string for a scored party."""
    reasons = []
    if row.get("sar_signal", 0) > 0:
        reasons.append("SAR_LABEL")
    if row.get("laundering_signal", 0) > 0:
        lt = row.get("laundering_types", "")
        if lt:
            reasons.append(f"LAUNDERING_LINK:{lt}")
        else:
            reasons.append("LAUNDERING_LINK")
    if row.get("network_signal", 0) > 0.5:
        reasons.append(f"HIGH_CONNECTIVITY(deg={int(row.get('degree', 0))})")
    if row.get("geo_signal", 0) > 0:
        jur = int(row.get("unique_jurisdictions", 0))
        if jur > 1:
            reasons.append(f"CROSS_BORDER:{jur}_jurisdictions")
        elif row.get("cross_border_count", 0) > 0:
            reasons.append("CROSS_BORDER")
    if row.get("volume_signal", 0) > 0.8:
        reasons.append("HIGH_VOLUME")
    return ", ".join(reasons)


def run_aml_scoring(
    artifacts_dir: Path,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Standalone AML scoring pipeline.

    Run independently of the main pipeline to compute (or recompute) AML
    scores for an existing run.  Reads from the run's ``queues/`` and
    ``data/`` directories, writes results back into ``queues/``.

    Args:
        artifacts_dir: Root artifacts directory for a pipeline run
                       (e.g. ``artifacts/runs/<run-id>``).
        weights: Optional signal-weight overrides.

    Returns:
        The AML summary dict (same as ``aml_score_summary.json``).
    """
    from .enrichment import load_enrichment

    data_dir = artifacts_dir / "data"
    queues_dir = artifacts_dir / "queues"
    queues_dir.mkdir(parents=True, exist_ok=True)

    # Load enrichment (gracefully empty if no extra_info.csv)
    enrichment_df = load_enrichment(data_dir)

    # Compute scores
    scores_df = compute_aml_scores(
        risk_queue_path=queues_dir / "risk_queue",
        enrichment_df=enrichment_df,
        edges_path=data_dir / "edges_td.csv",
        weights=weights,
    )

    # Persist
    scores_df.to_parquet(queues_dir / "party_aml_scores.parquet", index=False)
    scores_df.to_csv(queues_dir / "party_aml_scores.csv", index=False)

    summary = build_aml_summary(scores_df, weights=weights)
    (queues_dir / "aml_score_summary.json").write_text(
        json.dumps(summary, indent=2)
    )

    # Rebuild artifact index if available
    try:
        from .artifacts_index import ArtifactIndexer
        indexer = ArtifactIndexer(artifacts_dir)
        indexer.build()
    except Exception:
        pass

    logger.info(
        f"AML scoring complete: {len(scores_df):,} parties scored, "
        f"results in {queues_dir}"
    )
    return summary


def _compute_fanout_ratio(edges_path: Path) -> pd.Series:
    """
    Compute fan-out ratio per entity: out_degree / (in_degree + out_degree).

    Returns a Series indexed by entity_id with float values in [0, 1].
    """
    if not edges_path.exists():
        return pd.Series(dtype=float)

    try:
        edges = pd.read_csv(edges_path)
        edges.columns = [c.strip() for c in edges.columns]
    except Exception as e:
        logger.warning(f"Failed to read edges for fanout: {e}")
        return pd.Series(dtype=float)

    # Detect src/dst columns
    src_candidates = ["src", "source", "from", "id1"]
    dst_candidates = ["dst", "target", "to", "id2"]
    lower_map = {c.lower(): c for c in edges.columns}

    src_col = dst_col = None
    for s in src_candidates:
        if s in lower_map:
            src_col = lower_map[s]
            break
    for d in dst_candidates:
        if d in lower_map:
            dst_col = lower_map[d]
            break

    if src_col is None or dst_col is None:
        return pd.Series(dtype=float)

    out_degree = edges[src_col].astype(str).value_counts()
    in_degree = edges[dst_col].astype(str).value_counts()
    total_degree = out_degree.add(in_degree, fill_value=0)
    fanout = out_degree.divide(total_degree.clip(lower=1)).fillna(0)
    return fanout
