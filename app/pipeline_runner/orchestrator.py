"""
Pipeline Orchestrator

Executes the existing AML pipeline notebooks sequentially using papermill.
Does NOT modify pipeline logic - wraps existing notebooks for execution.

Features:
- Papermill-based execution with fallback to nbclient
- Per-step logging to files
- Progress tracking via callbacks
- Artifact collection after execution
- Configurable timeouts and parameters
"""

import os
import sys
import re
import json
import shutil
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional, Dict, Any, List, Tuple
from io import StringIO

from ..utils.paths import (
    get_repo_root,
    get_run_dir,
    get_data_dir,
    get_plots_dir,
    get_models_dir,
    get_logs_dir,
    get_report_dir,
)
from ..reports.png_styler import style_pngs

logger = logging.getLogger(__name__)

# Project root directory (resolved via utils)
PROJECT_ROOT = get_repo_root()

# Default notebook timeout in seconds (30 minutes)
DEFAULT_NOTEBOOK_TIMEOUT = 1800

# Run profiles with predefined parameters
RUN_PROFILES = {
    "quick": {
        "sample_size": 5000,
        "epochs": 2,
        "threshold": 0.99,
        "description": "Quick test run with minimal data",
    },
    "standard": {
        "sample_size": 20000,
        "epochs": 5,
        "threshold": 0.99,
        "description": "Standard run with balanced settings",
    },
    "heavy": {
        "sample_size": 100000,
        "epochs": 10,
        "threshold": 0.995,
        "description": "Heavy run - requires 12GB+ VRAM",
    },
}


def discover_notebooks(project_root: Path) -> List[Dict[str, Any]]:
    """
    Automatically discover notebooks in the project.

    Prefers numbered notebooks (1_*, 2_*, etc.) in the root directory.
    Falls back to a configurable list if discovery fails.

    Returns:
        List of step dictionaries with notebook info
    """
    notebooks = []

    # Look for numbered notebooks in root directory
    pattern = re.compile(r'^(\d+)_(.+)\.ipynb$')

    for nb_file in sorted(project_root.glob("*.ipynb")):
        match = pattern.match(nb_file.name)
        if match:
            number = int(match.group(1))
            name_part = match.group(2).replace("_", " ").title()

            # Determine if step is optional (HP tuning steps)
            is_optional = "maggy" in nb_file.name.lower() or "hp" in name_part.lower()

            notebooks.append({
                "number": number,
                "notebook": nb_file.name,
                "name": name_part,
                "optional": is_optional,
                "path": str(nb_file),
            })

    if not notebooks:
        # Fallback to hardcoded list
        logger.warning("No numbered notebooks found, using default list")
        notebooks = [
            {"number": 1, "notebook": "1_create_feature_groups.ipynb", "name": "Create Feature Groups"},
            {"number": 2, "notebook": "2_prep_training_dataset_for_embeddings.ipynb", "name": "Prepare Training Dataset"},
            {"number": 3, "notebook": "3_maggy_node_embeddings.ipynb", "name": "Node Embeddings HP Tuning", "optional": True},
            {"number": 4, "notebook": "4_compute_node_embeddings.ipynb", "name": "Compute Node Embeddings"},
            {"number": 5, "notebook": "5_predict_and_create_node_embeddings_fg.ipynb", "name": "Create Embeddings Feature Group"},
            {"number": 6, "notebook": "6_create_anomaly_detection_td.ipynb", "name": "Create Anomaly Detection Dataset"},
            {"number": 7, "notebook": "7_maggy_adversarial_aml.ipynb", "name": "Autoencoder HP Tuning", "optional": True},
            {"number": 8, "notebook": "8_train_adversarial_aml.ipynb", "name": "Train Anomaly Detection Model"},
            {"number": 9, "notebook": "9_aml_model_server.ipynb", "name": "Model Inference Testing"},
            {"number": 10, "notebook": "10_visualize_results.ipynb", "name": "Visualize Results"},
            {"number": 11, "notebook": "11_analytical_dashboard.ipynb", "name": "Analytical Dashboard"},
            {"number": 12, "notebook": "12_aml_pattern_analysis.ipynb", "name": "Pattern Analysis"},
        ]

    # Sort by number
    notebooks.sort(key=lambda x: x["number"])
    return notebooks


