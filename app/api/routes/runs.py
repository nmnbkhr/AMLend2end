"""
Pipeline Runs API Routes

Endpoints for creating, listing, and managing pipeline runs.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from datetime import datetime, timezone

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


def _resolve_artifact_dir(run: PipelineRun) -> Path:
    """
    Resolve the artifact directory for a run using the DB artifact_path.

    For SAML-D runs, artifact_path is an absolute path.
    For demo-data runs, it's a relative path resolved against PROJECT_ROOT.
    Falls back to get_run_dir() if artifact_path is not set.
    """
    if run.artifact_path:
        p = Path(run.artifact_path)
        if p.is_absolute():
            return p
        return (PROJECT_ROOT / p).resolve()
    return get_run_dir(run.id)


# Request/Response Models
class RunParams(BaseModel):
    """Parameters for starting a pipeline run"""
    profile: str = Field(default="standard", description="Run profile: quick, standard, heavy")
    data_source: str = Field(default="demo-data", description="Data source: demo-data or saml-d")
    data_path: Optional[str] = Field(default=None, description="Custom data path override")
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
def get_run_profiles():
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
def create_run(
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

    # Resolve artifact path based on data source
    if params.data_source == "saml-d":
        artifact_path = f"/mnt/e/xx/saml-d/artifacts/runs/{run_id}"
    else:
        artifact_path = f"artifacts/runs/{run_id}"

    # Create run record
    run = PipelineRun(
        id=run_id,
        status=RunStatus.PENDING,
        params=params.model_dump(),
        created_at=datetime.utcnow(),
        artifact_path=artifact_path,
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
def list_runs(
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
def get_run(run_id: str, db: Session = Depends(get_db)):
    """
    Get details of a specific pipeline run.

    Returns the current status, progress, and any results/errors.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    return RunResponse(**run.to_dict())


@router.get("/{run_id}/metrics")
def get_run_metrics(run_id: str, db: Session = Depends(get_db)):
    """
    Get metrics for a specific run.

    Returns the dashboard data contract with dataset, training, and anomaly metrics.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifacts_dir = _resolve_artifact_dir(run)
    metrics_file = artifacts_dir / "metrics" / "metrics.json"

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
def get_artifact_index(run_id: str, db: Session = Depends(get_db)):
    """
    Get the artifact index for a run.

    Returns categorized list of all artifacts with metadata.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifacts_dir = _resolve_artifact_dir(run)
    index_file = artifacts_dir / "artifact_index.json"

    if index_file.exists():
        import json
        with open(index_file) as f:
            return json.load(f)
    else:
        # Try to build index on the fly
        try:
            from ...pipeline_runner.artifacts_index import ArtifactIndexer
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
def get_run_paths(run_id: str, db: Session = Depends(get_db)):
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

    artifacts_dir = _resolve_artifact_dir(run)
    metrics_file = artifacts_dir / "metrics" / "metrics.json"

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
def cancel_run(run_id: str, db: Session = Depends(get_db)):
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
def delete_run(run_id: str, db: Session = Depends(get_db)):
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


# --- Risk Queue Endpoints ---


@router.get("/{run_id}/risk-summary")
def get_risk_summary(run_id: str, db: Session = Depends(get_db)):
    """Return the queue_summary.json for a completed run."""
    import json as _json

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    summary_path = artifact_dir / "queues" / "queue_summary.json"

    if not summary_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Risk queue not built for this run. Re-run the pipeline or build manually.",
        )

    with open(summary_path) as f:
        summary = _json.load(f)

    return summary


