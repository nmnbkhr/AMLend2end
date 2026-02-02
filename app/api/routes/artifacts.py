"""
Artifacts API Routes

Endpoints for accessing pipeline run artifacts (data, models, plots, reports).
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...db import get_db, PipelineRun
from ...utils.paths import (
    get_repo_root,
    get_artifacts_root,
    get_run_dir,
    safe_join_run,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

# Base paths for artifacts (using path utilities)
PROJECT_ROOT = get_repo_root()
ARTIFACTS_ROOT = get_artifacts_root()


class ArtifactInfo(BaseModel):
    """Information about an artifact file"""
    name: str
    path: str
    size_bytes: int
    type: str


class ArtifactListResponse(BaseModel):
    """Response for listing artifacts"""
    run_id: str
    artifacts: List[ArtifactInfo]
    total_count: int


def get_artifact_type(filename: str) -> str:
    """Determine artifact type from filename extension"""
    ext = Path(filename).suffix.lower()
    type_map = {
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".svg": "image",
        ".gif": "image",
        ".csv": "data",
        ".parquet": "data",
        ".npy": "data",
        ".json": "config",
        ".keras": "model",
        ".h5": "model",
        ".pt": "model",
        ".pth": "model",
        ".pkl": "model",
        ".onnx": "model",
        ".html": "report",
        ".pdf": "report",
        ".ipynb": "notebook",
        ".log": "log",
    }
    return type_map.get(ext, "other")


@router.get("/{run_id}", response_model=ArtifactListResponse)
async def list_artifacts(
    run_id: str,
    type_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    List all artifacts for a pipeline run.

    Optionally filter by artifact type: image, data, model, report, config, notebook, log, other
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        artifact_dir = get_run_dir(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")

    if not artifact_dir.exists():
        return ArtifactListResponse(run_id=run_id, artifacts=[], total_count=0)

    artifacts = []

    for root, dirs, files in os.walk(artifact_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for filename in files:
            if filename.startswith("."):
                continue

            filepath = Path(root) / filename
            artifact_type = get_artifact_type(filename)

            if type_filter and artifact_type != type_filter:
                continue

            relative_path = filepath.relative_to(artifact_dir)

            artifacts.append(ArtifactInfo(
                name=filename,
                path=str(relative_path),
                size_bytes=filepath.stat().st_size,
                type=artifact_type,
            ))

    artifacts.sort(key=lambda x: x.path)

    return ArtifactListResponse(
        run_id=run_id,
        artifacts=artifacts,
        total_count=len(artifacts),
    )


@router.get("/{run_id}/file/{file_path:path}")
async def get_artifact_file(
    run_id: str,
    file_path: str,
    db: Session = Depends(get_db),
):
    """
    Download a specific artifact file.

    The file_path is relative to the run's artifact directory.
    Uses safe_join_run to prevent path traversal attacks.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Use safe_join_run for path traversal protection
    try:
        full_path = safe_join_run(run_id, file_path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=f"Access denied: {e}")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {file_path}")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {file_path}")

    return FileResponse(full_path, filename=full_path.name)


