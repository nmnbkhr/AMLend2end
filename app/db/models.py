"""
SQLite Database Models for AML Pipeline Run Tracking

This module defines the SQLAlchemy ORM models for storing pipeline run metadata,
status updates, and artifact references.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import Column, String, DateTime, Text, Enum, Integer, Float, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class RunStatus(str, PyEnum):
    """Enumeration of possible run statuses"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineRun(Base):
    """
    Model representing a single pipeline run.

    Stores metadata about the run including status, timing, parameters,
    and error information if applicable.
    """
    __tablename__ = "pipeline_runs"

    # Primary identifier
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Status tracking
    status = Column(Enum(RunStatus), default=RunStatus.PENDING, nullable=False)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=12)  # 12 notebooks in the pipeline
    current_step_name = Column(String(255), default="Initializing")
    progress_percent = Column(Float, default=0.0)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Parameters (JSON serialized)
    params = Column(JSON, default=dict)

    # Results summary (populated after completion)
    total_nodes = Column(Integer, nullable=True)
    total_transactions = Column(Integer, nullable=True)
    anomalies_detected = Column(Integer, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)

    # Celery task ID for tracking
    celery_task_id = Column(String(255), nullable=True)

    # Artifact paths (relative to artifacts/runs/<run_id>/)
    artifact_path = Column(String(512), nullable=True)

    def __repr__(self):
        return f"<PipelineRun(id={self.id}, status={self.status}, progress={self.progress_percent}%)>"

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "status": self.status.value if self.status else None,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "current_step_name": self.current_step_name,
            "progress_percent": self.progress_percent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "params": self.params,
            "total_nodes": self.total_nodes,
            "total_transactions": self.total_transactions,
            "anomalies_detected": self.anomalies_detected,
            "error_message": self.error_message,
            "celery_task_id": self.celery_task_id,
            "artifact_path": self.artifact_path,
        }


class StepLog(Base):
    """
    Model for logging individual pipeline step execution details.

    Provides granular tracking of each notebook/step in the pipeline.
    """
    __tablename__ = "step_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, index=True)

    step_number = Column(Integer, nullable=False)
    step_name = Column(String(255), nullable=False)

    status = Column(String(50), default="pending")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Step outputs/logs
    log_output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Metrics from this step (JSON)
    metrics = Column(JSON, default=dict)

    def __repr__(self):
        return f"<StepLog(run_id={self.run_id}, step={self.step_number}, status={self.status})>"

    def to_dict(self) -> dict:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "step_number": self.step_number,
            "step_name": self.step_name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "log_output": self.log_output,
            "error_message": self.error_message,
            "metrics": self.metrics,
        }
