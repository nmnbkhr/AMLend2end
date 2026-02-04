"""
Path Utilities for AML Pipeline

Provides robust absolute path handling that works regardless of where
the process is launched from. Includes path traversal protection for
artifact downloads.
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Cache for repo root to avoid repeated lookups
_REPO_ROOT_CACHE: Optional[Path] = None


def get_repo_root() -> Path:
    """
    Get the repository root directory.

    Resolution order:
    1. Git root (via `git rev-parse --show-toplevel`)
    2. Environment variable REPO_ROOT if set
    3. Traverse from this file's location to find a known marker

    Returns:
        Absolute path to the repository root.

    Raises:
        RuntimeError: If the repo root cannot be determined.
    """
    global _REPO_ROOT_CACHE

    if _REPO_ROOT_CACHE is not None:
        return _REPO_ROOT_CACHE

    # 1. Try git
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_root = Path(result.stdout.strip()).resolve()
            if git_root.exists():
                _REPO_ROOT_CACHE = git_root
                logger.debug(f"Repo root from git: {git_root}")
                return git_root
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"Git root detection failed: {e}")

    # 2. Try environment variable
    env_root = os.environ.get("REPO_ROOT")
    if env_root:
        env_path = Path(env_root).resolve()
        if env_path.exists():
            _REPO_ROOT_CACHE = env_path
            logger.debug(f"Repo root from REPO_ROOT env: {env_path}")
            return env_path

    # 3. Traverse from this file's location
    # This file is at: <repo_root>/app/utils/paths.py
    current = Path(__file__).resolve()
    for _ in range(10):  # Max 10 levels up
        current = current.parent
        # Check for known markers
        if (current / "app" / "__init__.py").exists() and (current / "notebooks").exists():
            _REPO_ROOT_CACHE = current
            logger.debug(f"Repo root from traversal: {current}")
            return current
        if (current / "setup.py").exists() or (current / "pyproject.toml").exists():
            _REPO_ROOT_CACHE = current
            logger.debug(f"Repo root from setup marker: {current}")
            return current

    # 4. Fallback: assume 3 levels up from this file
    fallback = Path(__file__).resolve().parent.parent.parent
    logger.warning(f"Using fallback repo root: {fallback}")
    _REPO_ROOT_CACHE = fallback
    return fallback


def get_artifacts_root() -> Path:
    """
    Get the artifacts root directory.

    Default: <repo_root>/artifacts/runs

    Can be overridden via ARTIFACTS_ROOT environment variable.

    Returns:
        Absolute path to the artifacts root directory.
    """
    # Check environment override
    env_artifacts = os.environ.get("ARTIFACTS_ROOT")
    if env_artifacts:
        return Path(env_artifacts).resolve()

    return get_repo_root() / "artifacts" / "runs"


def get_run_dir(run_id: str) -> Path:
    """
    Get the absolute path to a run's artifact directory.

    Args:
        run_id: The run identifier (UUID).

    Returns:
        Absolute path to the run directory.

    Raises:
        ValueError: If run_id contains invalid characters.
    """
    # Basic validation of run_id
    if not run_id or not _is_valid_run_id(run_id):
        raise ValueError(f"Invalid run_id: {run_id}")

    return get_artifacts_root() / run_id


def _is_valid_run_id(run_id: str) -> bool:
    """
    Validate that a run_id is safe (UUID format or similar).

    Args:
        run_id: The run identifier to validate.

    Returns:
        True if valid, False otherwise.
    """
    # Allow alphanumeric and hyphens (UUID format)
    import re
    return bool(re.match(r"^[a-zA-Z0-9\-]+$", run_id))


def safe_join_run(run_id: str, relative_path: str) -> Path:
    """
    Safely join a relative path to a run directory.

    Prevents path traversal attacks (e.g., "../../../etc/passwd").

    Args:
        run_id: The run identifier.
        relative_path: The relative path within the run directory.

    Returns:
        Absolute path that is guaranteed to be within the run directory.

    Raises:
        ValueError: If the path would escape the run directory.
    """
    run_dir = get_run_dir(run_id)

    # Normalize the relative path (remove leading slashes, handle .. etc)
    # First strip any leading slashes
    clean_path = relative_path.lstrip("/\\")

    # Join and resolve
    full_path = (run_dir / clean_path).resolve()

    # Security check: ensure the resolved path is within run_dir
    try:
        full_path.relative_to(run_dir)
    except ValueError:
        raise ValueError(
            f"Path traversal detected: '{relative_path}' escapes run directory"
        )

    return full_path


def rel_to_run(run_id: str, abs_path: Union[str, Path]) -> str:
    """
    Convert an absolute path to a path relative to the run directory.

    Useful for displaying paths in the UI.

    Args:
        run_id: The run identifier.
        abs_path: The absolute path to convert.

    Returns:
        Relative path string, or the original path if conversion fails.
    """
    run_dir = get_run_dir(run_id)
    abs_path = Path(abs_path).resolve()

    try:
        return str(abs_path.relative_to(run_dir))
    except ValueError:
        # Path is not within run_dir, try relative to artifacts root
        try:
            return str(abs_path.relative_to(get_artifacts_root()))
        except ValueError:
            # Return basename as fallback
            return abs_path.name


def get_data_dir(run_id: str) -> Path:
    """
    Get the data directory for a run.

    Args:
        run_id: The run identifier.

    Returns:
        Absolute path to the run's data directory.
    """
    return get_run_dir(run_id) / "data"


def get_plots_dir(run_id: str) -> Path:
    """
    Get the plots directory for a run.

    Args:
        run_id: The run identifier.

    Returns:
        Absolute path to the run's plots directory.
    """
    return get_run_dir(run_id) / "plots"


def get_models_dir(run_id: str) -> Path:
    """
    Get the models directory for a run.

    Args:
        run_id: The run identifier.

    Returns:
        Absolute path to the run's models directory.
    """
    return get_run_dir(run_id) / "models"


def get_logs_dir(run_id: str) -> Path:
    """
    Get the logs directory for a run.

    Args:
        run_id: The run identifier.

    Returns:
        Absolute path to the run's logs directory.
    """
    return get_run_dir(run_id) / "logs"


def get_metrics_file(run_id: str) -> Path:
    """
    Get the metrics.json file path for a run.

    Args:
        run_id: The run identifier.

    Returns:
        Absolute path to the run's metrics.json file.
    """
    return get_run_dir(run_id) / "metrics" / "metrics.json"


def get_report_dir(run_id: str) -> Path:
    """
    Get the report directory for a run.

    Args:
        run_id: The run identifier.

    Returns:
        Absolute path to the run's report directory.
    """
    return get_run_dir(run_id) / "report"


def resolve_artifact_path(run_id: str, artifact_name: str, subdirs: list = None) -> Optional[Path]:
    """
    Resolve an artifact path by searching in common subdirectories.

    Args:
        run_id: The run identifier.
        artifact_name: The artifact filename to find.
        subdirs: List of subdirectories to search (default: ["data", "output"]).

    Returns:
        Absolute path to the artifact if found, None otherwise.
    """
    if subdirs is None:
        subdirs = ["data", "output", ""]

    run_dir = get_run_dir(run_id)

    for subdir in subdirs:
        if subdir:
            path = run_dir / subdir / artifact_name
        else:
            path = run_dir / artifact_name

        if path.exists():
            return path.resolve()

    return None


def debug_paths(run_id: str) -> dict:
    """
    Get debug information about resolved paths for a run.

    Useful for troubleshooting path issues.

    Args:
        run_id: The run identifier.

    Returns:
        Dictionary with path information.
    """
    run_dir = get_run_dir(run_id)

    paths_info = {
        "repo_root": str(get_repo_root()),
        "artifacts_root": str(get_artifacts_root()),
        "run_dir": str(run_dir),
        "run_dir_exists": run_dir.exists(),
        "data_dir": str(get_data_dir(run_id)),
        "data_dir_exists": get_data_dir(run_id).exists(),
        "files": {},
    }

    # Check common files
    common_files = [
        ("node_td.csv", "data"),
        ("edges_td.csv", "data"),
        ("alert_nodes_td.csv", "data"),
        ("node_embeddings_fg.parquet", "data"),
        ("metrics.json", "metrics"),
    ]

    for filename, subdir in common_files:
        file_path = run_dir / subdir / filename
        paths_info["files"][filename] = {
            "path": str(file_path),
            "exists": file_path.exists(),
        }

    return paths_info


# Convenience function to clear cache (useful for testing)
def clear_cache():
    """Clear the cached repo root."""
    global _REPO_ROOT_CACHE
    _REPO_ROOT_CACHE = None