@router.get("/{run_id}/report")
async def get_report(
    run_id: str,
    format: str = "html",
    db: Session = Depends(get_db),
):
    """
    Get the generated report for a run.

    Supports format: html (default), json (metadata only)
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        artifact_dir = get_run_dir(run_id) / "report"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")

    if format == "json":
        report_meta = artifact_dir / "report_meta.json"
        if report_meta.exists():
            with open(report_meta) as f:
                return JSONResponse(content=json.load(f))
        else:
            return JSONResponse(content={
                "run_id": run_id,
                "status": "report_not_generated",
                "message": "Report has not been generated for this run",
            })

    elif format == "html":
        report_file = artifact_dir / "report.html"
        if report_file.exists():
            return FileResponse(report_file, media_type="text/html", filename=f"aml_report_{run_id}.html")
        else:
            raise HTTPException(status_code=404, detail="HTML report not found")

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@router.get("/{run_id}/plots")
async def list_plots(run_id: str, db: Session = Depends(get_db)):
    """
    List all plot/visualization files for a run.

    Returns images from both plots/ directory and any PNG files in artifacts.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        artifact_dir = get_run_dir(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")

    plots = []

    # Check plots directory
    plots_dir = artifact_dir / "plots"
    if plots_dir.exists():
        for ext in ["*.png", "*.jpg", "*.svg"]:
            for filepath in plots_dir.glob(ext):
                plots.append({
                    "name": filepath.name,
                    "path": f"plots/{filepath.name}",
                    "url": f"/artifacts/{run_id}/file/plots/{filepath.name}",
                    "size_bytes": filepath.stat().st_size,
                })

    # Also check data directory for any images
    data_dir = artifact_dir / "data"
    if data_dir.exists():
        for ext in ["*.png", "*.jpg", "*.svg"]:
            for filepath in data_dir.glob(ext):
                plots.append({
                    "name": filepath.name,
                    "path": f"data/{filepath.name}",
                    "url": f"/artifacts/{run_id}/file/data/{filepath.name}",
                    "size_bytes": filepath.stat().st_size,
                })

    return {"run_id": run_id, "plots": plots, "total_count": len(plots)}


@router.get("/{run_id}/tables")
async def list_tables(run_id: str, db: Session = Depends(get_db)):
    """
    List all data table files for a run.

    Returns CSV and Parquet files from the data directory.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        artifact_dir = get_run_dir(run_id) / "data"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")
    tables = []

    if artifact_dir.exists():
        for ext in ["*.csv", "*.parquet"]:
            for filepath in artifact_dir.glob(ext):
                tables.append({
                    "name": filepath.name,
                    "path": f"data/{filepath.name}",
                    "url": f"/artifacts/{run_id}/file/data/{filepath.name}",
                    "size_bytes": filepath.stat().st_size,
                    "format": filepath.suffix[1:],  # Remove the dot
                })

    return {"run_id": run_id, "tables": tables, "total_count": len(tables)}


@router.get("/{run_id}/table/{table_name}")
async def get_table_data(
    run_id: str,
    table_name: str,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: Optional[str] = None,
    sort_desc: bool = False,
    db: Session = Depends(get_db),
):
    """
    Get paginated data from a table file.

    Supports CSV and Parquet files. Returns JSON data with pagination info.
    Uses safe_join_run to prevent path traversal.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        data_dir = get_run_dir(run_id) / "data"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")

    # Find the table file
    table_path = None
    for ext in [".csv", ".parquet"]:
        candidate = data_dir / f"{table_name}{ext}"
        if candidate.exists():
            table_path = candidate
            break

        # Also try with the extension already in the name
        candidate = data_dir / table_name
        if candidate.exists():
            table_path = candidate
            break

    if not table_path or not table_path.exists():
        raise HTTPException(status_code=404, detail=f"Table not found: {table_name}")

    try:
        import pandas as pd

        # Read the file
        if str(table_path).endswith(".parquet"):
            df = pd.read_parquet(table_path)
        else:
            df = pd.read_csv(table_path)

        total_rows = len(df)
        columns = list(df.columns)

        # Apply sorting
        if sort_by and sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=not sort_desc)

        # Apply pagination
        df_page = df.iloc[offset:offset + limit]

        # Convert to records (handle NaN values)
        records = df_page.fillna("").to_dict(orient="records")

        return {
            "run_id": run_id,
            "table_name": table_name,
            "columns": columns,
            "total_rows": total_rows,
            "offset": offset,
            "limit": limit,
            "data": records,
        }

    except Exception as e:
        logger.error(f"Failed to read table {table_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read table: {e}")


