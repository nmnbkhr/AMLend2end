"""
AML Pipeline Runner Application

A web-based interface for running and monitoring the AML detection pipeline.

Components:
- api: FastAPI REST API server
- workers: Celery background task workers
- pipeline_runner: Pipeline orchestration
- db: SQLite database models
- reports: HTML report generation
- ui: Streamlit user interface
"""

__version__ = "1.0.0"
__author__ = "AML Pipeline Team"