@router.get("/{run_id}/risk-queue")
def get_risk_queue(
    run_id: str,
    limit: int = 200,
    offset: int = 0,
    tier: Optional[List[str]] = None,
    entity_type: Optional[List[str]] = None,
    is_sar: Optional[int] = None,
    search: Optional[str] = None,
    max_percentile: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """
    Return paginated, filtered rows from the risk queue.

    Query params:
        limit / offset — pagination
        tier — repeated param, e.g. ?tier=T1&tier=T2
        entity_type — repeated param filter
        is_sar — 0 or 1
        search — substring match on entity_id
        max_percentile — capacity filter (top X%)
    """
    import pandas as pd

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    queue_parquet = artifact_dir / "queues" / "risk_queue.parquet"
    queue_csv = artifact_dir / "queues" / "risk_queue.csv"

    if queue_parquet.exists():
        df = pd.read_parquet(queue_parquet)
    elif queue_csv.exists():
        df = pd.read_csv(queue_csv)
    else:
        raise HTTPException(
            status_code=404,
            detail="Risk queue not built for this run.",
        )

    # ── Server-side filters ──

    # Capacity filter first (top X%)
    if max_percentile is not None:
        df = df[df["percentile"] <= max_percentile]

    # Tier filter
    if tier:
        df = df[df["tier"].isin(tier)]

    # Entity type filter
    if entity_type:
        df = df[df["entity_type"].astype(str).isin(entity_type)]

    # SAR filter
    if is_sar is not None:
        df = df[df["is_sar"] == is_sar]

    # Search
    if search:
        df = df[df["entity_id"].str.contains(search, case=False, na=False)]

    total = len(df)
    rows = df.iloc[offset : offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": rows.to_dict(orient="records"),
    }


# --- Operating Point Endpoints ---


class OperatingPointPayload(BaseModel):
    """Schema for saving an operating point configuration."""
    top_percent: float = Field(..., gt=0, le=100)
    tiers: List[str] = Field(..., min_length=1)
    entity_types: List[str] = Field(default_factory=list)
    sar_filter: str = Field(default="All")
    search: str = Field(default="")


@router.post("/{run_id}/operating-point")
def save_operating_point(
    run_id: str,
    payload: OperatingPointPayload,
    db: Session = Depends(get_db),
):
    """Save an operating point configuration for a run."""
    import json as _json

    # Validate tiers
    valid_tiers = {"T1", "T2", "T3", "T4"}
    invalid = set(payload.tiers) - valid_tiers
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier values: {invalid}. Must be one of {valid_tiers}",
        )

    # Validate sar_filter
    valid_sar = {"All", "SAR Only", "Non-SAR"}
    if payload.sar_filter not in valid_sar:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sar_filter: '{payload.sar_filter}'. Must be one of {valid_sar}",
        )

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    queues_dir = artifact_dir / "queues"
    queues_dir.mkdir(parents=True, exist_ok=True)

    operating_point = {
        "run_id": run_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload.model_dump(),
    }

    op_path = queues_dir / "operating_point.json"
    with open(op_path, "w") as f:
        _json.dump(operating_point, f, indent=2)

    logger.info(f"Saved operating point for run {run_id}")
    return operating_point


@router.get("/{run_id}/operating-point")
def get_operating_point(run_id: str, db: Session = Depends(get_db)):
    """Load the saved operating point for a run."""
    import json as _json

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    op_path = artifact_dir / "queues" / "operating_point.json"

    if not op_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No operating point saved for this run.",
        )

    with open(op_path) as f:
        return _json.load(f)


# --- Case Endpoints (Phase B) ---


@router.get("/{run_id}/cases/summary")
def get_cases_summary(run_id: str, db: Session = Depends(get_db)):
    """Return case_summary.json for a completed run."""
    import json as _json

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    summary_path = artifact_dir / "cases" / "case_summary.json"

    if not summary_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Cases not built for this run.",
        )

    with open(summary_path) as f:
        return _json.load(f)


@router.get("/{run_id}/cases/{case_id}")
def get_case_detail(run_id: str, case_id: str, db: Session = Depends(get_db)):
    """Return a single case JSON by case_id."""
    import json as _json

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    case_path = artifact_dir / "cases" / f"case_{case_id}.json"

    if not case_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Case not found: {case_id}",
        )

    with open(case_path) as f:
        return _json.load(f)


