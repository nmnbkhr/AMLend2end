"""
Database Session Management

Provides SQLAlchemy session factory and database initialization utilities.
Uses SQLite for local storage of run metadata.
"""

import os
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base

# Database configuration
# Store the SQLite database in the app directory
APP_DIR = Path(__file__).parent.parent
DB_PATH = APP_DIR / "aml_pipeline.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine with SQLite-specific settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite with multiple threads
    echo=False,  # Set to True for SQL debugging
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Initialize the database by creating all tables.

    Call this on application startup to ensure the database schema exists.
    """
    Base.metadata.create_all(bind=engine)
    print(f"[DB] Database initialized at: {DB_PATH}")


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get a database session.

    Usage in FastAPI:
        @app.get("/")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for getting a database session.

    Usage:
        with get_db_session() as db:
            run = db.query(PipelineRun).first()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_sync_session() -> Session:
    """
    Get a synchronous session for use in Celery tasks.

    Remember to close the session after use:
        session = get_sync_session()
        try:
            # do work
            session.commit()
        finally:
            session.close()
    """
    return SessionLocal()
