"""
Chart PNG Exporter — Headless export of all dashboard charts.

Generates all chart PNGs for a completed pipeline run.
Uses kaleido for Plotly-to-PNG conversion and png_styler for Bloomberg styling.
"""

import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import plotly.graph_objects as go
import plotly.io as pio

logger = logging.getLogger(__name__)

DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 700
DEFAULT_SCALE = 2


def _apply_theme():
    """Apply the modern terminal Plotly theme for export."""
    try:
        from ..ui.plotly_theme import apply_modern_terminal_plotly
        apply_modern_terminal_plotly()
    except Exception:
        pass


def _save_figure_png(
    fig: go.Figure,
    output_path: Path,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    scale: int = DEFAULT_SCALE,
) -> bool:
    """Save a Plotly figure as PNG using kaleido. Returns True on success."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(
            str(output_path), format="png",
            width=width, height=height, scale=scale,
            engine="kaleido",
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save PNG {output_path.name}: {e}")
        return False


def _style_png(input_path: Path, styled_path: Path, run_id: str) -> bool:
    """Apply Bloomberg styling to a PNG. Returns True on success."""
    try:
        from ..reports.png_styler import style_single_png
        result = style_single_png(input_path, styled_path, run_id=run_id)
        return result is not None
    except Exception as e:
        logger.warning(f"Failed to style PNG {input_path.name}: {e}")
        return False


def _build_chart_registry(data) -> List[Tuple[str, Callable, str]]:
    """
    Build the ordered list of (filename, generator_callable, group_name).

    Returns only charts whose data dependencies are satisfied.
    """
    from .analytics import (
        chart_sar_overview, chart_type_bar, chart_type_heatmap,
        chart_degree_histogram, chart_top_degree_bar, chart_embeddings_pca,
    )
    from .dashboard import (
        chart_risk_distribution, chart_volume_pie, chart_top10_risk_nodes,
        chart_anomaly_curve, chart_confusion_matrix, chart_waterfall,
        chart_performance_gauges, chart_network_graph,
        chart_amount_histogram, chart_amount_vs_risk, chart_volume_by_type,
        chart_risk_heatmap, chart_risk_histogram, chart_volume_vs_risk,
        chart_risk_by_type_box, chart_risk_radar, chart_lorenz_curve,
    )
    from .tier_queue import chart_risk_score_distribution
    from .aml_scores import (
        chart_entity_signal_bar, chart_aml_score_distribution, chart_signal_radar,
    )

    registry = []

    # Analytics group
    if data.alert_nodes_df is not None:
        registry.append(("analytics_sar_overview", lambda: chart_sar_overview(data.alert_nodes_df), "analytics"))
        registry.append(("analytics_type_bar", lambda: chart_type_bar(data.alert_nodes_df), "analytics"))
        registry.append(("analytics_type_heatmap", lambda: chart_type_heatmap(data.alert_nodes_df), "analytics"))
    if data.edges_df is not None:
        registry.append(("analytics_degree_histogram", lambda: chart_degree_histogram(data.edges_df, data.alert_nodes_df), "analytics"))
        registry.append(("analytics_top_degree_bar", lambda: chart_top_degree_bar(data.edges_df, data.alert_nodes_df), "analytics"))
    if data.embeddings_df is not None:
        registry.append(("analytics_embeddings_pca", lambda: chart_embeddings_pca(data.embeddings_df), "analytics"))

    # Dashboard - Executive Summary
    if data.node_embeddings is not None:
        registry.append(("exec_risk_distribution", lambda: chart_risk_distribution(data), "dashboard"))
    if data.edges_df is not None and "is_suspicious" in (data.edges_df.columns if data.edges_df is not None else []):
        registry.append(("exec_volume_pie", lambda: chart_volume_pie(data), "dashboard"))
    if data.node_money is not None:
        registry.append(("exec_top10_risk_nodes", lambda: chart_top10_risk_nodes(data), "dashboard"))
    if data.anomaly_scores is not None:
        registry.append(("exec_anomaly_curve", lambda: chart_anomaly_curve(data), "dashboard"))

    # Dashboard - Financial Impact
    if data.tp + data.fp + data.fn + data.tn > 0:
        registry.append(("financial_confusion_matrix", lambda: chart_confusion_matrix(data), "dashboard"))
        registry.append(("financial_waterfall", lambda: chart_waterfall(data), "dashboard"))
        registry.append(("financial_performance_gauges", lambda: chart_performance_gauges(data), "dashboard"))

    # Dashboard - Network Graph
    if data.edges_df is not None and data.node_embeddings is not None:
        registry.append(("network_graph", lambda: chart_network_graph(data), "dashboard"))

    # Dashboard - Transaction Deep Dive
    if data.edges_df is not None:
        registry.append(("txn_amount_histogram", lambda: chart_amount_histogram(data), "dashboard"))
        if "edge_risk" in (data.edges_df.columns if data.edges_df is not None else []):
            registry.append(("txn_amount_vs_risk", lambda: chart_amount_vs_risk(data), "dashboard"))
        if "tx_type" in (data.edges_df.columns if data.edges_df is not None else []):
            registry.append(("txn_volume_by_type", lambda: chart_volume_by_type(data), "dashboard"))
        if data.nodes_df is not None and "source_type" in (data.edges_df.columns if data.edges_df is not None else []):
            registry.append(("txn_risk_heatmap", lambda: chart_risk_heatmap(data), "dashboard"))

    # Dashboard - Node Risk Profiles
    if data.node_money is not None and "risk_score" in (data.node_money.columns if data.node_money is not None else []):
        registry.append(("risk_histogram", lambda: chart_risk_histogram(data), "dashboard"))
        registry.append(("risk_volume_vs_risk", lambda: chart_volume_vs_risk(data), "dashboard"))
        if "type" in data.node_money.columns:
            registry.append(("risk_by_type_box", lambda: chart_risk_by_type_box(data), "dashboard"))
        registry.append(("risk_radar", lambda: chart_risk_radar(data), "dashboard"))
        registry.append(("risk_lorenz_curve", lambda: chart_lorenz_curve(data), "dashboard"))

    # Tier Queue
    if data.risk_queue_df is not None:
        registry.append(("tier_risk_score_distribution", lambda: chart_risk_score_distribution(data.risk_queue_df), "tier_queue"))

    # AML Scores
    if data.aml_scores_df is not None:
        registry.append(("aml_entity_signal_bar", lambda: chart_entity_signal_bar(data.aml_scores_df), "aml_scores"))
        registry.append(("aml_score_distribution", lambda: chart_aml_score_distribution(data.aml_scores_df), "aml_scores"))
        registry.append(("aml_signal_radar", lambda: chart_signal_radar(data.aml_scores_df), "aml_scores"))

    return registry


def export_all_charts(
    artifacts_dir: Path,
    run_id: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    theme: str = "bloomberg",
) -> Dict:
    """
    Generate all chart PNGs for a completed run.

    Args:
        artifacts_dir: Path to run's artifact directory
        run_id: Run ID (for styling header)
        progress_callback: Optional callback(current, total, chart_name)
        theme: Styling theme name

    Returns:
        Summary dict with counts and chart details.
    """
    start = time.time()
    _apply_theme()

    from .data_loader import load_all_data

    logger.info(f"Loading data for chart export from {artifacts_dir}")
    data = load_all_data(artifacts_dir)

    registry = _build_chart_registry(data)
    total = len(registry)
    logger.info(f"Chart registry built: {total} charts to export")

    output_dir = Path(artifacts_dir) / "plots" / "dashboard"
    styled_dir = output_dir / "styled"
    output_dir.mkdir(parents=True, exist_ok=True)
    styled_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "total_charts": total,
        "exported": 0,
        "styled": 0,
        "failed": 0,
        "skipped": 0,
        "charts": [],
        "data_errors": data.errors,
    }

    for idx, (filename, gen_fn, group) in enumerate(registry):
        chart_info = {"name": filename, "group": group, "status": "pending"}

        if progress_callback:
            progress_callback(idx, total, filename)

        try:
            fig = gen_fn()
            if fig is None:
                chart_info["status"] = "skipped"
                results["skipped"] += 1
                logger.debug(f"Skipped chart {filename} (returned None)")
            else:
                png_path = output_dir / f"{filename}.png"
                if _save_figure_png(fig, png_path):
                    chart_info["status"] = "exported"
                    chart_info["path"] = str(png_path)
                    results["exported"] += 1

                    # Apply Bloomberg styling
                    styled_path = styled_dir / f"{filename}.png"
                    if _style_png(png_path, styled_path, run_id):
                        chart_info["styled_path"] = str(styled_path)
                        results["styled"] += 1
                else:
                    chart_info["status"] = "failed"
                    results["failed"] += 1
        except Exception as e:
            chart_info["status"] = "failed"
            chart_info["error"] = str(e)
            results["failed"] += 1
            logger.error(f"Chart {filename} failed: {e}", exc_info=True)

        results["charts"].append(chart_info)

    if progress_callback:
        progress_callback(total, total, "done")

    results["duration_seconds"] = round(time.time() - start, 2)
    logger.info(
        f"Chart export complete: {results['exported']} exported, "
        f"{results['styled']} styled, {results['failed']} failed, "
        f"{results['skipped']} skipped in {results['duration_seconds']}s"
    )
    return results


def export_chart_group(
    artifacts_dir: Path,
    run_id: str,
    group: str,
    theme: str = "bloomberg",
) -> Dict:
    """Export charts for a single group only."""
    start = time.time()
    _apply_theme()

    from .data_loader import load_all_data

    data = load_all_data(artifacts_dir)
    registry = _build_chart_registry(data)
    filtered = [(fn, gen, grp) for fn, gen, grp in registry if grp == group]

    output_dir = Path(artifacts_dir) / "plots" / "dashboard"
    styled_dir = output_dir / "styled"
    output_dir.mkdir(parents=True, exist_ok=True)
    styled_dir.mkdir(parents=True, exist_ok=True)

    results = {"total_charts": len(filtered), "exported": 0, "failed": 0, "skipped": 0, "charts": []}

    for filename, gen_fn, grp in filtered:
        chart_info = {"name": filename, "group": grp}
        try:
            fig = gen_fn()
            if fig is None:
                chart_info["status"] = "skipped"
                results["skipped"] += 1
            else:
                png_path = output_dir / f"{filename}.png"
                if _save_figure_png(fig, png_path):
                    chart_info["status"] = "exported"
                    results["exported"] += 1
                    styled_path = styled_dir / f"{filename}.png"
                    _style_png(png_path, styled_path, run_id)
                else:
                    chart_info["status"] = "failed"
                    results["failed"] += 1
        except Exception as e:
            chart_info["status"] = "failed"
            chart_info["error"] = str(e)
            results["failed"] += 1

        results["charts"].append(chart_info)

    results["duration_seconds"] = round(time.time() - start, 2)
    return results
