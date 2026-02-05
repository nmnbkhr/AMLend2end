"""
Analytics tab chart generators — no Streamlit dependency.

Extracted from streamlit_app.py lines 1572-1827.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional


def chart_sar_overview(alert_df: pd.DataFrame) -> Optional[go.Figure]:
    """SAR vs Non-SAR donut chart. Source: streamlit_app.py line 1583."""
    if alert_df is None or "is_sar" not in alert_df.columns:
        return None

    sar_counts = alert_df["is_sar"].value_counts().reset_index()
    sar_counts.columns = ["is_sar", "count"]
    sar_counts["label"] = sar_counts["is_sar"].map({1: "SAR", 0: "Non-SAR"})

    fig = px.pie(
        sar_counts,
        values="count",
        names="label",
        title="SAR vs Non-SAR Distribution",
        hole=0.4,
        color="label",
        color_discrete_map={"SAR": "#d62728", "Non-SAR": "#2ca02c"},
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="<b>%{label}</b><br>Count: %{value:,}<br>Percent: %{percent}<extra></extra>",
    )
    return fig


def chart_type_bar(alert_df: pd.DataFrame, type_col: str = "type") -> Optional[go.Figure]:
    """Top 30 types stacked bar chart. Source: streamlit_app.py line 1614."""
    if alert_df is None or type_col not in alert_df.columns or "is_sar" not in alert_df.columns:
        return None

    type_sar_counts = alert_df.groupby([type_col, "is_sar"]).size().reset_index(name="count")
    type_totals = type_sar_counts.groupby(type_col)["count"].sum().sort_values(ascending=False)
    top_30_types = type_totals.head(30).index.tolist()
    type_sar_filtered = type_sar_counts[type_sar_counts[type_col].isin(top_30_types)]
    type_sar_filtered = type_sar_filtered.copy()
    type_sar_filtered["sar_label"] = type_sar_filtered["is_sar"].map({1: "SAR", 0: "Non-SAR"})

    fig = px.bar(
        type_sar_filtered,
        x=type_col,
        y="count",
        color="sar_label",
        title="Top 30 Types by Count (Split by SAR Status)",
        barmode="stack",
        color_discrete_map={"SAR": "#d62728", "Non-SAR": "#2ca02c"},
        labels={type_col: "Type", "count": "Count", "sar_label": "Status"},
    )
    fig.update_traces(
        hovertemplate="<b>Type:</b> %{x}<br><b>Count:</b> %{y:,}<extra></extra>"
    )
    fig.update_layout(xaxis_tickangle=-45)
    return fig


def chart_type_heatmap(alert_df: pd.DataFrame, type_col: str = "type") -> Optional[go.Figure]:
    """Type x SAR heatmap. Source: streamlit_app.py line 1634."""
    if alert_df is None or type_col not in alert_df.columns or "is_sar" not in alert_df.columns:
        return None

    type_sar_counts = alert_df.groupby([type_col, "is_sar"]).size().reset_index(name="count")
    type_totals = type_sar_counts.groupby(type_col)["count"].sum().sort_values(ascending=False)
    top_30_types = type_totals.head(30).index.tolist()
    type_sar_filtered = type_sar_counts[type_sar_counts[type_col].isin(top_30_types)]
    type_sar_filtered = type_sar_filtered.copy()
    type_sar_filtered["sar_label"] = type_sar_filtered["is_sar"].map({1: "SAR", 0: "Non-SAR"})
    pivot_df = type_sar_filtered.pivot(index=type_col, columns="sar_label", values="count").fillna(0)

    fig = px.imshow(
        pivot_df.values,
        x=pivot_df.columns.tolist(),
        y=pivot_df.index.tolist(),
        color_continuous_scale="Reds",
        title="Heatmap: Type x SAR Status",
        labels={"x": "SAR Status", "y": "Type", "color": "Count"},
        aspect="auto",
    )
    fig.update_traces(
        hovertemplate="<b>Type:</b> %{y}<br><b>Status:</b> %{x}<br><b>Count:</b> %{z:,}<extra></extra>"
    )
    return fig


def chart_degree_histogram(edges_df: pd.DataFrame, alert_df: Optional[pd.DataFrame] = None) -> Optional[go.Figure]:
    """Node degree distribution histogram. Source: streamlit_app.py line 1689."""
    if edges_df is None:
        return None

    src_col, dst_col = None, None
    for col in ["source", "src", "from", "sender"]:
        if col in edges_df.columns:
            src_col = col
            break
    for col in ["target", "dst", "to", "receiver"]:
        if col in edges_df.columns:
            dst_col = col
            break

    if not src_col or not dst_col:
        return None

    src_counts = edges_df[src_col].value_counts()
    dst_counts = edges_df[dst_col].value_counts()
    degree_df = pd.DataFrame({"id": list(set(src_counts.index) | set(dst_counts.index))})
    degree_df["out_degree"] = degree_df["id"].map(src_counts).fillna(0).astype(int)
    degree_df["in_degree"] = degree_df["id"].map(dst_counts).fillna(0).astype(int)
    degree_df["degree"] = degree_df["out_degree"] + degree_df["in_degree"]

    fig = px.histogram(
        degree_df,
        x="degree",
        nbins=50,
        title="Node Degree Distribution",
        labels={"degree": "Degree", "count": "Count"},
    )
    fig.update_traces(
        hovertemplate="<b>Degree:</b> %{x}<br><b>Count:</b> %{y:,}<extra></extra>"
    )
    return fig


def chart_top_degree_bar(edges_df: pd.DataFrame, alert_df: Optional[pd.DataFrame] = None) -> Optional[go.Figure]:
    """Top 20 nodes by degree bar chart. Source: streamlit_app.py line 1713."""
    if edges_df is None:
        return None

    src_col, dst_col = None, None
    for col in ["source", "src", "from", "sender"]:
        if col in edges_df.columns:
            src_col = col
            break
    for col in ["target", "dst", "to", "receiver"]:
        if col in edges_df.columns:
            dst_col = col
            break

    if not src_col or not dst_col:
        return None

    src_counts = edges_df[src_col].value_counts()
    dst_counts = edges_df[dst_col].value_counts()
    degree_df = pd.DataFrame({"id": list(set(src_counts.index) | set(dst_counts.index))})
    degree_df["out_degree"] = degree_df["id"].map(src_counts).fillna(0).astype(int)
    degree_df["in_degree"] = degree_df["id"].map(dst_counts).fillna(0).astype(int)
    degree_df["degree"] = degree_df["out_degree"] + degree_df["in_degree"]

    top_20 = degree_df.nlargest(20, "degree")

    fig = px.bar(
        top_20,
        x="id",
        y="degree",
        title="Top 20 Nodes by Degree",
        labels={"id": "Node ID", "degree": "Degree"},
        color="degree",
        color_continuous_scale="Blues",
    )
    fig.update_layout(xaxis_tickangle=-45)
    return fig


def chart_embeddings_pca(embeddings_df: pd.DataFrame) -> Optional[go.Figure]:
    """PCA visualization of node embeddings. Source: streamlit_app.py line 1804."""
    if embeddings_df is None:
        return None

    try:
        from sklearn.decomposition import PCA
    except ImportError:
        return None

    emb_cols = [c for c in embeddings_df.columns if c.startswith("emb_")]
    if not emb_cols:
        emb_cols = [c for c in embeddings_df.columns if c.startswith("embedding_")]
    if not emb_cols:
        exclude = {"id", "is_sar", "type", "score", "amount", "degree"}
        emb_cols = [c for c in embeddings_df.select_dtypes(include=[np.number]).columns if c not in exclude]

    if len(emb_cols) < 2:
        return None

    sample_size = min(5000, len(embeddings_df))
    sample_df = embeddings_df.sample(n=sample_size, random_state=42) if len(embeddings_df) > sample_size else embeddings_df.copy()

    if len(sample_df) < 10:
        return None

    X = sample_df[emb_cols].values
    pca = PCA(n_components=2)
    pca_result = pca.fit_transform(X)

    sample_df = sample_df.copy()
    sample_df["PCA1"] = pca_result[:, 0]
    sample_df["PCA2"] = pca_result[:, 1]

    hover_data = {}
    if "id" in sample_df.columns:
        hover_data["id"] = True
    if "is_sar" in sample_df.columns:
        hover_data["is_sar"] = True

    color_col = None
    color_map = None
    if "is_sar" in sample_df.columns:
        sample_df["sar_label"] = sample_df["is_sar"].map({1: "SAR", 0: "Non-SAR", None: "Unknown"})
        color_col = "sar_label"
        color_map = {"SAR": "#d62728", "Non-SAR": "#2ca02c", "Unknown": "#7f7f7f"}

    fig = px.scatter(
        sample_df,
        x="PCA1",
        y="PCA2",
        color=color_col,
        color_discrete_map=color_map,
        title=f"PCA Visualization of Embeddings (n={len(sample_df):,})",
        hover_data=hover_data,
        labels={
            "PCA1": f"PC1 ({pca.explained_variance_ratio_[0] * 100:.1f}%)",
            "PCA2": f"PC2 ({pca.explained_variance_ratio_[1] * 100:.1f}%)",
        },
    )
    fig.update_traces(marker=dict(size=5, opacity=0.7))
    fig.update_layout(legend_title_text="SAR Status")
    return fig