@router.get("/{run_id}/cases")
def list_cases(
    run_id: str,
    tier: Optional[List[str]] = None,
    typology: Optional[List[str]] = None,
    min_entities: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Return paginated, filtered list of cases from the case index.

    Query params:
        tier — repeated param filter (e.g. ?tier=T1&tier=T2)
        typology — repeated param filter (e.g. ?typology=FAN_OUT&typology=SAR_PROXIMITY)
        min_entities — minimum entity count
        limit / offset — pagination
    """
    import pandas as _pd

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    index_path = artifact_dir / "cases" / "case_index.parquet"
    index_csv = artifact_dir / "cases" / "case_index.csv"

    if index_path.exists():
        df = _pd.read_parquet(index_path)
    elif index_csv.exists():
        df = _pd.read_csv(index_csv)
    else:
        raise HTTPException(
            status_code=404,
            detail="Cases not built for this run.",
        )

    # Filters
    if tier:
        df = df[df["tier"].isin(tier)]

    if typology:
        mask = df["typologies"].apply(
            lambda t: any(typ in str(t) for typ in typology)
        )
        df = df[mask]

    if min_entities is not None:
        df = df[df["entity_count"] >= min_entities]

    total = len(df)
    rows = df.iloc[offset: offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "cases": rows.to_dict(orient="records"),
    }


# --- AML Score Endpoints (Phase B) ---


@router.get("/{run_id}/aml-summary")
def get_aml_summary(run_id: str, db: Session = Depends(get_db)):
    """Return aml_score_summary.json for a completed run."""
    import json as _json

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    summary_path = artifact_dir / "queues" / "aml_score_summary.json"

    if not summary_path.exists():
        raise HTTPException(
            status_code=404,
            detail="AML scores not computed for this run.",
        )

    with open(summary_path) as f:
        return _json.load(f)


@router.get("/{run_id}/aml-scores")
def get_aml_scores(
    run_id: str,
    limit: int = 200,
    offset: int = 0,
    band: Optional[List[str]] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    is_sar: Optional[int] = None,
    has_laundering: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: str = "aml_score",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    """
    Return paginated, filtered AML scores.

    Query params:
        limit / offset — pagination
        band — repeated param, e.g. ?band=Critical&band=High
        min_score / max_score — score range filter
        is_sar — 0 or 1
        has_laundering — 1 to show only entities with laundering transactions
        search — substring match on entity_id
        sort_by — column to sort (default: aml_score)
        sort_order — asc or desc (default: desc)
    """
    import pandas as _pd

    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)
    scores_parquet = artifact_dir / "queues" / "party_aml_scores.parquet"
    scores_csv = artifact_dir / "queues" / "party_aml_scores.csv"

    if scores_parquet.exists():
        df = _pd.read_parquet(scores_parquet)
    elif scores_csv.exists():
        df = _pd.read_csv(scores_csv)
    else:
        raise HTTPException(
            status_code=404,
            detail="AML scores not computed for this run.",
        )

    # Filters
    if band:
        df = df[df["risk_band"].isin(band)]

    if min_score is not None:
        df = df[df["aml_score"] >= min_score]

    if max_score is not None:
        df = df[df["aml_score"] <= max_score]

    if is_sar is not None:
        df = df[df["is_sar"] == is_sar]

    if has_laundering is not None and has_laundering == 1:
        if "laundering_txn_count" in df.columns:
            df = df[df["laundering_txn_count"] > 0]

    if search:
        df = df[df["entity_id"].astype(str).str.contains(search, case=False, na=False)]

    # Sort
    if sort_by in df.columns:
        ascending = sort_order.lower() == "asc"
        df = df.sort_values(sort_by, ascending=ascending)

    total = len(df)
    rows = df.iloc[offset: offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": rows.to_dict(orient="records"),
    }


@router.post("/{run_id}/aml-scores/compute")
def compute_aml_scores_endpoint(
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Compute (or recompute) AML scores for a completed run.

    This runs the AML scoring pipeline independently of the main pipeline.
    Results are stored in ``queues/party_aml_scores.parquet``,
    ``queues/party_aml_scores.csv``, and ``queues/aml_score_summary.json``.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    artifact_dir = _resolve_artifact_dir(run)

    # Verify prerequisite: risk queue must exist
    queue_parquet = artifact_dir / "queues" / "risk_queue.parquet"
    queue_csv = artifact_dir / "queues" / "risk_queue.csv"
    if not queue_parquet.exists() and not queue_csv.exists():
        raise HTTPException(
            status_code=400,
            detail="Risk queue not found. Run the main pipeline first to produce the risk queue.",
        )

    try:
        from app.pipeline_runner.aml_scoring import run_aml_scoring
        summary = run_aml_scoring(artifact_dir)
    except Exception as exc:
        logger.error(f"AML scoring failed for run {run_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"AML scoring failed: {exc}")

    logger.info(f"AML scoring computed on-demand for run {run_id}")
    return summary


# --- Chart PNG Generation Endpoints (Phase C) ---


@router.post("/{run_id}/generate-pngs")
def trigger_png_generation(run_id: str, db: Session = Depends(get_db)):
    """
    Trigger on-demand generation of dashboard chart PNGs.

    Dispatches a Celery task to generate all chart PNGs for the specified run.
    Returns immediately with the Celery task ID for progress tracking.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    if run.status != RunStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate PNGs for run with status: {run.status.value}. Must be completed.",
        )

    try:
        from ...workers.tasks import generate_chart_pngs_task

        task = generate_chart_pngs_task.delay(run_id)

        return {
            "message": f"PNG generation started for run {run_id}",
            "celery_task_id": task.id,
            "status": "queued",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue PNG generation: {str(e)}",
        )


@router.get("/{run_id}/generate-pngs/{task_id}")
def get_png_generation_status(run_id: str, task_id: str):
    """
    Check the status of a PNG generation task.

    Returns current progress including chart name being generated.
    """
    from ...workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)

    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.state == "PROGRESS":
        response["progress"] = result.info
    elif result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)

    return response