@router.get("/{run_id}/anomalies")
async def get_anomalies_data(
    run_id: str,
    limit: int = Query(default=50, le=500),
    min_score: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """
    Get anomaly detection results for a run.

    Returns top anomalies sorted by score, with optional score filtering.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        data_dir = get_run_dir(run_id) / "data"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")

    # Look for embeddings file with anomaly scores
    anomaly_file = None
    for candidate in ["node_embeddings_fg.parquet", "node_embeddings_fg.csv", "anomalies.csv", "predictions.csv"]:
        path = data_dir / candidate
        if path.exists():
            anomaly_file = path
            break

    if not anomaly_file:
        return {
            "run_id": run_id,
            "status": "no_data",
            "message": "No anomaly data found for this run",
            "anomalies": [],
        }

    try:
        import pandas as pd

        if str(anomaly_file).endswith(".parquet"):
            df = pd.read_parquet(anomaly_file)
        else:
            df = pd.read_csv(anomaly_file)

        # Determine score column
        score_col = None
        for col in ["anomaly_score", "score", "is_sar", "prediction"]:
            if col in df.columns:
                score_col = col
                break

        if not score_col:
            return {
                "run_id": run_id,
                "status": "no_score_column",
                "message": "No anomaly score column found",
                "columns": list(df.columns),
            }

        # Filter by minimum score if specified
        if min_score is not None:
            df = df[df[score_col] >= min_score]

        # Sort by score descending and get top results
        df_sorted = df.sort_values(by=score_col, ascending=False).head(limit)

        # Select relevant columns (skip embedding columns for response size)
        display_cols = [c for c in df_sorted.columns if not c.startswith("emb_")]
        df_display = df_sorted[display_cols]

        return {
            "run_id": run_id,
            "score_column": score_col,
            "total_records": len(df),
            "returned_count": len(df_display),
            "columns": display_cols,
            "anomalies": df_display.fillna("").to_dict(orient="records"),
        }

    except Exception as e:
        logger.error(f"Failed to read anomalies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read anomalies: {e}")


@router.get("/{run_id}/bundle")
async def get_run_bundle(run_id: str, db: Session = Depends(get_db)):
    """
    Download the run bundle zip file.

    Contains key artifacts: metrics, report, alert data, plots, and logs.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        artifacts_dir = get_run_dir(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")

    bundle_path = artifacts_dir / "report" / "run_bundle.zip"

    if not bundle_path.exists():
        # Try to create the bundle on demand
        try:
            from ...reports.generator import ReportGenerator

            # Create a minimal results dict for the generator
            results = {
                "run_id": run_id,
                "total_nodes": run.total_nodes,
                "total_transactions": run.total_transactions,
                "anomalies_detected": run.anomalies_detected,
            }

            generator = ReportGenerator(run_id, results, artifacts_dir)
            bundle_path = generator.create_run_bundle()

            if not bundle_path or not bundle_path.exists():
                raise HTTPException(status_code=404, detail="Run bundle not available and could not be created")

        except Exception as e:
            logger.error(f"Failed to create run bundle: {e}")
            raise HTTPException(status_code=404, detail="Run bundle not available")

    return FileResponse(
        bundle_path,
        media_type="application/zip",
        filename=f"aml_run_{run_id[:8]}_bundle.zip"
    )


@router.get("/{run_id}/summary")
async def get_run_summary(run_id: str, db: Session = Depends(get_db)):
    """
    Get a summary of run results and artifacts.

    Combines run metadata with artifact overview.
    """
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    try:
        artifact_dir = get_run_dir(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {e}")

    # Count artifacts by type
    artifact_counts = {"image": 0, "data": 0, "model": 0, "report": 0, "config": 0, "notebook": 0, "log": 0, "other": 0}
    total_size = 0

    if artifact_dir.exists():
        for root, dirs, files in os.walk(artifact_dir):
            for filename in files:
                filepath = Path(root) / filename
                artifact_type = get_artifact_type(filename)
                if artifact_type in artifact_counts:
                    artifact_counts[artifact_type] += 1
                else:
                    artifact_counts["other"] += 1
                total_size += filepath.stat().st_size

    # Check for metrics
    metrics = None
    metrics_file = artifact_dir / "metrics" / "metrics.json"
    if metrics_file.exists():
        with open(metrics_file) as f:
            metrics = json.load(f)

    return {
        "run_id": run_id,
        "status": run.status.value if run.status else "unknown",
        "results": {
            "total_nodes": run.total_nodes,
            "total_transactions": run.total_transactions,
            "anomalies_detected": run.anomalies_detected,
        },
        "artifacts": {
            "counts": artifact_counts,
            "total_files": sum(artifact_counts.values()),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        },
        "has_report": (artifact_dir / "report" / "report.html").exists() if artifact_dir.exists() else False,
        "has_metrics": metrics is not None,
        "metrics_summary": {
            "anomaly_rate": metrics.get("anomalies", {}).get("anomaly_rate") if metrics else None,
            "threshold": metrics.get("anomalies", {}).get("threshold") if metrics else None,
        } if metrics else None,
    }
