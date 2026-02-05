"""
Artifact Indexer

Scans the run artifacts directory and builds an index of all files
for dynamic UI rendering and API access.

Uses output_map.yaml for deterministic file lookup with fallback to heuristics.
"""

import os
import json
import logging
import fnmatch
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Load output mapping configuration
OUTPUT_MAP_PATH = Path(__file__).parent / "output_map.yaml"


def load_output_map() -> Dict[str, Any]:
    """Load the output mapping configuration."""
    if OUTPUT_MAP_PATH.exists():
        try:
            with open(OUTPUT_MAP_PATH) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load output_map.yaml: {e}")
    return {}

# File type categories
FILE_CATEGORIES = {
    "plots": {
        "extensions": [".png", ".jpg", ".jpeg", ".svg", ".gif"],
        "description": "Visualization files",
    },
    "styled_plots": {
        "extensions": [".png", ".jpg", ".jpeg", ".svg", ".gif"],
        "description": "Bloomberg-styled visualization files",
        "subdirectory": "plots/styled",
    },
    "dashboard_plots": {
        "extensions": [".png", ".jpg", ".jpeg", ".svg"],
        "description": "Dashboard-generated chart files",
        "subdirectory": "plots/dashboard",
    },
    "dashboard_styled_plots": {
        "extensions": [".png", ".jpg", ".jpeg", ".svg"],
        "description": "Styled dashboard chart files",
        "subdirectory": "plots/dashboard/styled",
    },
    "tables": {
        "extensions": [".csv", ".parquet", ".xlsx", ".tsv"],
        "description": "Data tables",
    },
    "models": {
        "extensions": [".pt", ".pth", ".onnx", ".pkl", ".joblib", ".h5", ".keras", ".npy"],
        "description": "Model files",
    },
    "notebooks": {
        "extensions": [".ipynb"],
        "description": "Executed notebooks",
    },
    "reports": {
        "extensions": [".html", ".pdf", ".md"],
        "description": "Report files",
    },
    "logs": {
        "extensions": [".log", ".txt"],
        "description": "Log files",
    },
    "config": {
        "extensions": [".json", ".yaml", ".yml", ".toml"],
        "description": "Configuration files",
    },
    "queues": {
        "extensions": [".parquet", ".csv", ".json"],
        "description": "Risk queue files",
        "subdirectory": "queues",
    },
    "cases": {
        "extensions": [".parquet", ".json"],
        "description": "Investigation case files",
        "subdirectory": "cases",
    },
}


def get_file_category(filename: str, relative_path: str = "") -> str:
    """
    Determine the category of a file based on its extension and path.

    Args:
        filename: The filename to categorize
        relative_path: The relative path from artifacts root (used for styled plots detection)

    Returns:
        Category string
    """
    # Check if this is a dashboard styled plot
    if relative_path and "plots/dashboard/styled" in str(relative_path):
        return "dashboard_styled_plots"

    # Check if this is a dashboard plot
    if relative_path and "plots/dashboard" in str(relative_path):
        return "dashboard_plots"

    # Check if this is a styled plot (in plots/styled/ directory)
    if relative_path and "plots/styled" in str(relative_path):
        return "styled_plots"

    # Check if this is a queue file (in queues/ directory)
    if relative_path and "queues" in str(relative_path):
        return "queues"

    # Check if this is a case file (in cases/ directory)
    if relative_path and "cases" in str(relative_path):
        return "cases"

    ext = Path(filename).suffix.lower()
    for category, info in FILE_CATEGORIES.items():
        # Skip styled_plots here - it's detected by path above
        if category == "styled_plots":
            continue
        if ext in info["extensions"]:
            return category
    return "other"


