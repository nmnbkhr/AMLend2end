"""
Metrics Builder

Builds the metrics.json file with standardized dashboard data contract.
Extracts metrics from pipeline outputs and provides a consistent format
for the UI dashboard.

Uses output_map.yaml for deterministic file lookups with fallback to heuristics.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd
import numpy as np
import yaml

logger = logging.getLogger(__name__)

# Load output mapping configuration
OUTPUT_MAP_PATH = Path(__file__).parent / "output_map.yaml"


def load_output_map() -> Dict[str, Any]:
    """Load the output mapping configuration."""
    if OUTPUT_MAP_PATH.exists():
        try:
            with open(OUTPUT_MAP_PATH) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load output_map.yaml: {e}")
    return {}


class MetricsBuilder:
    """
    Builds standardized metrics from pipeline outputs.

    The metrics JSON follows a data contract for the dashboard:
    - dataset: num_transactions, num_accounts, time_range
    - training: epochs, final_loss, duration_seconds
    - anomalies: threshold, num_flagged, top_k_preview
    - embedding: dim, num_nodes, num_edges
    - paths: chosen file paths for key artifacts
    """

    def __init__(self, artifacts_dir: Path, project_root: Path):
        """
        Initialize the metrics builder.

        Args:
            artifacts_dir: Path to the run's artifacts directory (will be resolved to absolute)
            project_root: Path to the project root (will be resolved to absolute)
        """
        self.artifacts_dir = Path(artifacts_dir).resolve()
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.artifacts_dir / "data"
        self.models_dir = self.artifacts_dir / "models"
        self.metrics_dir = self.artifacts_dir / "metrics"
        self.output_map = load_output_map()

    def _find_by_pattern(self, pattern: str) -> Optional[Path]:
        """Find a file matching a glob pattern in the artifacts directory."""
        matches = list(self.artifacts_dir.glob(pattern))
        return matches[0] if matches else None

    def _find_mapped_file(self, map_key: str, section: str = "tables") -> Optional[Path]:
        """Find a file using the output mapping."""
        section_map = self.output_map.get(section, {})
        if map_key not in section_map:
            return None

        patterns = section_map[map_key].get("patterns", [])
        for pattern in patterns:
            found = self._find_by_pattern(pattern)
            if found:
                return found
        return None

    def _get_column_alias(self, df: pd.DataFrame, canonical_name: str) -> Optional[str]:
        """Get the actual column name from the dataframe using aliases."""
        aliases = self.output_map.get("column_aliases", {}).get(canonical_name, [canonical_name])
        for alias in aliases:
            if alias in df.columns:
                return alias
        return None

    def build(self, run_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build the complete metrics dictionary.

        Args:
            run_results: Results from the orchestrator

        Returns:
            dict with structured metrics
        """
        logger.info("Building metrics...")

        # Build paths first to share found paths with other sections
        paths = self._build_paths()

        metrics = {
            "generated_at": datetime.utcnow().isoformat(),
            "run_id": run_results.get("run_id"),
            "dataset": self._build_dataset_metrics(),
            "training": self._build_training_metrics(run_results),
            "anomalies": self._build_anomaly_metrics(paths),
            "embedding": self._build_embedding_metrics(),
            "execution": self._build_execution_metrics(run_results),
            "paths": paths,
        }

        return metrics

    def _build_paths(self) -> Dict[str, Any]:
        """Build paths section with chosen file paths for key artifacts."""
        paths = {
            "anomalies_table_path": None,
            "key_plots_paths": [],
            "model_paths": {},
        }

        # Find primary anomalies table
        for key in ["anomalies_primary", "anomalies_nodes"]:
            found = self._find_mapped_file(key, "tables")
            if found:
                paths["anomalies_table_path"] = str(found.relative_to(self.artifacts_dir))
                break

        # Fallback to heuristics
        if not paths["anomalies_table_path"]:
            for pattern in ["data/alert_nodes_td.csv", "data/anomalies.csv", "data/node_embeddings_fg.*"]:
                found = self._find_by_pattern(pattern)
                if found:
                    paths["anomalies_table_path"] = str(found.relative_to(self.artifacts_dir))
                    break

        # Find key plots
        plots_map = self.output_map.get("plots", {})
        priority_keys = ["executive", "anomaly_distribution", "top_anomalies", "suspicious_volume"]
        for key in priority_keys:
            if key in plots_map:
                for pattern in plots_map[key].get("patterns", []):
                    found = self._find_by_pattern(pattern)
                    if found:
                        paths["key_plots_paths"].append(str(found.relative_to(self.artifacts_dir)))
                        break

        # Find model paths
        models_map = self.output_map.get("models", {})
        for key, map_key in [("model", "gan_detector"), ("threshold", "gan_threshold"), ("metadata", "gan_metadata")]:
            if map_key in models_map:
                for pattern in models_map[map_key].get("patterns", []):
                    found = self._find_by_pattern(pattern)
                    if found:
                        paths["model_paths"][key] = str(found.relative_to(self.artifacts_dir))
                        break

        return paths

    def _build_dataset_metrics(self) -> Dict[str, Any]:
        """Build dataset-related metrics."""
        metrics = {
            "num_transactions": None,
            "num_accounts": None,
            "num_nodes": None,
            "time_range": None,
            "data_files": [],
        }

        try:
            # Try to read edges/transactions using output mapping
            edges_file = self._find_mapped_file("edges_td", "tables")
            if not edges_file:
                edges_file = self._find_file("edges_td.csv", ["data", "training_data"])

            if edges_file:
                df = pd.read_csv(edges_file)
                metrics["num_transactions"] = len(df)

                # Extract unique accounts (source + target)
                if "source" in df.columns and "target" in df.columns:
                    unique_accounts = set(df["source"].unique()) | set(df["target"].unique())
                    metrics["num_accounts"] = len(unique_accounts)

                # Time range if available
                for time_col in ["timestamp", "date", "time", "tx_date"]:
                    if time_col in df.columns:
                        try:
                            dates = pd.to_datetime(df[time_col])
                            metrics["time_range"] = {
                                "start": dates.min().isoformat(),
                                "end": dates.max().isoformat(),
                            }
                            break
                        except:
                            pass

            # Try nodes file using output mapping
            nodes_file = self._find_mapped_file("nodes_td", "tables")
            if not nodes_file:
                nodes_file = self._find_file("node_td.csv", ["data", "training_data"])

            if nodes_file:
                df = pd.read_csv(nodes_file)
                metrics["num_nodes"] = len(df)
                metrics["num_accounts"] = len(df)

            # List data files
            if self.data_dir.exists():
                for f in self.data_dir.glob("*.csv"):
                    metrics["data_files"].append(f.name)
                for f in self.data_dir.glob("*.parquet"):
                    metrics["data_files"].append(f.name)

        except Exception as e:
            logger.warning(f"Failed to build dataset metrics: {e}")

        return metrics

    def _build_training_metrics(self, run_results: Dict[str, Any]) -> Dict[str, Any]:
        """Build training-related metrics."""
        metrics = {
            "epochs": None,
            "final_loss": None,
            "duration_seconds": None,
            "model_path": None,
            "model_files": [],
            "threshold": None,
        }

        try:
            # Get params from run results
            params = run_results.get("params", {})
            if isinstance(params, dict):
                metrics["epochs"] = params.get("epochs")
                # Also get threshold from params
                if params.get("threshold"):
                    metrics["threshold"] = params.get("threshold")

            # Try to find model directory
            model_dirs = list(self.models_dir.glob("gan_anomaly_*"))
            if not model_dirs:
                model_dirs = list(self.project_root.glob("models/gan_anomaly_*"))

            if model_dirs:
                model_dir = model_dirs[0]

                # Full relative path from artifacts_dir
                if self.models_dir in model_dir.parents or model_dir.parent == self.models_dir:
                    metrics["model_path"] = f"models/{model_dir.name}"
                else:
                    metrics["model_path"] = str(model_dir.relative_to(self.project_root))

                # List all model files
                for f in model_dir.iterdir():
                    if f.is_file():
                        metrics["model_files"].append(f.name)

                # Check for metadata file
                metadata_file = model_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file) as f:
                        model_meta = json.load(f)
                        metrics["epochs"] = model_meta.get("epochs", metrics["epochs"])
                        metrics["final_loss"] = model_meta.get("final_loss")
                        if not metrics["threshold"]:
                            metrics["threshold"] = model_meta.get("threshold")

                # Load threshold from .npy file if not yet set
                threshold_file = model_dir / "threshold.npy"
                if threshold_file.exists() and not metrics["threshold"]:
                    try:
                        metrics["threshold"] = float(np.load(threshold_file))
                    except Exception:
                        pass

            # Duration from step results
            step_results = run_results.get("step_results", {})
            training_step = step_results.get(8, {})  # Step 8 is training
            if training_step.get("execution_time"):
                metrics["duration_seconds"] = training_step["execution_time"]

        except Exception as e:
            logger.warning(f"Failed to build training metrics: {e}")

        return metrics

    def _build_anomaly_metrics(self, paths: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Build anomaly detection metrics.

        Priority:
        1. Use alert_nodes_td.csv if exists (from output_map)
        2. Fallback to node_embeddings_fg.* or heuristics
        """
        metrics = {
            "threshold": None,
            "num_flagged": None,
            "anomaly_rate": None,
            "anomaly_rate_nodes_pct": None,
            "anomalies_table_path": None,
            "top_k_preview": [],
            "source_file": None,
        }

        try:
            # Find threshold
            threshold_files = list(self.models_dir.glob("*/threshold.npy"))
            if not threshold_files:
                threshold_files = list(self.project_root.glob("models/gan_anomaly_*/threshold.npy"))

            if threshold_files:
                threshold = np.load(threshold_files[0])
                metrics["threshold"] = float(threshold)

            # Try to find primary anomalies table (alert_nodes_td.csv)
            anomalies_df = None
            source_file = None

            # Use output mapping first
            primary_file = self._find_mapped_file("anomalies_primary", "tables")
            if not primary_file:
                primary_file = self._find_mapped_file("anomalies_nodes", "tables")

            if primary_file and primary_file.exists():
                anomalies_df = pd.read_csv(primary_file)
                source_file = str(primary_file.relative_to(self.artifacts_dir))
                metrics["source_file"] = source_file
                metrics["anomalies_table_path"] = source_file
            else:
                # Fallback to heuristics
                embeddings_file = self._find_file("node_embeddings_fg.parquet", ["data", "output"])
                if not embeddings_file:
                    embeddings_file = self._find_file("node_embeddings_fg.csv", ["data", "output"])

                if embeddings_file:
                    if str(embeddings_file).endswith(".parquet"):
                        anomalies_df = pd.read_parquet(embeddings_file)
                    else:
                        anomalies_df = pd.read_csv(embeddings_file)
                    source_file = str(embeddings_file.relative_to(self.artifacts_dir)) if self.artifacts_dir in embeddings_file.parents else embeddings_file.name
                    metrics["source_file"] = source_file
                    metrics["anomalies_table_path"] = source_file

            if anomalies_df is not None:
                total_rows = len(anomalies_df)

                # Find columns using aliases
                is_sar_col = self._get_column_alias(anomalies_df, "is_sar")
                score_col = self._get_column_alias(anomalies_df, "score")
                id_col = self._get_column_alias(anomalies_df, "id")

                # Count anomalies/flagged items
                if is_sar_col:
                    metrics["num_flagged"] = int(anomalies_df[is_sar_col].sum())
                elif score_col and metrics["threshold"]:
                    metrics["num_flagged"] = int((anomalies_df[score_col] > metrics["threshold"]).sum())
                else:
                    # If this is alert_nodes_td.csv, count all rows as flagged
                    if source_file and "alert_nodes" in source_file:
                        metrics["num_flagged"] = total_rows

                # Anomaly rate (within the anomalies table)
                if metrics["num_flagged"] is not None and total_rows > 0:
                    metrics["anomaly_rate"] = round((metrics["num_flagged"] / total_rows) * 100, 2)

                # Anomaly rate as percentage of all nodes
                # Try to get total nodes count from dataset metrics or nodes file
                total_nodes = None
                nodes_file = self._find_mapped_file("nodes_td", "tables")
                if not nodes_file:
                    nodes_file = self._find_file("node_td.csv", ["data", "training_data"])
                if nodes_file and nodes_file.exists():
                    try:
                        nodes_df = pd.read_csv(nodes_file)
                        total_nodes = len(nodes_df)
                    except Exception:
                        pass

                if total_nodes and metrics["num_flagged"] is not None:
                    metrics["anomaly_rate_nodes_pct"] = round((metrics["num_flagged"] / total_nodes) * 100, 4)

                # Build top_k_preview with preferred columns
                metrics["top_k_preview"] = self._build_top_k_preview(anomalies_df, score_col, is_sar_col)

        except Exception as e:
            logger.warning(f"Failed to build anomaly metrics: {e}")

        return metrics

    def _build_top_k_preview(
        self,
        df: pd.DataFrame,
        score_col: Optional[str] = None,
        is_sar_col: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Build top K preview with preferred columns.

        Preferred columns: id, is_sar, score, amount, degree, risk, type
        Gracefully handles missing columns.
        """
        preview_columns = self.output_map.get("preview_columns", [
            "id", "is_sar", "score", "amount", "degree", "risk", "type"
        ])

        # Find available columns using aliases
        available_cols = []
        col_mapping = {}  # Maps canonical name to actual column name

        for canonical in preview_columns:
            actual_col = self._get_column_alias(df, canonical)
            if actual_col and actual_col in df.columns:
                available_cols.append(actual_col)
                col_mapping[canonical] = actual_col

        # If no preferred columns found, use first few non-embedding columns
        if not available_cols:
            available_cols = [c for c in df.columns if not c.startswith("emb_")][:5]

        # Sort dataframe
        if score_col and score_col in df.columns:
            top_df = df.nlargest(limit, score_col)
        elif is_sar_col and is_sar_col in df.columns:
            # Put SAR=1 rows first
            top_df = df.sort_values(by=is_sar_col, ascending=False).head(limit)
        else:
            top_df = df.head(limit)

        # Select columns and convert to records
        try:
            preview_df = top_df[available_cols].fillna("")
            return preview_df.to_dict(orient="records")
        except Exception as e:
            logger.warning(f"Failed to build top_k_preview: {e}")
            return []

    def _build_embedding_metrics(self) -> Dict[str, Any]:
        """Build embedding-related metrics."""
        metrics = {
            "dim": None,
            "num_nodes": None,
            "num_edges": None,
        }

        try:
            # Find embeddings file
            embeddings_file = self._find_file("node_embeddings_fg.parquet", ["data", "output"])
            if not embeddings_file:
                embeddings_file = self._find_file("node_embeddings_fg.csv", ["data", "output"])

            if embeddings_file:
                if str(embeddings_file).endswith(".parquet"):
                    df = pd.read_parquet(embeddings_file)
                else:
                    df = pd.read_csv(embeddings_file)

                metrics["num_nodes"] = len(df)

                # Count embedding dimensions
                emb_cols = [c for c in df.columns if c.startswith("emb_")]
                metrics["dim"] = len(emb_cols)

            # Edge count
            edges_file = self._find_file("edges_td.csv", ["data", "training_data"])
            if edges_file:
                edges_df = pd.read_csv(edges_file)
                metrics["num_edges"] = len(edges_df)

        except Exception as e:
            logger.warning(f"Failed to build embedding metrics: {e}")

        return metrics

    def _build_execution_metrics(self, run_results: Dict[str, Any]) -> Dict[str, Any]:
        """Build execution-related metrics."""
        metrics = {
            "started_at": run_results.get("started_at"),
            "completed_at": run_results.get("completed_at"),
            "duration_seconds": run_results.get("execution_time_seconds"),
            "steps_completed": run_results.get("steps_completed"),
            "steps_failed": run_results.get("steps_failed"),
            "status": "completed" if not run_results.get("error") else "failed",
            "key_plots_paths": [],
        }

        # Collect key plots paths (up to 12 in priority order)
        plots_dir = self.artifacts_dir / "plots"
        if plots_dir.exists():
            # Priority order for key plots
            priority_patterns = [
                "dashboard_executive.png",
                "anomaly_distribution.png",
                "top_anomalies.png",
                "top_suspicious_by_volume.png",
                "dashboard_risk.png",
                "transaction_network.png",
                "degree_distribution.png",
                "money_flow.png",
            ]

            added_plots = set()
            for pattern in priority_patterns:
                plot_path = plots_dir / pattern
                if plot_path.exists():
                    rel_path = f"plots/{pattern}"
                    metrics["key_plots_paths"].append(rel_path)
                    added_plots.add(pattern)

            # Add remaining plots up to 12 total
            remaining_slots = 12 - len(metrics["key_plots_paths"])
            if remaining_slots > 0:
                for plot_file in sorted(plots_dir.glob("*.png")):
                    if plot_file.name not in added_plots:
                        metrics["key_plots_paths"].append(f"plots/{plot_file.name}")
                        remaining_slots -= 1
                        if remaining_slots <= 0:
                            break

        return metrics

    def _find_file(self, filename: str, search_dirs: List[str]) -> Optional[Path]:
        """
        Find a file in multiple possible directories.

        Args:
            filename: Name of the file to find
            search_dirs: List of directory names to search

        Returns:
            Path to the file if found, None otherwise
        """
        for dir_name in search_dirs:
            # Check in artifacts dir
            path = self.artifacts_dir / dir_name / filename
            if path.exists():
                return path

            # Check in project root
            path = self.project_root / dir_name / filename
            if path.exists():
                return path

        return None
