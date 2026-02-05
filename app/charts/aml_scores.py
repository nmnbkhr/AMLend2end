"""
AML Scores chart generators — no Streamlit dependency.

Extracted from streamlit_app.py lines 3333-3423.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional


BAND_COLORS = {
    "Critical": "#DC2626",
    "High": "#F59E0B",
    "Medium": "#3B82F6",
    "Low": "#22C55E",
    "Minimal": "#6B7280",
}

SIGNAL_LABELS = {
    "sar_signal": "SAR",
    "laundering_signal": "Laundering",
    "network_signal": "Network",
    "geo_signal": "Geo",
    "volume_signal": "Volume",
}

SIGNAL_COLORS_MAP = {
    "SAR": "#DC2626",
    "Laundering": "#F59E0B",
    "Network": "#3B82F6",
    "Geo": "#22C55E",
    "Volume": "#9333EA",
}


def chart_entity_signal_bar(scores_df: pd.DataFrame) -> Optional[go.Figure]:
    """Signal strength bar chart for top-1 entity. Source: line 3333."""
    if scores_df is None or len(scores_df) == 0:
        return None

    signal_cols = ["sar_signal", "laundering_signal", "network_signal",
                   "geo_signal", "volume_signal"]
    available = [c for c in signal_cols if c in scores_df.columns]
    if not available:
        return None

    # Pick the highest-scoring entity
    sort_col = "aml_score" if "aml_score" in scores_df.columns else available[0]
    entity_row = scores_df.nlargest(1, sort_col).iloc[0]

    vals, labels, colors = [], [], []
    for sc in available:
        val = float(entity_row[sc])
        label = SIGNAL_LABELS.get(sc, sc)
        vals.append(val)
        labels.append(label)
        colors.append(SIGNAL_COLORS_MAP.get(label, "#6B7280"))

    fig = go.Figure(go.Bar(
        x=labels, y=vals, marker_color=colors,
        text=[f"{v:.3f}" for v in vals], textposition="outside",
    ))
    eid = str(entity_row.get("entity_id", entity_row.name))[:16]
    fig.update_layout(
        title=f"Signal Strength — {eid}",
        height=300, margin=dict(l=40, r=20, t=40, b=40),
        yaxis=dict(range=[0, 1.15], title="Signal Strength"),
        xaxis=dict(title=""),
    )
    return fig


def chart_aml_score_distribution(scores_df: pd.DataFrame) -> Optional[go.Figure]:
    """AML score distribution histogram colored by risk_band. Source: line 3370."""
    if scores_df is None or "aml_score" not in scores_df.columns:
        return None

    color_col = "risk_band" if "risk_band" in scores_df.columns else None
    fig = px.histogram(
        scores_df,
        x="aml_score",
        color=color_col,
        nbins=50,
        color_discrete_map=BAND_COLORS if color_col else None,
        labels={"aml_score": "AML Score", "risk_band": "Risk Band"},
    )
    fig.update_layout(
        height=340,
        margin=dict(l=40, r=20, t=30, b=40),
        barmode="overlay",
        legend=dict(orientation="h", y=1.08),
    )
    fig.update_traces(opacity=0.75)
    return fig


def chart_signal_radar(scores_df: pd.DataFrame, top_n: int = 5) -> Optional[go.Figure]:
    """Signal breakdown radar chart for top N entities. Source: line 3398."""
    if scores_df is None or len(scores_df) == 0:
        return None

    signal_cols = ["sar_signal", "laundering_signal", "network_signal",
                   "geo_signal", "volume_signal"]
    if not all(c in scores_df.columns for c in signal_cols):
        return None

    categories = ["SAR", "Laundering", "Network", "Geo", "Volume"]
    sort_col = "aml_score" if "aml_score" in scores_df.columns else signal_cols[0]
    df_top = scores_df.nlargest(top_n, sort_col)

    fig = go.Figure()
    for _, row in df_top.iterrows():
        values = [row[c] for c in signal_cols]
        values.append(values[0])
        eid = str(row.get("entity_id", "?"))[:12]
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories + [categories[0]],
            name=eid,
            fill="toself",
            opacity=0.5,
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1]),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=420,
        margin=dict(l=60, r=60, t=40, b=40),
        legend=dict(orientation="h", y=-0.15),
    )
    return fig
