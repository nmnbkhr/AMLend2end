"""
Celery Tasks for AML Pipeline Execution

Defines background tasks that wrap the existing pipeline execution.
The actual pipeline logic is delegated to the orchestrator module.
"""

import logging
import traceback
from datetime import datetime
from typing import Optional

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from .celery_app import celery_app
from ..db import get_sync_session, PipelineRun, StepLog, RunStatus
from ..pipeline_runner.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


class PipelineTask(Task):
    """
    Custom Celery task class with error handling and state management.
    """
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails"""
        run_id = args[0] if args else kwargs.get("run_id")
        logger.error(f"Pipeline task {task_id} failed for run {run_id}: {exc}")

        if run_id:
            session = get_sync_session()
            try:
                run = session.query(PipelineRun).filter(PipelineRun.id == run_id).first()
                if run:
                    run.status = RunStatus.FAILED
                    run.completed_at = datetime.utcnow()
                    run.error_message = str(exc)
                    run.error_traceback = traceback.format_exc()
                    session.commit()
            finally:
                session.close()

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds"""
        run_id = args[0] if args else kwargs.get("run_id")
        logger.info(f"Pipeline task {task_id} completed successfully for run {run_id}")


def update_progress(session, run_id: str, step: int, step_name: str, progress_percent: float):
    """
    Callback function to update run progress in the database.

    Called by the orchestrator after each step completion.
    """
    try:
        run = session.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if run:
            run.current_step = step
            run.current_step_name = step_name
            run.progress_percent = progress_percent
            session.commit()
            logger.debug(f"Run {run_id}: Step {step} - {step_name} ({progress_percent:.1f}%)")
    except Exception as e:
        logger.error(f"Failed to update progress for run {run_id}: {e}")
        session.rollback()


def update_step_status(session, run_id: str, step: int, step_name: str, status: str, error: Optional[str] = None):
    """
    Callback function to update step-level status in the database.

    Creates or updates StepLog entries for granular tracking.
    """
    try:
        # Find or create step log
        step_log = (
            session.query(StepLog)
            .filter(StepLog.run_id == run_id, StepLog.step_number == step)
            .first()
        )

        now = datetime.utcnow()

        if not step_log:
            step_log = StepLog(
                run_id=run_id,
                step_number=step,
                step_name=step_name,
                status=status,
                started_at=now if status == "running" else None,
            )
            session.add(step_log)
        else:
            step_log.status = status
            if status == "running" and not step_log.started_at:
                step_log.started_at = now
            elif status in ["completed", "failed", "skipped"]:
                step_log.completed_at = now

        if error:
            step_log.error_message = error

        session.commit()
        logger.debug(f"Run {run_id}: Step {step} ({step_name}) -> {status}")

    except Exception as e:
        logger.error(f"Failed to update step status for run {run_id}, step {step}: {e}")
        session.rollback()


