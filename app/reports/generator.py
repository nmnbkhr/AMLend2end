"""
Report Generator

Generates HTML reports from pipeline run results using Jinja2 templates.
Supports embedded images, alerts table, and run bundle zip creation.
"""

import json
import logging
import base64
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

import yaml
import pandas as pd
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"

# Load output mapping
OUTPUT_MAP_PATH = Path(__file__).parent.parent / "pipeline_runner" / "output_map.yaml"


def load_output_map() -> Dict[str, Any]:
    """Load the output mapping configuration."""
    if OUTPUT_MAP_PATH.exists():
        try:
            with open(OUTPUT_MAP_PATH) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load output_map.yaml: {e}")
    return {}


class ReportGenerator:
    """
    Generates HTML reports from pipeline run results.
    """

    def __init__(
        self,
        run_id: str,
        results: Dict[str, Any],
        artifacts_dir: Path,
    ):
        """
        Initialize the report generator.

        Args:
            run_id: Unique run identifier
            results: Pipeline execution results
            artifacts_dir: Path to the run's artifact directory
        """
        self.run_id = run_id
        self.results = results
        self.artifacts_dir = Path(artifacts_dir)
        self.report_dir = self.artifacts_dir / "report"
        self.plots_dir = self.artifacts_dir / "plots"

        # Setup Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )

        # Load output mapping
        self.output_map = load_output_map()

    def _format_duration(self, seconds: Optional[float]) -> str:
        """Format duration in seconds to human-readable string."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} hours"

    def _collect_plots(self, embed: bool = True, prefer_styled: bool = True) -> List[Dict[str, Any]]:
        """
        Collect plot files and prepare them for the report.

        Args:
            embed: If True, embed images as base64 data for standalone HTML viewing.
            prefer_styled: If True, use styled plots from plots/styled/ if they exist.

        Returns:
            List of plot dictionaries with base64-embedded image data.
        """
        plots = []

        if not self.plots_dir.exists():
            return plots

        # Check for styled plots
        styled_dir = self.plots_dir / "styled"
        use_styled = prefer_styled and styled_dir.exists() and any(styled_dir.glob("*.png"))
        source_dir = styled_dir if use_styled else self.plots_dir
        relative_path_prefix = "../plots/styled" if use_styled else "../plots"

        # Define plot titles based on filename patterns
        plot_titles = {
            "transaction_network": "Transaction Network Graph",
            "anomaly_distribution": "Anomaly Score Distribution",
            "degree_distribution": "Node Degree Distribution",
            "money_flow": "Money Flow Analysis",
            "top_anomalies": "Top Anomalies",
            "dashboard_executive": "Executive Dashboard",
            "dashboard_risk": "Risk Network",
            "pattern_": "Pattern Analysis",
            "dashboard_loss": "Loss & Savings Analysis",
            "dashboard_node": "Node Profiles",
            "dashboard_transaction": "Transaction Deep-Dive",
            "top_suspicious": "Top Suspicious by Volume",
        }

        for plot_file in sorted(source_dir.glob("*.png")):
            # Determine title from filename
            title = plot_file.stem.replace("_", " ").title()
            for pattern, custom_title in plot_titles.items():
                if pattern in plot_file.stem.lower():
                    title = custom_title
                    break

            plot_info = {
                "title": title,
                "path": f"{relative_path_prefix}/{plot_file.name}",
                "filename": plot_file.name,
                "embedded": False,
                "styled": use_styled,
            }

            # Embed as base64 for standalone HTML viewing
            if embed:
                try:
                    with open(plot_file, "rb") as f:
                        plot_info["data"] = base64.b64encode(f.read()).decode("utf-8")
                        plot_info["embedded"] = True
                except Exception as e:
                    logger.warning(f"Failed to embed plot {plot_file}: {e}")

            plots.append(plot_info)

        if use_styled:
            logger.info(f"Using {len(plots)} styled plots for report")

        return plots

    def _load_rules(self) -> List[Dict[str, Any]]:
        """Load detection rules from the pipeline output."""
        rules = []

        rules_file = self.artifacts_dir / "data" / "aml_rules.json"
        if not rules_file.exists():
            # Try the original output location
            rules_file = self.artifacts_dir.parent.parent.parent / "output" / "aml_rules.json"

        if rules_file.exists():
            try:
                with open(rules_file) as f:
                    rules_data = json.load(f)

                # Parse rules from the JSON structure
                if isinstance(rules_data, dict):
                    for category, category_rules in rules_data.items():
                        if isinstance(category_rules, list):
                            for rule in category_rules[:5]:  # Top 5 rules per category
                                rules.append({
                                    "description": rule.get("rule", rule.get("description", "Unknown")),
                                    "confidence": round(rule.get("suspicious_rate", 0) * 100, 1),
                                    "pattern_type": category.replace("_", " ").title(),
                                })
                elif isinstance(rules_data, list):
                    for rule in rules_data[:10]:
                        rules.append({
                            "description": rule.get("rule", rule.get("description", "Unknown")),
                            "confidence": round(rule.get("suspicious_rate", rule.get("confidence", 0)) * 100, 1),
                            "pattern_type": rule.get("category", "General"),
                        })

            except Exception as e:
                logger.warning(f"Failed to load rules: {e}")

        return rules

    def _build_dataset_summary(self) -> Dict[str, Any]:
        """Build dataset summary from available data."""
        summary = {}

        if self.results.get("total_nodes"):
            summary["Total Nodes"] = f"{self.results['total_nodes']:,}"

        if self.results.get("total_transactions"):
            summary["Total Transactions"] = f"{self.results['total_transactions']:,}"

        # Try to load additional stats from data files
        try:
            node_file = self.artifacts_dir / "data" / "node_embeddings_fg.parquet"
            if node_file.exists():
                import pandas as pd
                df = pd.read_parquet(node_file)
                summary["Embedding Dimensions"] = str(len([c for c in df.columns if c.startswith("emb_")]))

                if "is_sar" in df.columns:
                    sar_count = df["is_sar"].sum()
                    sar_rate = (sar_count / len(df)) * 100
                    summary["Labeled Suspicious (SAR)"] = f"{int(sar_count):,} ({sar_rate:.2f}%)"

        except Exception as e:
            logger.debug(f"Could not load additional dataset stats: {e}")

        return summary

    def _build_anomaly_results(self) -> Optional[Dict[str, Any]]:
        """Build anomaly detection results summary."""
        results = {}

        if self.results.get("anomalies_detected") is not None:
            results["total_anomalies"] = self.results["anomalies_detected"]

            if self.results.get("total_nodes"):
                rate = (self.results["anomalies_detected"] / self.results["total_nodes"]) * 100
                results["anomaly_rate"] = f"{rate:.2f}"

        # Try to load threshold
        try:
            import numpy as np
            threshold_files = list(self.artifacts_dir.glob("models/*/threshold.npy"))
            if threshold_files:
                threshold = np.load(threshold_files[0])
                results["threshold"] = f"{float(threshold):.6f}"
        except Exception:
            pass

        return results if results else None

    def _collect_key_plots(self, embed: bool = True) -> List[Dict[str, Any]]:
        """
        Collect key plots in priority order with optional base64 embedding.

        Priority: dashboard_executive, anomaly_distribution, top_anomalies, top_suspicious_by_volume
        Plus up to 4 more from other plots.
        """
        key_plots = []

        # Priority plot filenames
        priority_plots = [
            ("plots/dashboard_executive.png", "Executive Dashboard"),
            ("plots/anomaly_distribution.png", "Anomaly Score Distribution"),
            ("plots/top_anomalies.png", "Top Anomalies"),
            ("plots/top_suspicious_by_volume.png", "Top Suspicious by Volume"),
        ]

        for pattern, title in priority_plots:
            plot_path = self.artifacts_dir / pattern
            if plot_path.exists():
                plot_info = {
                    "title": title,
                    "path": f"../{pattern}",
                    "filename": plot_path.name,
                    "embedded": False,
                }
                if embed:
                    try:
                        with open(plot_path, "rb") as f:
                            plot_info["data"] = base64.b64encode(f.read()).decode("utf-8")
                            plot_info["embedded"] = True
                    except Exception as e:
                        logger.warning(f"Failed to embed plot {plot_path}: {e}")
                key_plots.append(plot_info)

        # Add up to 4 more plots from the plots directory
        if self.plots_dir.exists():
            added_names = {p["filename"] for p in key_plots}
            remaining_slots = 8 - len(key_plots)

            for plot_file in sorted(self.plots_dir.glob("*.png")):
                if plot_file.name in added_names:
                    continue
                if remaining_slots <= 0:
                    break

                title = plot_file.stem.replace("_", " ").title()
                key_plots.append({
                    "title": title,
                    "path": f"../plots/{plot_file.name}",
                    "filename": plot_file.name,
                    "embedded": False,
                })
                remaining_slots -= 1

        return key_plots

    def _load_alert_data(self, limit: int = 50) -> Dict[str, Any]:
        """
        Load alert data from alert_nodes_td.csv.

        Returns dict with top_alerts, alert_columns, alerts_source_file, alerts_total_count
        """
        result = {
            "top_alerts": [],
            "alert_columns": [],
            "alerts_source_file": None,
            "alerts_total_count": 0,
        }

        # Try to find alert_nodes_td.csv
        alert_file = self.artifacts_dir / "data" / "alert_nodes_td.csv"
        if not alert_file.exists():
            return result

        try:
            df = pd.read_csv(alert_file)
            result["alerts_source_file"] = "alert_nodes_td.csv"
            result["alerts_total_count"] = len(df)

            # Select columns (prefer id, type, is_sar, score, amount, degree, risk)
            preferred_cols = ["id", "type", "is_sar", "score", "amount", "degree", "risk"]
            available_cols = [c for c in preferred_cols if c in df.columns]

            # If no preferred columns, use all columns up to 7
            if not available_cols:
                available_cols = list(df.columns)[:7]

            result["alert_columns"] = available_cols

            # Sort by is_sar (SAR first) then by score if available
            if "is_sar" in df.columns:
                df = df.sort_values(by="is_sar", ascending=False)
            if "score" in df.columns:
                df = df.sort_values(by="score", ascending=False)

            # Get top rows
            top_df = df.head(limit)
            result["top_alerts"] = top_df.fillna("").to_dict(orient="records")

        except Exception as e:
            logger.warning(f"Failed to load alert data: {e}")

        return result

    def create_run_bundle(self) -> Optional[Path]:
        """
        Create a run bundle zip file containing key artifacts.

        Bundle includes:
        - metrics/metrics.json
        - artifact_index.json
        - report/report.html
        - data/alert_nodes_td.csv (if exists)
        - Key plots (if exist)
        - logs/*.log (optional)

        Returns:
            Path to the created zip file, or None if failed
        """
        bundle_path = self.report_dir / "run_bundle.zip"

        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Required files
                required = [
                    ("metrics/metrics.json", self.artifacts_dir / "metrics" / "metrics.json"),
                    ("artifact_index.json", self.artifacts_dir / "artifact_index.json"),
                    ("report/report.html", self.report_dir / "report.html"),
                ]

                for arc_name, file_path in required:
                    if file_path.exists():
                        zf.write(file_path, arc_name)

                # Optional data files
                optional_data = [
                    ("data/alert_nodes_td.csv", self.artifacts_dir / "data" / "alert_nodes_td.csv"),
                ]

                for arc_name, file_path in optional_data:
                    if file_path.exists():
                        zf.write(file_path, arc_name)

                # Key plots
                key_plot_names = [
                    "dashboard_executive.png",
                    "anomaly_distribution.png",
                    "top_anomalies.png",
                    "top_suspicious_by_volume.png",
                ]

                for plot_name in key_plot_names:
                    plot_path = self.plots_dir / plot_name
                    if plot_path.exists():
                        zf.write(plot_path, f"plots/{plot_name}")

                # Include logs
                logs_dir = self.artifacts_dir / "logs"
                if logs_dir.exists():
                    for log_file in logs_dir.glob("*.log"):
                        zf.write(log_file, f"logs/{log_file.name}")

            logger.info(f"Run bundle created at: {bundle_path}")
            return bundle_path

        except Exception as e:
            logger.error(f"Failed to create run bundle: {e}")
            return None

    def generate(self) -> Path:
        """
        Generate the HTML report.

        Returns:
            Path to the generated report file
        """
        logger.info(f"Generating report for run {self.run_id}")

        # Ensure report directory exists
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # Load template
        template = self.jinja_env.get_template("report.html.j2")

        # Load alert data
        alert_data = self._load_alert_data(limit=50)

        # Prepare template context
        context = {
            "run_id": self.run_id,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "status": "Completed" if not self.results.get("error") else "Failed",

            # Metrics
            "total_nodes": self.results.get("total_nodes"),
            "total_transactions": self.results.get("total_transactions"),
            "anomalies_detected": self.results.get("anomalies_detected"),

            # Timing
            "started_at": self.results.get("started_at"),
            "completed_at": self.results.get("completed_at"),
            "execution_time": self._format_duration(self.results.get("execution_time_seconds")),
            "steps_completed": self.results.get("steps_completed", 0),
            "total_steps": 12,

            # Detailed sections
            "dataset_summary": self._build_dataset_summary(),
            "anomaly_results": self._build_anomaly_results(),
            "plots": self._collect_plots(),
            "key_plots": self._collect_key_plots(embed=True),
            "rules": self._load_rules(),

            # Alert data (Top Alerts table)
            "top_alerts": alert_data["top_alerts"],
            "alert_columns": alert_data["alert_columns"],
            "alerts_source_file": alert_data["alerts_source_file"],
            "alerts_total_count": alert_data["alerts_total_count"],

            # Errors
            "error_message": self.results.get("error"),
            "error_traceback": self.results.get("error_traceback"),
        }

        # Render template
        html_content = template.render(**context)

        # Write report file
        report_path = self.report_dir / "report.html"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Also save report metadata as JSON
        meta_path = self.report_dir / "report_meta.json"
        meta = {
            "run_id": self.run_id,
            "generated_at": context["generated_at"],
            "status": context["status"],
            "metrics": {
                "total_nodes": context["total_nodes"],
                "total_transactions": context["total_transactions"],
                "anomalies_detected": context["anomalies_detected"],
            },
            "plots_count": len(context["plots"]),
            "rules_count": len(context["rules"]),
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        # Create run bundle zip
        bundle_path = self.create_run_bundle()
        if bundle_path:
            meta["bundle_path"] = str(bundle_path.relative_to(self.artifacts_dir))
            # Update meta file with bundle info
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

        logger.info(f"Report generated at: {report_path}")
        return report_path
