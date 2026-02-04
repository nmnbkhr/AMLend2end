"""
Pipeline Status API Routes

Endpoints for checking pipeline run status and step-level progress.
"""

import logging
import asyncio
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...db import get_db, PipelineRun, StepLog, RunStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/status", tags=["status"])


# Response Models
class StepStatus(BaseModel):
    """Status of an individual pipeline step"""
    step_number: int
    step_name: str
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    metrics: dict


class RunStatusDetail(BaseModel):
    """Detailed status of a pipeline run including step-level info"""
    run_id: str
    status: str
    current_step: int
    total_steps: int
    current_step_name: str
    progress_percent: float
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
    steps: List[StepStatus]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    celery: str


# Pipeline step definitions (12 steps from the existing notebooks)
PIPELINE_STEPS = [
    {"number": 1, "name": "Create Feature Groups", "notebook": "1_create_feature_groups.ipynb"},
    {"number": 2, "name": "Prepare Training Dataset", "notebook": "2_prep_training_dataset_for_embeddings.ipynb"},
    {"number": 3, "name": "Node Embeddings HP Tuning", "notebook": "3_maggy_node_embeddings.ipynb"},
    {"number": 4, "name": "Compute Node Embeddings", "notebook": "4_compute_node_embeddings.ipynb"},
    {"number": 5, "name": "Create Embeddings Feature Group", "notebook": "5_predict_and_create_node_embeddings_fg.ipynb"},
    {"number": 6, "name": "Create Anomaly Detection Dataset", "notebook": "6_create_anomaly_detection_td.ipynb"},
    {"number": 7, "name": "Autoencoder HP Tuning", "notebook": "7_maggy_adversarial_aml.ipynb"},
    {"number": 8, "name": "Train Anomaly Detection Model", "notebook": "8_train_adversarial_aml.ipynb"},
    {"number": 9, "name": "Model Inference Testing", "notebook": "9_aml_model_server.ipynb"},
    {"number": 10, "name": "Visualize Results", "notebook": "10_visualize_results.ipynb"},
    {"number": 11, "name": "Analytical Dashboard", "notebook": "11_analytical_dashboard.ipynb"},
    {"number": 12, "name": "Pattern Analysis", "notebook": "12_aml_pattern_analysis.ipynb"},
]


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.

    Verifies database connectivity and Celery worker availability.
    """
    # Check database
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    # Check Celery (run in thread pool since inspect.ping() is synchronous and slow)
    celery_status = "unknown"
    try:
        def check_celery():
            from ...workers.celery_app import celery_app
            inspect = celery_app.control.inspect()
            return inspect.ping()

        ping_response = await asyncio.wait_for(
            asyncio.to_thread(check_celery),
            timeout=5.0  # 5 second timeout
        )
        if ping_response:
            celery_status = "healthy"
        else:
            celery_status = "no_workers"
    except asyncio.TimeoutError:
        logger.warning("Celery health check timed out")
        celery_status = "timeout"
    except Exception as e:
        logger.warning(f"Celery health check failed: {e}")
        celery_status = "unhealthy"

    overall = "healthy" if db_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        celery=celery_status,
    )


@router.get("/steps")
async def get_pipeline_steps():
    """
    Get the list of all pipeline steps.

    Returns the step definitions without run-specific status.
    """
    return {"steps": PIPELINE_STEPS, "total_steps": len(PIPELINE_STEPS)}


@router.get("/{run_id}", response_model=RunStatusDetail)
async def get_run_status(run_id: str, db: Session = Depends(get_db)):
    """
    Get detailed status of a specific run.

    Includes step-level progress information.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Get step logs for this run
    step_logs = (
        db.query(StepLog)
        .filter(StepLog.run_id == run_id)
        .order_by(StepLog.step_number)
        .all()
    )

    # Build step status list, merging with step definitions
    steps = []
    logged_steps = {log.step_number: log for log in step_logs}

    for step_def in PIPELINE_STEPS:
        step_num = step_def["number"]
        if step_num in logged_steps:
            log = logged_steps[step_num]
            steps.append(StepStatus(
                step_number=step_num,
                step_name=step_def["name"],
                status=log.status,
                started_at=log.started_at.isoformat() if log.started_at else None,
                completed_at=log.completed_at.isoformat() if log.completed_at else None,
                metrics=log.metrics or {},
            ))
        else:
            # Step not yet logged
            status = "pending"
            if run.current_step > step_num:
                status = "completed"  # Assume completed if we're past it
            elif run.current_step == step_num and run.status == RunStatus.RUNNING:
                status = "running"

            steps.append(StepStatus(
                step_number=step_num,
                step_name=step_def["name"],
                status=status,
                started_at=None,
                completed_at=None,
                metrics={},
            ))

    return RunStatusDetail(
        run_id=run.id,
        status=run.status.value if run.status else "unknown",
        current_step=run.current_step,
        total_steps=run.total_steps,
        current_step_name=run.current_step_name,
        progress_percent=run.progress_percent,
        created_at=run.created_at.isoformat() if run.created_at else None,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        error_message=run.error_message,
        steps=steps,
    )


@router.get("/{run_id}/logs")
async def get_run_logs(
    run_id: str,
    step: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Get execution logs for a run.

    Optionally filter by step number.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    query = db.query(StepLog).filter(StepLog.run_id == run_id)

    if step is not None:
        query = query.filter(StepLog.step_number == step)

    logs = query.order_by(StepLog.step_number).all()

    return {
        "run_id": run_id,
        "logs": [log.to_dict() for log in logs],
    }