def get_file_size_str(size_bytes: int) -> str:
    """Convert bytes to human-readable size string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


class ArtifactIndexer:
    """
    Builds an index of all artifacts in a run directory.

    The index includes:
    - File categorization (plots, tables, models, etc.)
    - File metadata (size, modification time)
    - Relative paths for API access
    - Summary statistics
    - Mapped paths from output_map.yaml
    """

    def __init__(self, artifacts_dir: Path):
        """
        Initialize the indexer.

        Args:
            artifacts_dir: Path to the run's artifacts directory (will be resolved to absolute)
        """
        self.artifacts_dir = Path(artifacts_dir).resolve()
        self.index_path = self.artifacts_dir / "artifact_index.json"
        self.output_map = load_output_map()

    def _find_by_pattern(self, pattern: str) -> Optional[Path]:
        """Find a file matching a glob pattern in the artifacts directory."""
        matches = list(self.artifacts_dir.glob(pattern))
        return matches[0] if matches else None

    def _find_mapped_file(self, map_key: str, section: str = "tables") -> Optional[Path]:
        """
        Find a file using the output mapping.

        Args:
            map_key: Key in the output map (e.g., 'anomalies_primary')
            section: Section of output_map (tables, plots, models, etc.)

        Returns:
            Path to the file if found, None otherwise
        """
        section_map = self.output_map.get(section, {})
        if map_key not in section_map:
            return None

        patterns = section_map[map_key].get("patterns", [])
        for pattern in patterns:
            found = self._find_by_pattern(pattern)
            if found:
                return found
        return None

    def get_primary_anomalies_table(self) -> Optional[Dict[str, Any]]:
        """
        Get the primary anomalies table using output mapping.

        Priority:
        1. data/alert_nodes_td.csv (from output_map)
        2. Fallback to heuristics
        """
        # Try mapped primary first
        path = self._find_mapped_file("anomalies_primary", "tables")
        if not path:
            path = self._find_mapped_file("anomalies_nodes", "tables")

        if path and path.exists():
            return self._get_file_info(path)

        # Fallback to heuristics
        return self.get_anomalies_table()

    def get_key_plots(self) -> List[Dict[str, Any]]:
        """
        Get key plots in priority order using output mapping.

        Returns plots in this order:
        1. dashboard_executive.png
        2. anomaly_distribution.png
        3. top_anomalies.png
        4. top_suspicious_by_volume.png
        5. Up to 4 more from secondary plots
        """
        key_plots = []
        plots_map = self.output_map.get("plots", {})

        # Priority plots
        priority_keys = ["executive", "anomaly_distribution", "top_anomalies", "suspicious_volume"]

        for key in priority_keys:
            if key in plots_map:
                patterns = plots_map[key].get("patterns", [])
                for pattern in patterns:
                    found = self._find_by_pattern(pattern)
                    if found:
                        key_plots.append(self._get_file_info(found))
                        break

        # Add secondary plots (up to 4 more)
        remaining_slots = 8 - len(key_plots)
        if remaining_slots > 0:
            all_plots = list(self.artifacts_dir.glob("plots/*.png"))
            added_names = {p["name"] for p in key_plots}

            for plot_path in sorted(all_plots, key=lambda p: p.name):
                if plot_path.name not in added_names:
                    key_plots.append(self._get_file_info(plot_path))
                    added_names.add(plot_path.name)
                    if len(key_plots) >= 8:
                        break

        return key_plots

    def get_model_paths(self) -> Dict[str, Optional[str]]:
        """
        Get model file paths using output mapping.

        Returns dict with keys: model, threshold, metadata
        """
        result = {"model": None, "threshold": None, "metadata": None}
        models_map = self.output_map.get("models", {})

        for key, map_key in [("model", "gan_detector"), ("threshold", "gan_threshold"), ("metadata", "gan_metadata")]:
            if map_key in models_map:
                patterns = models_map[map_key].get("patterns", [])
                for pattern in patterns:
                    found = self._find_by_pattern(pattern)
                    if found:
                        result[key] = str(found.relative_to(self.artifacts_dir))
                        break

        return result

    def _get_file_info(self, filepath: Path) -> Dict[str, Any]:
        """Get file info dictionary for a path."""
        try:
            stat = filepath.stat()
            relative_path = filepath.relative_to(self.artifacts_dir)
            return {
                "name": filepath.name,
                "path": str(relative_path),
                "full_path": str(filepath),
                "size_bytes": stat.st_size,
                "size_str": get_file_size_str(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "category": get_file_category(filepath.name, str(relative_path)),
                "directory": str(relative_path.parent) if str(relative_path.parent) != "." else "",
            }
        except Exception as e:
            logger.warning(f"Failed to get file info for {filepath}: {e}")
            return {"name": filepath.name, "path": str(filepath), "error": str(e)}

    def build_index(self) -> Dict[str, Any]:
        """
        Scan the artifacts directory and build the index.

        Returns:
            dict with categorized artifacts and summary
        """
        logger.info(f"Building artifact index for {self.artifacts_dir}")

        index = {
            "generated_at": datetime.utcnow().isoformat(),
            "artifacts_dir": str(self.artifacts_dir),
            "categories": {},
            "all_files": [],
            "summary": {
                "total_files": 0,
                "total_size_bytes": 0,
                "by_category": {},
            },
        }

        # Initialize categories
        for category in FILE_CATEGORIES:
            index["categories"][category] = []
            index["summary"]["by_category"][category] = 0

        # Scan directory recursively
        if not self.artifacts_dir.exists():
            logger.warning(f"Artifacts directory does not exist: {self.artifacts_dir}")
            self._save_index(index)
            return index

        for root, dirs, files in os.walk(self.artifacts_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for filename in files:
                if filename.startswith("."):
                    continue

                filepath = Path(root) / filename
                relative_path = filepath.relative_to(self.artifacts_dir)

                # Get file info
                try:
                    stat = filepath.stat()
                    file_info = {
                        "name": filename,
                        "path": str(relative_path),
                        "full_path": str(filepath),
                        "size_bytes": stat.st_size,
                        "size_str": get_file_size_str(stat.st_size),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "category": get_file_category(filename, str(relative_path)),
                        "directory": str(relative_path.parent) if str(relative_path.parent) != "." else "",
                    }

                    # Add to all files list
                    index["all_files"].append(file_info)

                    # Add to category
                    category = file_info["category"]
                    if category in index["categories"]:
                        index["categories"][category].append(file_info)
                    else:
                        if "other" not in index["categories"]:
                            index["categories"]["other"] = []
                        index["categories"]["other"].append(file_info)

                    # Update summary
                    index["summary"]["total_files"] += 1
                    index["summary"]["total_size_bytes"] += stat.st_size
                    if category in index["summary"]["by_category"]:
                        index["summary"]["by_category"][category] += 1
                    else:
                        index["summary"]["by_category"]["other"] = \
                            index["summary"]["by_category"].get("other", 0) + 1

                except Exception as e:
                    logger.warning(f"Failed to index file {filepath}: {e}")

        # Add human-readable total size
        index["summary"]["total_size_str"] = get_file_size_str(index["summary"]["total_size_bytes"])

        # Sort files in each category by name
        for category in index["categories"]:
            index["categories"][category].sort(key=lambda x: x["name"])

        # Add mapped paths (deterministic lookups from output_map.yaml)
        index["mapped_paths"] = self._build_mapped_paths()

        # Save index
        self._save_index(index)

        return index

    def _build_mapped_paths(self) -> Dict[str, Any]:
        """Build deterministic mapped paths from output_map.yaml."""
        mapped = {
            "anomalies_table": None,
            "key_plots": [],
            "styled_plots": [],
            "has_styled_plots": False,
            "model_paths": {},
        }

        # Primary anomalies table
        anomalies = self.get_primary_anomalies_table()
        if anomalies:
            mapped["anomalies_table"] = anomalies.get("path")

        # Key plots
        key_plots = self.get_key_plots()
        mapped["key_plots"] = [p.get("path") for p in key_plots if p.get("path")]

        # Styled plots
        if self.has_styled_plots():
            mapped["has_styled_plots"] = True
            styled = self.get_styled_plots()
            mapped["styled_plots"] = [p.get("path") for p in styled if p.get("path")]

        # Model paths
        mapped["model_paths"] = self.get_model_paths()

        return mapped

    def _save_index(self, index: Dict[str, Any]):
        """Save the index to a JSON file."""
        try:
            with open(self.index_path, "w") as f:
                json.dump(index, f, indent=2)
            logger.info(f"Artifact index saved to {self.index_path}")
        except Exception as e:
            logger.error(f"Failed to save artifact index: {e}")

    def load_index(self) -> Optional[Dict[str, Any]]:
        """Load existing index from file."""
        if self.index_path.exists():
            try:
                with open(self.index_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load artifact index: {e}")
        return None

    def get_files_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all files in a specific category."""
        index = self.load_index()
        if index and category in index.get("categories", {}):
            return index["categories"][category]
        return []

    def get_plots(self) -> List[Dict[str, Any]]:
        """Get all plot files (original, not styled)."""
        return self.get_files_by_category("plots")

    def get_styled_plots(self) -> List[Dict[str, Any]]:
        """Get all styled plot files (Bloomberg-terminal style)."""
        return self.get_files_by_category("styled_plots")

    def has_styled_plots(self) -> bool:
        """Check if styled plots exist for this run."""
        styled_dir = self.artifacts_dir / "plots" / "styled"
        return styled_dir.exists() and any(styled_dir.glob("*.png"))

    def get_plots_with_styled_fallback(self, prefer_styled: bool = True) -> List[Dict[str, Any]]:
        """
        Get plots, preferring styled versions if available.

        Args:
            prefer_styled: If True and styled plots exist, return those; else original

        Returns:
            List of plot file info dicts
        """
        if prefer_styled and self.has_styled_plots():
            return self.get_styled_plots()
        return self.get_plots()

    def get_tables(self) -> List[Dict[str, Any]]:
        """Get all table files (CSV, Parquet, etc.)."""
        return self.get_files_by_category("tables")

    def get_models(self) -> List[Dict[str, Any]]:
        """Get all model files."""
        return self.get_files_by_category("models")

    def get_notebooks(self) -> List[Dict[str, Any]]:
        """Get all executed notebooks."""
        return self.get_files_by_category("notebooks")

    def find_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """Find a specific file in the index."""
        index = self.load_index()
        if index:
            for file_info in index.get("all_files", []):
                if file_info["name"] == filename or file_info["path"] == filename:
                    return file_info
        return None

    def get_anomalies_table(self) -> Optional[Dict[str, Any]]:
        """
        Find the anomalies table file if it exists.

        Priority:
        1. Use output_map.yaml patterns (deterministic)
        2. Fallback to heuristics
        """
        # First try output mapping
        tables_map = self.output_map.get("tables", {})

        # Try anomalies tables in priority order
        priority_keys = ["anomalies_primary", "anomalies_nodes", "anomalies_nodes_fg", "node_embeddings_fg"]
        for key in priority_keys:
            if key in tables_map:
                patterns = tables_map[key].get("patterns", [])
                for pattern in patterns:
                    found = self._find_by_pattern(pattern)
                    if found:
                        return self._get_file_info(found)

        # Fallback to heuristic search
        common_names = [
            "alert_nodes_td.csv",
            "anomalies.csv",
            "anomalies.parquet",
            "node_embeddings_fg.parquet",
            "node_embeddings_fg.csv",
            "predictions.csv",
            "predictions.parquet",
        ]

        tables = self.get_tables()
        for name in common_names:
            for table in tables:
                if table["name"] == name:
                    return table

        # If no exact match, look for files containing "anomal" or "prediction"
        for table in tables:
            name_lower = table["name"].lower()
            if "anomal" in name_lower or "alert" in name_lower or "prediction" in name_lower:
                return table

        return None