@celery_app.task(bind=True, base=PipelineTask, name="run_pipeline")
def run_pipeline_task(self, run_id: str) -> dict:
    """
    Main task for executing the AML pipeline.

    This task:
    1. Updates run status to RUNNING
    2. Creates the artifact directory structure
    3. Executes each pipeline step via the orchestrator
    4. Updates progress after each step
    5. Generates the final report
    6. Updates run status to COMPLETED or FAILED

    Args:
        run_id: UUID of the pipeline run

    Returns:
        dict with run results summary
    """
    session = get_sync_session()
    orchestrator = None

    try:
        # Get run from database
        run = session.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            raise ValueError(f"Run not found: {run_id}")

        # Update status to RUNNING
        run.status = RunStatus.RUNNING
        run.started_at = datetime.utcnow()
        session.commit()

        logger.info(f"Starting pipeline run: {run_id}")

        # Create callback closures that capture the session
        def progress_cb(step, name, pct):
            update_progress(session, run_id, step, name, pct)

        def step_cb(step, name, status, error=None):
            update_step_status(session, run_id, step, name, status, error)

        # Initialize orchestrator with callbacks
        orchestrator = PipelineOrchestrator(
            run_id=run_id,
            params=run.params or {},
            progress_callback=progress_cb,
            step_callback=step_cb,
        )

        # Update total steps based on discovered notebooks
        run.total_steps = orchestrator.total_steps
        session.commit()

        # Execute the pipeline
        result = orchestrator.run()

        # Update run with results
        run = session.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.utcnow()
        run.current_step = run.total_steps
        run.current_step_name = "Completed"
        run.progress_percent = 100.0

        # Store result metrics
        run.total_nodes = result.get("total_nodes")
        run.total_transactions = result.get("total_transactions")
        run.anomalies_detected = result.get("anomalies_detected")

        session.commit()

        logger.info(f"Pipeline run completed: {run_id}")

        return {
            "run_id": run_id,
            "status": "completed",
            "results": result,
        }

    except SoftTimeLimitExceeded:
        logger.error(f"Pipeline run {run_id} exceeded time limit")
        run = session.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if run:
            run.status = RunStatus.FAILED
            run.completed_at = datetime.utcnow()
            run.error_message = "Task exceeded time limit"
            session.commit()
        raise

    except Exception as e:
        logger.error(f"Pipeline run {run_id} failed: {e}")
        logger.error(traceback.format_exc())

        run = session.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if run:
            run.status = RunStatus.FAILED
            run.completed_at = datetime.utcnow()
            run.error_message = str(e)
            run.error_traceback = traceback.format_exc()
            session.commit()
        raise

    finally:
        session.close()
        if orchestrator:
            orchestrator.cleanup()


@celery_app.task(bind=True, name="cleanup_old_runs")
def cleanup_old_runs(self, days_old: int = 30) -> dict:
    """
    Maintenance task to clean up old runs and artifacts.

    Can be scheduled to run periodically via Celery beat.
    """
    import shutil
    from pathlib import Path
    from datetime import timedelta

    session = get_sync_session()
    cleaned_count = 0

    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        old_runs = (
            session.query(PipelineRun)
            .filter(PipelineRun.created_at < cutoff_date)
            .filter(PipelineRun.status.in_([RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]))
            .all()
        )

        artifacts_root = Path(__file__).parent.parent.parent / "artifacts" / "runs"

        for run in old_runs:
            # Delete artifacts
            artifact_dir = artifacts_root / run.id
            if artifact_dir.exists():
                shutil.rmtree(artifact_dir)
                logger.info(f"Deleted artifacts for run {run.id}")

            # Delete step logs
            session.query(StepLog).filter(StepLog.run_id == run.id).delete()

            # Delete run record
            session.delete(run)
            cleaned_count += 1

        session.commit()
        logger.info(f"Cleaned up {cleaned_count} old runs")

        return {"cleaned_runs": cleaned_count}

    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


@celery_app.task(bind=True, name="rebuild_artifact_index")
def rebuild_artifact_index(self, run_id: str) -> dict:
    """
    Rebuild the artifact index for a specific run.

    Useful if artifacts were modified manually or index is corrupted.
    """
    from pathlib import Path
    from ..pipeline_runner.artifacts_index import ArtifactIndexer

    try:
        artifacts_root = Path(__file__).parent.parent.parent / "artifacts" / "runs"
        artifacts_dir = artifacts_root / run_id

        if not artifacts_dir.exists():
            return {"status": "error", "message": f"Artifacts directory not found: {run_id}"}

        indexer = ArtifactIndexer(artifacts_dir)
        index = indexer.build_index()

        return {
            "status": "success",
            "run_id": run_id,
            "summary": index.get("summary", {}),
        }

    except Exception as e:
        logger.error(f"Failed to rebuild artifact index for run {run_id}: {e}")
        return {"status": "error", "message": str(e)}
