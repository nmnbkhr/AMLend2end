"""
Headless data loader for chart generation — no Streamlit dependency.

Loads all data needed by chart generators from a run's artifact directory.
Mirrors the data loading logic in streamlit_app.py lines 1890-2017.
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


DEMO_CONFIG = {
    "avg_loss_per_undetected_aml": 0.15,
    "investigation_cost_per_alert": 500,
    "false_positive_cost": 200,
    "regulatory_fine_multiplier": 3.0,
    "recovery_rate_detected": 0.70,
}


@dataclass
class ChartData:
    """Container for all data needed by chart generators."""

    # Analytics tab data
    alert_nodes_df: Optional[pd.DataFrame] = None
    edges_df: Optional[pd.DataFrame] = None
    embeddings_df: Optional[pd.DataFrame] = None

    # Interactive dashboard computed data
    node_embeddings: Optional[pd.DataFrame] = None
    node_money: Optional[pd.DataFrame] = None
    nodes_df: Optional[pd.DataFrame] = None
    anomaly_scores: Optional[np.ndarray] = None
    threshold_val: Optional[float] = None

    # Computed metrics
    n_anomalies: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    suspicious_txn_value: float = 0.0
    recovered_amount: float = 0.0
    total_operational_cost: float = 0.0
    net_savings: float = 0.0
    regulatory_fine_risk: float = 0.0
    potential_loss_detected: float = 0.0
    investigation_cost: float = 0.0
    false_positive_cost: float = 0.0

    # Tier queue data
    risk_queue_df: Optional[pd.DataFrame] = None

    # AML scores data
    aml_scores_df: Optional[pd.DataFrame] = None

    # Errors per group (non-fatal)
    errors: dict = field(default_factory=dict)


def load_analytics_data(artifacts_dir: Path, data: Optional[ChartData] = None) -> ChartData:
    """Load data needed for Analytics tab charts."""
    if data is None:
        data = ChartData()

    data_dir = artifacts_dir / "data"

    try:
        alert_path = data_dir / "alert_nodes_td.csv"
        if alert_path.exists():
            data.alert_nodes_df = pd.read_csv(alert_path)
            logger.info(f"Loaded alert_nodes_td.csv: {len(data.alert_nodes_df)} rows")
    except Exception as e:
        data.errors["alert_nodes"] = str(e)
        logger.warning(f"Failed to load alert_nodes_td.csv: {e}")

    try:
        edges_path = data_dir / "edges_td.csv"
        if edges_path.exists():
            data.edges_df = pd.read_csv(edges_path)
            logger.info(f"Loaded edges_td.csv: {len(data.edges_df)} rows")
    except Exception as e:
        data.errors["edges"] = str(e)
        logger.warning(f"Failed to load edges_td.csv: {e}")

    try:
        emb_path = data_dir / "node_embeddings_fg.parquet"
        if emb_path.exists():
            data.embeddings_df = pd.read_parquet(emb_path)
            logger.info(f"Loaded node_embeddings_fg.parquet: {len(data.embeddings_df)} rows")
    except Exception as e:
        data.errors["embeddings"] = str(e)
        logger.warning(f"Failed to load node_embeddings_fg.parquet: {e}")

    return data


def load_dashboard_data(artifacts_dir: Path, data: Optional[ChartData] = None) -> ChartData:
    """
    Load data for Interactive Dashboard charts.

    Uses pre-computed scores from notebook 10/11 when available.
    Falls back to loading the keras model and running model.predict()
    only if anomaly_score is not already in the parquet.
    """
    if data is None:
        data = ChartData()

    data_dir = artifacts_dir / "data"
    models_dir = artifacts_dir / "models"

    try:
        # Load nodes
        nodes_path = data_dir / "node_td.csv"
        if nodes_path.exists():
            data.nodes_df = pd.read_csv(nodes_path)

        # Load embeddings
        embeddings_path = data_dir / "node_embeddings_fg.parquet"
        if not embeddings_path.exists():
            data.errors["dashboard_embeddings"] = "node_embeddings_fg.parquet not found"
            return data
        if data.embeddings_df is None:
            data.embeddings_df = pd.read_parquet(embeddings_path)

        data.node_embeddings = data.embeddings_df.copy()

        # Load threshold
        if not models_dir.exists():
            data.errors["dashboard_model"] = f"Models directory not found: {models_dir}"
            return data

        model_dirs = sorted(
            [d for d in models_dir.iterdir() if d.is_dir() and d.name.startswith("gan_anomaly_")]
        )
        if not model_dirs:
            data.errors["dashboard_model"] = "No trained model found"
            return data

        latest_model_dir = model_dirs[-1]
        data.threshold_val = float(np.load(latest_model_dir / "threshold.npy"))

        # Check for pre-computed anomaly scores (saved by notebook 10)
        has_precomputed = all(
            c in data.node_embeddings.columns
            for c in ("anomaly_score", "is_anomaly", "risk_score")
        )

        if has_precomputed:
            logger.info("Using pre-computed anomaly scores from parquet")
            data.anomaly_scores = data.node_embeddings["anomaly_score"].values
        else:
            logger.info("No pre-computed scores found, running model.predict()")
            emb_cols = [c for c in data.node_embeddings.columns if c.startswith("emb_")]
            from tensorflow import keras

            model = keras.models.load_model(str(latest_model_dir / "anomaly_detector.keras"))
            all_embeddings = data.node_embeddings[emb_cols].values
            reconstructed = model.predict(all_embeddings, verbose=0)
            data.anomaly_scores = np.mean(np.square(all_embeddings - reconstructed), axis=1)

            data.node_embeddings["anomaly_score"] = data.anomaly_scores
            data.node_embeddings["is_anomaly"] = data.anomaly_scores > data.threshold_val
            score_min, score_max = data.anomaly_scores.min(), data.anomaly_scores.max()
            if score_max > score_min:
                data.node_embeddings["risk_score"] = (data.anomaly_scores - score_min) / (score_max - score_min)
            else:
                data.node_embeddings["risk_score"] = 0.0

        # Try pre-computed enriched edges (saved by notebook 11)
        enriched_edges_path = data_dir / "edges_enriched.parquet"
        if enriched_edges_path.exists():
            data.edges_df = pd.read_parquet(enriched_edges_path)
            logger.info(f"Loaded pre-computed edges_enriched.parquet: {len(data.edges_df)} rows")
        else:
            # Load raw edges and compute risk mapping
            edges_path = data_dir / "edges_td.csv"
            if not edges_path.exists():
                data.errors["dashboard_edges"] = "edges_td.csv not found"
                return data
            if data.edges_df is None:
                data.edges_df = pd.read_csv(edges_path)

            node_risk_dict = data.node_embeddings.set_index("id")["risk_score"].to_dict()
            node_anomaly_dict = data.node_embeddings.set_index("id")["is_anomaly"].to_dict()

            data.edges_df["source_risk"] = data.edges_df["source"].map(node_risk_dict).fillna(0)
            data.edges_df["target_risk"] = data.edges_df["target"].map(node_risk_dict).fillna(0)
            data.edges_df["edge_risk"] = data.edges_df[["source_risk", "target_risk"]].max(axis=1)
            data.edges_df["source_anomaly"] = data.edges_df["source"].map(node_anomaly_dict).fillna(False)
            data.edges_df["target_anomaly"] = data.edges_df["target"].map(node_anomaly_dict).fillna(False)
            data.edges_df["is_suspicious"] = data.edges_df["source_anomaly"] | data.edges_df["target_anomaly"]

            if data.nodes_df is not None:
                node_type_dict = data.nodes_df.set_index("id")["type"].to_dict()
                data.edges_df["source_type"] = data.edges_df["source"].map(node_type_dict).fillna(-1).astype(int)
                data.edges_df["target_type"] = data.edges_df["target"].map(node_type_dict).fillna(-1).astype(int)

        # Try pre-computed node money flow (saved by notebook 11)
        money_flow_path = data_dir / "node_money_flow.parquet"
        if money_flow_path.exists():
            data.node_money = pd.read_parquet(money_flow_path)
            logger.info(f"Loaded pre-computed node_money_flow.parquet: {len(data.node_money)} rows")
        else:
            # Compute money flow per node
            outgoing = data.edges_df.groupby("source").agg(
                {"base_amt": "sum", "tran_id": "count"}
            ).rename(columns={"base_amt": "outgoing_amt", "tran_id": "outgoing_count"})
            incoming = data.edges_df.groupby("target").agg(
                {"base_amt": "sum", "tran_id": "count"}
            ).rename(columns={"base_amt": "incoming_amt", "tran_id": "incoming_count"})

            data.node_money = data.node_embeddings[["id", "anomaly_score", "is_anomaly", "risk_score"]].copy()
            if "is_sar" in data.node_embeddings.columns:
                data.node_money["is_sar"] = data.node_embeddings["is_sar"]
            data.node_money = data.node_money.merge(outgoing, left_on="id", right_index=True, how="left")
            data.node_money = data.node_money.merge(incoming, left_on="id", right_index=True, how="left")
            data.node_money = data.node_money.fillna(0)
            data.node_money["total_volume"] = data.node_money["outgoing_amt"] + data.node_money["incoming_amt"]
            data.node_money["total_transactions"] = data.node_money["outgoing_count"] + data.node_money["incoming_count"]
            data.node_money["net_flow"] = data.node_money["incoming_amt"] - data.node_money["outgoing_amt"]

            if data.nodes_df is not None:
                data.node_money = data.node_money.merge(data.nodes_df[["id", "type"]], on="id", how="left")

        # Financial metrics
        n_anomalies = int(data.node_embeddings["is_anomaly"].sum())
        n_normal = len(data.node_embeddings) - n_anomalies
        data.n_anomalies = n_anomalies
        data.suspicious_txn_value = float(data.edges_df[data.edges_df["is_suspicious"]]["base_amt"].sum())

        if "is_sar" in data.node_embeddings.columns:
            data.tp = int(((data.node_embeddings["is_sar"] == 1) & (data.node_embeddings["is_anomaly"])).sum())
            data.fp = int(((data.node_embeddings["is_sar"] == 0) & (data.node_embeddings["is_anomaly"])).sum())
            data.fn = int(((data.node_embeddings["is_sar"] == 1) & (~data.node_embeddings["is_anomaly"])).sum())
            data.tn = int(((data.node_embeddings["is_sar"] == 0) & (~data.node_embeddings["is_anomaly"])).sum())
        else:
            data.tp = int(n_anomalies * 0.10)
            data.fp = n_anomalies - data.tp
            data.fn = int(n_normal * 0.01)
            data.tn = n_normal - data.fn

        cfg = DEMO_CONFIG
        avg_suspicious_txn = data.suspicious_txn_value / max(n_anomalies, 1)
        data.potential_loss_detected = data.tp * avg_suspicious_txn * cfg["avg_loss_per_undetected_aml"]
        data.recovered_amount = data.potential_loss_detected * cfg["recovery_rate_detected"]
        normal_txn_value = float(data.edges_df[~data.edges_df["is_suspicious"]]["base_amt"].sum())
        avg_normal_txn = normal_txn_value / max(n_normal, 1)
        potential_loss_undetected = data.fn * avg_normal_txn * cfg["avg_loss_per_undetected_aml"]
        data.regulatory_fine_risk = potential_loss_undetected * cfg["regulatory_fine_multiplier"]
        data.investigation_cost = n_anomalies * cfg["investigation_cost_per_alert"]
        data.false_positive_cost = data.fp * cfg["false_positive_cost"]
        data.total_operational_cost = data.investigation_cost + data.false_positive_cost
        data.net_savings = data.recovered_amount - data.total_operational_cost

        data.precision = data.tp / max(data.tp + data.fp, 1)
        data.recall = data.tp / max(data.tp + data.fn, 1)
        data.f1 = 2 * (data.precision * data.recall) / max(data.precision + data.recall, 1e-9)

        logger.info(f"Dashboard data loaded: {len(data.node_embeddings)} nodes, {n_anomalies} anomalies")

    except Exception as e:
        data.errors["dashboard"] = str(e)
        logger.error(f"Failed to load dashboard data: {e}", exc_info=True)

    return data


def load_tier_queue_data(artifacts_dir: Path, data: Optional[ChartData] = None) -> ChartData:
    """Load risk queue data for Tier Queue charts."""
    if data is None:
        data = ChartData()

    queues_dir = artifacts_dir / "queues"
    try:
        # Try parquet first, then CSV
        for pattern in ["risk_queue.parquet", "entities_tier_*.parquet", "risk_queue.csv"]:
            matches = list(queues_dir.glob(pattern)) if queues_dir.exists() else []
            if matches:
                if pattern.endswith(".parquet"):
                    frames = [pd.read_parquet(f) for f in matches]
                    data.risk_queue_df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
                else:
                    data.risk_queue_df = pd.read_csv(matches[0])
                logger.info(f"Loaded risk queue: {len(data.risk_queue_df)} rows")
                break
    except Exception as e:
        data.errors["tier_queue"] = str(e)
        logger.warning(f"Failed to load risk queue data: {e}")

    return data


def load_aml_scores_data(artifacts_dir: Path, data: Optional[ChartData] = None) -> ChartData:
    """Load AML scores data for AML Scores charts."""
    if data is None:
        data = ChartData()

    data_dir = artifacts_dir / "data"
    try:
        for name in ["aml_scores.parquet", "aml_scores.csv"]:
            path = data_dir / name
            if path.exists():
                if name.endswith(".parquet"):
                    data.aml_scores_df = pd.read_parquet(path)
                else:
                    data.aml_scores_df = pd.read_csv(path)
                logger.info(f"Loaded AML scores: {len(data.aml_scores_df)} rows")
                break
    except Exception as e:
        data.errors["aml_scores"] = str(e)
        logger.warning(f"Failed to load AML scores data: {e}")

    return data


def load_all_data(artifacts_dir: Path) -> ChartData:
    """
    Load all data for all chart groups.

    Each loader is called in sequence, merging into a single ChartData.
    Errors in one group do not prevent loading of others.
    """
    data = ChartData()
    data = load_analytics_data(artifacts_dir, data)
    data = load_dashboard_data(artifacts_dir, data)
    data = load_tier_queue_data(artifacts_dir, data)
    data = load_aml_scores_data(artifacts_dir, data)
    return data
