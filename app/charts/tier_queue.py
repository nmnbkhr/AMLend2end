"""
Tier Queue chart generators — no Streamlit dependency.

Extracted from streamlit_app.py line 2716.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional


TIER_COLORS = {"T1": "#EF4444", "T2": "#F59E0B", "T3": "#3B82F6", "T4": "#6B7280"}


def chart_risk_score_distribution(queue_df: pd.DataFrame) -> Optional[go.Figure]:
    """Risk score distribution histogram colored by tier. Source: line 2716."""
    if queue_df is None or "risk_score" not in queue_df.columns:
        return None

    color_col = "tier" if "tier" in queue_df.columns else None
    fig = px.histogram(
        queue_df,
        x="risk_score",
        color=color_col,
        nbins=40,
        color_discrete_map=TIER_COLORS if color_col else None,
        labels={"risk_score": "Risk Score", "tier": "Tier"},
    )
    fig.update_layout(
        height=340,
        margin=dict(l=40, r=20, t=30, b=40),
        barmode="overlay",
        legend=dict(orientation="h", y=1.08),
    )
    fig.update_traces(opacity=0.75)
    return fig
