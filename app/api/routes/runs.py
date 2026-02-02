"""
Pipeline Runs API Routes

Endpoints for creating, listing, and managing pipeline runs.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...db import get_db, PipelineRun, RunStatus
from ...pipeline_runner.orchestrator import RUN_PROFILES
from ...utils.paths import get_repo_root, get_artifacts_root, get_run_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])

# Project paths (using path utilities)
PROJECT_ROOT = get_repo_root()
ARTIFACTS_ROOT = get_artifacts_root()


# Request/Response Models
class RunParams(BaseModel):
    """Parameters for starting a pipeline run"""
    profile: str = Field(default="standard", description="Run profile: quick, standard, heavy")
    sample_size: Optional[int] = Field(default=None, description="Override sample size")
    epochs: Optional[int] = Field(default=None, description="Override epochs")
    threshold: Optional[float] = Field(default=None, description="Override anomaly threshold")
    notebook_timeout: Optional[int] = Field(default=None, description="Timeout per notebook (seconds)")
    skip_hyperparameter_tuning: bool = Field(default=True, description="Skip Maggy HP tuning")
    generate_visualizations: bool = Field(default=True, description="Generate visualizations")
    generate_report: bool = Field(default=True, description="Generate HTML report")


class RunResponse(BaseModel):
    """Response model for a pipeline run"""
    id: str
    status: str
    current_step: int
    total_steps: int
    current_step_name: str
    progress_percent: float
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    params: dict
    total_nodes: Optional[int]
    total_transactions: Optional[int]
    anomalies_detected: Optional[int]
    error_message: Optional[str]
    celery_task_id: Optional[str]
    artifact_path: Optional[str]

    class Config:
        from_attributes = True


class CreateRunResponse(BaseModel):
    """Response when creating a new run"""
    run_id: str
    message: str
    status: str


class ProfileInfo(BaseModel):
    """Information about a run profile"""
    name: str
    sample_size: int
    epochs: int
    threshold: float
    description: str


# API Endpoints
@router.get("/profiles")
async def get_run_profiles():
    """
    Get available run profiles with their configurations.

    Profiles provide preset configurations for different use cases:
    - quick: Fast testing with minimal data
    - standard: Balanced settings for typical runs
    - heavy: Full dataset processing (requires more resources)
    """
    profiles = []
    for name, config in RUN_PROFILES.items():
        profiles.append(ProfileInfo(
            name=name,
            sample_size=config["sample_size"],
            epochs=config["epochs"],
            threshold=config["threshold"],
            description=config["description"],
        ))
    return {"profiles": profiles}


@router.post("/", response_model=CreateRunResponse)
async def create_run(
    params: RunParams = RunParams(),
    db: Session = Depends(get_db),
):
    """
    Start a new pipeline run.

    Creates a new run record in the database and enqueues a Celery task
    to execute the pipeline in the background.
    """
    # Generate unique run ID
    run_id = str(uuid.uuid4())

    # Create run record
    run = PipelineRun(
        id=run_id,
        status=RunStatus.PENDING,
        params=params.model_dump(),
        created_at=datetime.utcnow(),
        artifact_path=f"artifacts/runs/{run_id}",
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    # Dispatch Celery task
    try:
        from ...workers.tasks import run_pipeline_task
        task = run_pipeline_task.delay(run_id)

        # Update run with Celery task ID
        run.celery_task_id = task.id
        db.commit()

        logger.info(f"Started pipeline run {run_id} with Celery task {task.id}")
    except Exception as e:
        logger.error(f"Failed to dispatch Celery task for run {run_id}: {e}")
        run.status = RunStatus.FAILED
        run.error_message = f"Failed to start background task: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to start pipeline: {str(e)}")

    return CreateRunResponse(
        run_id=run_id,
        message="Pipeline run started successfully",
        status=run.status.value,
    )


@router.get("/", response_model=List[RunResponse])
async def list_runs(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    List all pipeline runs.

    Supports pagination and optional status filtering.
    """
    query = db.query(PipelineRun)

    if status:
        try:
            status_enum = RunStatus(status)
            query = query.filter(PipelineRun.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    runs = (
        query
        .order_by(PipelineRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [RunResponse(**run.to_dict()) for run in runs]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific pipeline run.

    Returns the current status, progress, and any results/errors.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    return RunResponse(**run.to_dict())


@router.get("/{run_id}/metrics")
async def get_run_metrics(run_id: str, db: Session = Depends(get_db)):
    """
    Get metrics for a specific run.

    Returns the dashboard data contract with dataset, training, and anomaly metrics.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    metrics_file = ARTIFACTS_ROOT / run_id / "metrics" / "metrics.json"

    if metrics_file.exists():
        import json
        with open(metrics_file) as f:
            return json.load(f)
    else:
        return {
            "run_id": run_id,
            "status": "metrics_not_available",
            "message": "Metrics have not been generated for this run",
        }


@router.get("/{run_id}/artifact-index")
async def get_artifact_index(run_id: str, db: Session = Depends(get_db)):
    """
    Get the artifact index for a run.

    Returns categorized list of all artifacts with metadata.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    index_file = ARTIFACTS_ROOT / run_id / "artifact_index.json"

    if index_file.exists():
        import json
        with open(index_file) as f:
            return json.load(f)
    else:
        # Try to build index on the fly
        try:
            from ...pipeline_runner.artifacts_index import ArtifactIndexer
            artifacts_dir = ARTIFACTS_ROOT / run_id
            if artifacts_dir.exists():
                indexer = ArtifactIndexer(artifacts_dir)
                return indexer.build_index()
        except Exception as e:
            logger.warning(f"Failed to build artifact index: {e}")

        return {
            "run_id": run_id,
            "status": "index_not_available",
            "categories": {},
            "summary": {"total_files": 0},
        }


@router.get("/{run_id}/paths")
async def get_run_paths(run_id: str, db: Session = Depends(get_db)):
    """
    Get explicit artifact paths for a run.

    Returns paths to key artifacts extracted from metrics.json:
    - anomalies_table_path: Path to primary anomalies table
    - key_plots_paths: List of key visualization paths
    - model_path: Path to trained model directory
    - model_files: List of files in model directory
    """
    import json

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    metrics_file = ARTIFACTS_ROOT / run_id / "metrics" / "metrics.json"
    artifacts_dir = ARTIFACTS_ROOT / run_id

    paths = {
        "run_id": run_id,
        "artifacts_base": str(artifacts_dir),
        "anomalies_table_path": None,
        "key_plots_paths": [],
        "model_path": None,
        "model_files": [],
        "report_path": None,
        "bundle_path": None,
    }

    if metrics_file.exists():
        try:
            with open(metrics_file) as f:
                metrics = json.load(f)

            # Extract paths from metrics
            anomalies = metrics.get("anomalies", {})
            training = metrics.get("training", {})
            execution = metrics.get("execution", {})

            paths["anomalies_table_path"] = anomalies.get("anomalies_table_path")
            paths["key_plots_paths"] = execution.get("key_plots_paths", [])
            paths["model_path"] = training.get("model_path")
            paths["model_files"] = training.get("model_files", [])

        except Exception as e:
            logger.warning(f"Failed to read metrics for paths: {e}")

    # Check for report and bundle
    report_path = artifacts_dir / "report" / "report.html"
    if report_path.exists():
        paths["report_path"] = "report/report.html"

    bundle_path = artifacts_dir / "report" / "run_bundle.zip"
    if bundle_path.exists():
        paths["bundle_path"] = "report/run_bundle.zip"

    return paths


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: Session = Depends(get_db)):
    """
    Cancel a running pipeline.

    Only works for runs that are in PENDING or RUNNING status.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    if run.status not in [RunStatus.PENDING, RunStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel run with status: {run.status.value}"
        )

    # Revoke Celery task if we have the task ID
    if run.celery_task_id:
        try:
            from ...workers.celery_app import celery_app
            celery_app.control.revoke(run.celery_task_id, terminate=True)
            logger.info(f"Revoked Celery task {run.celery_task_id}")
        except Exception as e:
            logger.warning(f"Failed to revoke Celery task: {e}")

    run.status = RunStatus.CANCELLED
    run.completed_at = datetime.utcnow()
    db.commit()

    return {"message": f"Run {run_id} cancelled", "status": run.status.value}


@router.delete("/{run_id}")
async def delete_run(run_id: str, db: Session = Depends(get_db)):
    """
    Delete a pipeline run and its metadata.

    Note: This does not delete artifacts. Use the artifacts endpoint for that.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Don't allow deleting running tasks
    if run.status == RunStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running pipeline. Cancel it first."
        )

    db.delete(run)
    db.commit()

    return {"message": f"Run {run_id} deleted"}