class NotebookExecutor:
    """
    Handles execution of individual notebooks using papermill with nbclient fallback.
    """

    def __init__(self, project_root: Path, output_dir: Path, log_dir: Path):
        self.project_root = project_root
        self.output_dir = output_dir
        self.log_dir = log_dir

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        notebook_path: Path,
        parameters: Dict[str, Any],
        timeout: int = DEFAULT_NOTEBOOK_TIMEOUT,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Execute a notebook using papermill, with nbclient fallback.

        Args:
            notebook_path: Path to the notebook
            parameters: Parameters to inject
            timeout: Execution timeout in seconds

        Returns:
            Tuple of (success, output_path, error_message)
        """
        notebook_name = notebook_path.name
        output_path = self.output_dir / notebook_name
        log_path = self.log_dir / f"{notebook_path.stem}.log"

        # Capture logs
        log_content = StringIO()

        try:
            # Try papermill first
            success, error = self._execute_with_papermill(
                notebook_path, output_path, parameters, timeout, log_content
            )

            if not success and "parameters" in str(error).lower():
                # Fallback to nbclient if papermill fails due to parameter issues
                logger.info(f"Papermill failed, falling back to nbclient for {notebook_name}")
                log_content.write(f"\n--- Falling back to nbclient ---\n")
                success, error = self._execute_with_nbclient(
                    notebook_path, output_path, timeout, log_content
                )

        except Exception as e:
            success = False
            error = str(e)
            log_content.write(f"\nExecution error: {error}\n")
            log_content.write(traceback.format_exc())

        # Write log file
        with open(log_path, "w") as f:
            f.write(log_content.getvalue())

        return success, str(output_path) if output_path.exists() else None, error if not success else None

    def _execute_with_papermill(
        self,
        notebook_path: Path,
        output_path: Path,
        parameters: Dict[str, Any],
        timeout: int,
        log_stream: StringIO,
    ) -> Tuple[bool, Optional[str]]:
        """Execute notebook using papermill."""
        try:
            import papermill as pm

            log_stream.write(f"Executing {notebook_path.name} with papermill\n")
            log_stream.write(f"Parameters: {json.dumps(parameters, indent=2)}\n")
            log_stream.write(f"Timeout: {timeout}s\n")
            log_stream.write("-" * 50 + "\n")

            # Execute with papermill
            pm.execute_notebook(
                str(notebook_path),
                str(output_path),
                parameters=parameters,
                cwd=str(self.project_root),
                kernel_name="python3",
                progress_bar=False,
                log_output=True,
                stdout_file=log_stream,
                stderr_file=log_stream,
                execution_timeout=timeout,
            )

            log_stream.write("-" * 50 + "\n")
            log_stream.write("Execution completed successfully\n")
            return True, None

        except pm.PapermillExecutionError as e:
            error_msg = f"Papermill execution error: {e}"
            log_stream.write(f"\n{error_msg}\n")
            return False, error_msg

        except Exception as e:
            error_msg = f"Papermill error: {e}"
            log_stream.write(f"\n{error_msg}\n")
            log_stream.write(traceback.format_exc())
            return False, error_msg

    def _execute_with_nbclient(
        self,
        notebook_path: Path,
        output_path: Path,
        timeout: int,
        log_stream: StringIO,
    ) -> Tuple[bool, Optional[str]]:
        """Execute notebook using nbclient (fallback)."""
        try:
            import nbformat
            from nbclient import NotebookClient
            from nbclient.exceptions import CellExecutionError

            log_stream.write(f"Executing {notebook_path.name} with nbclient\n")
            log_stream.write(f"Timeout: {timeout}s\n")
            log_stream.write("-" * 50 + "\n")

            # Read notebook
            with open(notebook_path) as f:
                nb = nbformat.read(f, as_version=4)

            # Create client and execute
            client = NotebookClient(
                nb,
                timeout=timeout,
                kernel_name="python3",
                resources={"metadata": {"path": str(self.project_root)}},
            )

            # Execute
            client.execute()

            # Save executed notebook
            with open(output_path, "w") as f:
                nbformat.write(nb, f)

            log_stream.write("-" * 50 + "\n")
            log_stream.write("Execution completed successfully\n")
            return True, None

        except CellExecutionError as e:
            error_msg = f"Cell execution error: {e}"
            log_stream.write(f"\n{error_msg}\n")

            # Still save the partially executed notebook
            try:
                with open(output_path, "w") as f:
                    nbformat.write(nb, f)
            except:
                pass

            return False, error_msg

        except Exception as e:
            error_msg = f"nbclient error: {e}"
            log_stream.write(f"\n{error_msg}\n")
            log_stream.write(traceback.format_exc())
            return False, error_msg


class PipelineOrchestrator:
    """
    Orchestrates execution of the AML pipeline notebooks.

    This class wraps the existing pipeline without modifying it.
    It provides progress tracking, logging, and artifact collection.
    """

    def __init__(
        self,
        run_id: str,
        params: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, str, float], None]] = None,
        step_callback: Optional[Callable[[int, str, str, Optional[str]], None]] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            run_id: Unique identifier for this run
            params: Optional parameters to customize the run
            progress_callback: Callback function(step, name, percent) for progress updates
            step_callback: Callback function(step, name, status, error) for step status updates
        """
        self.run_id = run_id
        self.params = params or {}
        self.progress_callback = progress_callback
        self.step_callback = step_callback

        # Setup paths using path utilities (robust absolute paths for Celery compatibility)
        self.project_root = get_repo_root()
        self.artifacts_dir = get_run_dir(run_id)
        self.data_dir = get_data_dir(run_id)
        self.models_dir = get_models_dir(run_id)
        self.plots_dir = get_plots_dir(run_id)
        self.report_dir = get_report_dir(run_id)
        self.logs_dir = get_logs_dir(run_id)
        self.notebooks_dir = self.artifacts_dir / "notebooks_executed"
        self.metrics_dir = self.artifacts_dir / "metrics"

        # Create artifact directories
        self._setup_artifact_dirs()

        # Discover notebooks
        self.pipeline_steps = discover_notebooks(self.project_root)
        self.total_steps = len(self.pipeline_steps)

        # Initialize notebook executor
        self.executor = NotebookExecutor(
            self.project_root,
            self.notebooks_dir,
            self.logs_dir,
        )

        # Extract run parameters
        self._extract_params()

        # Results accumulator
        self.results = {
            "run_id": run_id,
            "total_nodes": None,
            "total_transactions": None,
            "anomalies_detected": None,
            "steps_completed": 0,
            "steps_failed": 0,
            "step_results": {},
        }

        logger.info(f"Orchestrator initialized for run {run_id}")
        logger.info(f"Project root: {self.project_root}")
        logger.info(f"Artifacts dir: {self.artifacts_dir}")
        logger.info(f"Discovered {self.total_steps} pipeline steps")

    def _extract_params(self):
        """Extract and validate run parameters."""
        # Apply profile if specified
        profile = self.params.get("profile", "standard")
        if profile in RUN_PROFILES:
            profile_params = RUN_PROFILES[profile].copy()
            profile_params.pop("description", None)
            # Profile provides defaults, explicit params override
            for key, value in profile_params.items():
                if key not in self.params:
                    self.params[key] = value

        # Extract individual parameters with defaults
        self.sample_size = self.params.get("sample_size", 20000)
        self.epochs = self.params.get("epochs", 5)
        self.threshold = self.params.get("threshold", 0.99)
        self.notebook_timeout = self.params.get("notebook_timeout", DEFAULT_NOTEBOOK_TIMEOUT)
        self.skip_hp_tuning = self.params.get("skip_hyperparameter_tuning", True)
        self.generate_viz = self.params.get("generate_visualizations", True)
        self.generate_report = self.params.get("generate_report", True)

        # Data source configuration
        self.data_source = self.params.get("data_source", "demo-data")
        self.data_path = self.params.get("data_path")
        if not self.data_path:
            if self.data_source == "saml-d":
                self.data_path = "/mnt/e/xx/demodata"
            else:
                self.data_path = str(self.project_root / "demodata")

        logger.info(f"Run parameters: sample_size={self.sample_size}, epochs={self.epochs}, "
                    f"threshold={self.threshold}, timeout={self.notebook_timeout}s, "
                    f"data_source={self.data_source}, data_path={self.data_path}")

    def _setup_artifact_dirs(self):
        """Create the artifact directory structure for this run."""
        dirs = [
            self.data_dir,
            self.models_dir,
            self.plots_dir,
            self.report_dir,
            self.logs_dir,
            self.notebooks_dir,
            self.metrics_dir,
        ]
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created artifact directories at {self.artifacts_dir}")

    def _update_progress(self, step: int, name: str, percent: float):
        """Update progress via callback if available."""
        if self.progress_callback:
            try:
                self.progress_callback(step, name, percent)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def _update_step_status(self, step: int, name: str, status: str, error: Optional[str] = None):
        """Update step status via callback if available."""
        if self.step_callback:
            try:
                self.step_callback(step, name, status, error)
            except Exception as e:
                logger.warning(f"Step callback failed: {e}")

    def _get_notebook_parameters(self) -> Dict[str, Any]:
        """
        Get parameters to inject into notebooks via papermill.

        Returns parameters that notebooks can optionally use.
        """
        return {
            "run_id": self.run_id,
            "artifacts_dir": str(self.artifacts_dir),
            "sample_size": self.sample_size,
            "epochs": self.epochs,
            "threshold": self.threshold,
            "data_path": self.data_path,
        }

    def _execute_notebook(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single notebook step.

        Args:
            step: Step dictionary with notebook info

        Returns:
            dict with execution result
        """
        notebook_name = step["notebook"]
        step_num = step["number"]
        step_name = step["name"]

        notebook_path = self.project_root / notebook_name
        if not notebook_path.exists():
            logger.warning(f"Notebook not found: {notebook_path}")
            return {
                "status": "skipped",
                "reason": "notebook_not_found",
                "notebook": notebook_name,
            }

        logger.info(f"Executing notebook: {notebook_name}")
        start_time = datetime.utcnow()

        # Get parameters for this notebook
        parameters = self._get_notebook_parameters()

        # Execute notebook
        success, output_path, error = self.executor.execute(
            notebook_path,
            parameters,
            timeout=self.notebook_timeout,
        )

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        result = {
            "status": "completed" if success else "failed",
            "notebook": notebook_name,
            "output_path": output_path,
            "execution_time": duration,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
        }

        if error:
            result["error"] = error

        # Read log file for additional context
        log_path = self.logs_dir / f"{notebook_path.stem}.log"
        if log_path.exists():
            result["log_path"] = str(log_path)

        return result

    def _collect_outputs(self):
        """
        Collect outputs from the existing output directories.

        Copies relevant files to the run's artifact directory.
        """
        logger.info("Collecting pipeline outputs...")

        # Source directories from existing pipeline
        output_dir = self.project_root / "output"
        models_dir = self.project_root / "models"
        training_data_dir = self.project_root / "training_data"

        collected_files = {"plots": [], "data": [], "models": []}

        # Copy visualizations
        if output_dir.exists():
            for img_file in output_dir.glob("*.png"):
                dest = self.plots_dir / img_file.name
                shutil.copy2(img_file, dest)
                collected_files["plots"].append(img_file.name)
                logger.debug(f"Collected plot: {img_file.name}")

            for img_file in output_dir.glob("*.jpg"):
                dest = self.plots_dir / img_file.name
                shutil.copy2(img_file, dest)
                collected_files["plots"].append(img_file.name)

            # Copy data files
            for data_file in output_dir.glob("*.parquet"):
                dest = self.data_dir / data_file.name
                shutil.copy2(data_file, dest)
                collected_files["data"].append(data_file.name)

            for data_file in output_dir.glob("*.csv"):
                dest = self.data_dir / data_file.name
                shutil.copy2(data_file, dest)
                collected_files["data"].append(data_file.name)

            # Copy JSON files
            for json_file in output_dir.glob("*.json"):
                dest = self.data_dir / json_file.name
                shutil.copy2(json_file, dest)
                collected_files["data"].append(json_file.name)

        # Copy training data files
        if training_data_dir.exists():
            for data_file in training_data_dir.glob("*.csv"):
                dest = self.data_dir / data_file.name
                shutil.copy2(data_file, dest)
                collected_files["data"].append(data_file.name)

        # Copy model artifacts
        if models_dir.exists():
            for model_dir in models_dir.glob("gan_anomaly_*"):
                if model_dir.is_dir():
                    dest = self.models_dir / model_dir.name
                    if not dest.exists():
                        shutil.copytree(model_dir, dest)
                    collected_files["models"].append(model_dir.name)
                    logger.debug(f"Collected model: {model_dir.name}")

        logger.info(f"Output collection complete: {len(collected_files['plots'])} plots, "
                    f"{len(collected_files['data'])} data files, {len(collected_files['models'])} models")

        return collected_files

    def _parse_results(self) -> Dict[str, Any]:
        """
        Parse results from pipeline outputs to extract summary metrics.
        """
        results = {
            "total_nodes": None,
            "total_transactions": None,
            "anomalies_detected": None,
        }

        try:
            # Try to read node embeddings to get node count
            embeddings_file = self.data_dir / "node_embeddings_fg.parquet"
            if not embeddings_file.exists():
                embeddings_file = self.project_root / "output" / "node_embeddings_fg.parquet"

            if embeddings_file.exists():
                import pandas as pd
                df = pd.read_parquet(embeddings_file)
                results["total_nodes"] = len(df)

                # Count anomalies
                if "is_sar" in df.columns:
                    results["anomalies_detected"] = int(df["is_sar"].sum())
                elif "anomaly_score" in df.columns:
                    # Use threshold from model if available
                    thresholds = list(self.models_dir.glob("*/threshold.npy"))
                    if not thresholds:
                        thresholds = list(self.project_root.glob("models/gan_anomaly_*/threshold.npy"))

                    if thresholds:
                        import numpy as np
                        threshold = np.load(thresholds[0])
                        results["anomalies_detected"] = int((df["anomaly_score"] > threshold).sum())

            # Get transaction count from edges file
            edges_file = self.data_dir / "edges_td.csv"
            if not edges_file.exists():
                edges_file = self.project_root / "training_data" / "edges_td.csv"

            if edges_file.exists():
                import pandas as pd
                edges_df = pd.read_csv(edges_file)
                results["total_transactions"] = len(edges_df)

        except Exception as e:
            logger.warning(f"Failed to parse some results: {e}")

        return results

    def _build_metrics(self) -> Dict[str, Any]:
        """
        Build the metrics.json file with dashboard data contract.
        """
        from .metrics_builder import MetricsBuilder

        builder = MetricsBuilder(self.artifacts_dir, self.project_root)
        metrics = builder.build(self.results)

        # Save metrics
        metrics_path = self.metrics_dir / "metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)

        logger.info(f"Metrics saved to {metrics_path}")
        return metrics

    def _build_artifact_index(self):
        """
        Build the artifact index for dynamic UI.
        """
        from .artifacts_index import ArtifactIndexer

        indexer = ArtifactIndexer(self.artifacts_dir)
        index = indexer.build_index()

        logger.info(f"Artifact index built: {index['summary']}")
        return index

    def _style_plots(self) -> int:
        """
        Apply Bloomberg-terminal styling to generated plots.

        Creates styled versions in plots/styled/ directory.

        Returns:
            Number of styled plots created
        """
        try:
            styled_files = style_pngs(self.run_id, theme="bloomberg")
            logger.info(f"Created {len(styled_files)} styled plots")
            return len(styled_files)
        except Exception as e:
            logger.warning(f"Failed to style plots: {e}")
            return 0

    def run(self) -> Dict[str, Any]:
        """
        Execute the full pipeline.

        Returns:
            dict with run results including metrics and artifact paths
        """
        logger.info(f"Starting pipeline execution for run {self.run_id}")
        start_time = datetime.utcnow()
        self.results["started_at"] = start_time.isoformat()

        completed_steps = 0
        failed_steps = 0

        try:
            for step in self.pipeline_steps:
                step_num = step["number"]
                step_name = step["name"]
                notebook = step["notebook"]
                is_optional = step.get("optional", False)

                # Skip HP tuning steps if configured
                if is_optional and self.skip_hp_tuning and ("maggy" in notebook.lower() or "hp" in step_name.lower()):
                    logger.info(f"Skipping optional step {step_num}: {step_name}")
                    self._update_progress(step_num, f"{step_name} (skipped)", (step_num / self.total_steps) * 100)
                    self._update_step_status(step_num, step_name, "skipped")
                    self.results["step_results"][step_num] = {"status": "skipped", "reason": "optional_disabled"}
                    completed_steps += 1
                    continue

                # Skip visualization steps if not requested
                if step_num >= 10 and not self.generate_viz:
                    logger.info(f"Skipping visualization step {step_num}: {step_name}")
                    self._update_progress(step_num, f"{step_name} (skipped)", (step_num / self.total_steps) * 100)
                    self._update_step_status(step_num, step_name, "skipped")
                    self.results["step_results"][step_num] = {"status": "skipped", "reason": "visualization_disabled"}
                    completed_steps += 1
                    continue

                # Update progress to "running"
                self._update_progress(step_num, f"Running: {step_name}", ((step_num - 0.5) / self.total_steps) * 100)
                self._update_step_status(step_num, step_name, "running")

                # Execute the step
                step_result = self._execute_notebook(step)
                self.results["step_results"][step_num] = step_result

                if step_result.get("status") == "failed":
                    failed_steps += 1
                    self._update_step_status(step_num, step_name, "failed", step_result.get("error"))

                    # For non-optional steps, this is a fatal error
                    if not is_optional:
                        error_msg = f"Step {step_num} ({step_name}) failed: {step_result.get('error')}"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    else:
                        logger.warning(f"Optional step {step_num} failed, continuing...")
                else:
                    completed_steps += 1
                    self._update_step_status(step_num, step_name, "completed")

                # Update progress to "completed"
                progress_pct = (step_num / self.total_steps) * 100
                self._update_progress(step_num, step_name, progress_pct)

                logger.info(f"Completed step {step_num}/{self.total_steps}: {step_name}")

            # Collect outputs from the pipeline
            self._collect_outputs()

            # Apply Bloomberg-terminal styling to plots
            try:
                styled_count = self._style_plots()
                self.results["styled_plots_count"] = styled_count
            except Exception as e:
                logger.warning(f"Failed to style plots: {e}")
                self.results["styled_plots_count"] = 0

            # Parse results
            parsed_results = self._parse_results()
            self.results.update(parsed_results)
            self.results["steps_completed"] = completed_steps
            self.results["steps_failed"] = failed_steps

            # Build metrics for dashboard
            try:
                self._build_metrics()
            except Exception as e:
                logger.warning(f"Failed to build metrics: {e}")

            # Build artifact index (includes styled plots category)
            try:
                self._build_artifact_index()
            except Exception as e:
                logger.warning(f"Failed to build artifact index: {e}")

            # Generate report if requested
            if self.generate_report:
                self._generate_report()

            end_time = datetime.utcnow()
            self.results["completed_at"] = end_time.isoformat()
            self.results["execution_time_seconds"] = (end_time - start_time).total_seconds()

            logger.info(f"Pipeline execution completed for run {self.run_id}")
            return self.results

        except Exception as e:
            logger.error(f"Pipeline execution failed for run {self.run_id}: {e}")
            self.results["error"] = str(e)
            self.results["error_traceback"] = traceback.format_exc()
            self.results["steps_completed"] = completed_steps
            self.results["steps_failed"] = failed_steps

            # Still try to collect partial outputs and build index
            try:
                self._collect_outputs()
                self._build_artifact_index()
            except:
                pass

            raise

    def _generate_report(self):
        """
        Generate the HTML report for this run.
        """
        from ..reports.generator import ReportGenerator

        try:
            generator = ReportGenerator(
                run_id=self.run_id,
                results=self.results,
                artifacts_dir=self.artifacts_dir,
            )
            generator.generate()
            logger.info(f"Report generated for run {self.run_id}")
        except Exception as e:
            logger.error(f"Failed to generate report for run {self.run_id}: {e}")

    def cleanup(self):
        """
        Cleanup any temporary resources.
        """
        # Currently no cleanup needed, but this is a hook for future use
        pass
