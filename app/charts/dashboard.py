"""
Interactive Dashboard chart generators — no Streamlit dependency.

Extracted from streamlit_app.py lines 2042-2362.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional

from .data_loader import ChartData

CLR = dict(blue="#3498db", green="#2ecc71", red="#e74c3c",
           purple="#9b59b6", orange="#e67e22", yellow="#f1c40f")
RISK_COLORS = [CLR["green"], CLR["yellow"], CLR["orange"], CLR["red"]]
RISK_LABELS = ["Low", "Medium", "High", "Critical"]


# --- Executive Summary (4 charts) ---

def chart_risk_distribution(data: ChartData) -> Optional[go.Figure]:
    """Risk distribution bar chart. Source: line 2057."""
    if data.node_embeddings is None or "risk_score" not in data.node_embeddings.columns:
        return None

    risk_cat = pd.cut(
        data.node_embeddings["risk_score"],
        bins=[0, 0.25, 0.5, 0.75, 1.0],
        labels=RISK_LABELS,
        include_lowest=True,
    )
    risk_counts = risk_cat.value_counts().reindex(RISK_LABELS).fillna(0)
    fig = go.Figure(go.Bar(
        x=RISK_LABELS, y=risk_counts.values, marker_color=RISK_COLORS,
        text=[f"{int(v):,}" for v in risk_counts.values], textposition="outside",
    ))
    fig.update_layout(title="Risk Distribution", yaxis_title="Nodes", margin=dict(t=40, b=30))
    return fig


def chart_volume_pie(data: ChartData) -> Optional[go.Figure]:
    """Suspicious vs normal volume pie. Source: line 2066."""
    if data.edges_df is None or "is_suspicious" not in data.edges_df.columns:
        return None

    susp_vol = float(data.edges_df[data.edges_df["is_suspicious"]]["base_amt"].sum())
    norm_vol = float(data.edges_df[~data.edges_df["is_suspicious"]]["base_amt"].sum())
    fig = go.Figure(go.Pie(
        labels=["Normal", "Suspicious"], values=[norm_vol, susp_vol],
        marker_colors=[CLR["blue"], CLR["red"]], hole=0.45, textinfo="label+percent",
        hovertemplate="%{label}<br>$%{value:,.0f}<extra></extra>",
    ))
    fig.update_layout(title="Volume: Normal vs Suspicious", margin=dict(t=40, b=10))
    return fig


def chart_top10_risk_nodes(data: ChartData) -> Optional[go.Figure]:
    """Top 10 risk nodes by volume. Source: line 2077."""
    if data.node_money is None or "risk_score" not in data.node_money.columns:
        return None

    top10 = data.node_money.nlargest(10, "risk_score")
    fig = go.Figure(go.Bar(
        y=[f"{r['id'][:10]}... ({r['risk_score']:.2f})" for _, r in top10.iterrows()],
        x=top10["total_volume"], orientation="h",
        marker_color=px.colors.sample_colorscale("Reds", top10["risk_score"].values),
        hovertemplate="Node: %{y}<br>Volume: $%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title="Top 10 Risk Nodes by Volume", xaxis_title="Volume ($)",
        yaxis=dict(autorange="reversed"), margin=dict(t=40, b=30, l=160),
    )
    return fig


def chart_anomaly_curve(data: ChartData) -> Optional[go.Figure]:
    """Anomaly score curve with threshold line. Source: line 2088."""
    if data.anomaly_scores is None or data.threshold_val is None:
        return None

    sorted_scores = np.sort(data.anomaly_scores)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(sorted_scores))), y=sorted_scores,
        fill="tozeroy", fillcolor="rgba(52,152,219,0.2)",
        line=dict(color=CLR["blue"], width=2),
        hovertemplate="Node %{x}<br>Score: %{y:.6f}<extra></extra>",
    ))
    fig.add_hline(
        y=data.threshold_val, line_dash="dash", line_color="red",
        annotation_text=f"Threshold {data.threshold_val:.6f}",
    )
    fig.update_layout(
        title="Anomaly Score Curve", xaxis_title="Nodes (sorted)",
        yaxis_title="Score", margin=dict(t=40, b=30),
    )
    return fig


# --- Financial Impact (3 charts) ---

def chart_confusion_matrix(data: ChartData) -> Optional[go.Figure]:
    """Detection confusion matrix. Source: line 2112."""
    cm = np.array([[data.tn, data.fp], [data.fn, data.tp]])
    if cm.sum() == 0:
        return None

    fig = px.imshow(
        cm, text_auto=True,
        x=["Predicted Normal", "Predicted Anomaly"],
        y=["Actual Normal", "Actual AML"],
        color_continuous_scale="RdYlGn_r", labels=dict(color="Count"),
    )
    fig.update_layout(title="Detection Matrix", margin=dict(t=40, b=30))
    return fig


def chart_waterfall(data: ChartData) -> Optional[go.Figure]:
    """Loss vs savings waterfall. Source: line 2120."""
    fig = go.Figure(go.Waterfall(
        x=["Suspicious<br>Value", "Loss<br>Avoided", "Recovered",
           "Investigation<br>Cost", "FP Cost", "Net Savings"],
        y=[data.suspicious_txn_value, -data.potential_loss_detected, data.recovered_amount,
           -data.investigation_cost, -data.false_positive_cost, data.net_savings],
        measure=["absolute", "relative", "relative", "relative", "relative", "total"],
        connector_line_color="rgba(200,200,200,0.3)",
        increasing_marker_color=CLR["green"], decreasing_marker_color=CLR["red"],
        totals_marker_color=CLR["purple"],
        texttemplate="$%{y:,.0f}", textposition="outside",
    ))
    fig.update_layout(
        title="Loss vs Savings Waterfall", yaxis_title="Amount ($)",
        margin=dict(t=40, b=30),
    )
    return fig


def chart_performance_gauges(data: ChartData) -> Optional[go.Figure]:
    """Precision/Recall/F1 gauge indicators. Source: line 2135."""
    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{"type": "indicator"}] * 3],
        subplot_titles=["Precision", "Recall", "F1 Score"],
    )
    for i, (name, val, color) in enumerate([
        ("Precision", data.precision, CLR["blue"]),
        ("Recall", data.recall, CLR["green"]),
        ("F1", data.f1, CLR["purple"]),
    ], 1):
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=val * 100, number_suffix="%",
            gauge=dict(
                axis=dict(range=[0, 100]), bar_color=color,
                steps=[
                    dict(range=[0, 50], color="rgba(255,0,0,0.15)"),
                    dict(range=[50, 80], color="rgba(255,255,0,0.10)"),
                    dict(range=[80, 100], color="rgba(0,255,0,0.10)"),
                ],
            ),
        ), row=1, col=i)
    fig.update_layout(height=280, margin=dict(t=40, b=10))
    return fig


# --- Network Graph (1 chart) ---

def chart_network_graph(data: ChartData, filter_mode: str = "all") -> Optional[go.Figure]:
    """Transaction network graph. Source: line 2206."""
    if data.edges_df is None or data.node_embeddings is None:
        return None
    if "edge_risk" not in data.edges_df.columns:
        return None

    import networkx as nx

    max_nodes = 300
    node_risk_dict = data.node_embeddings.set_index("id")["risk_score"].to_dict()

    # Strategy: pick seed nodes (highest risk), then expand to their neighbors
    # so the resulting subgraph stays connected and meaningful.
    edges_sorted = data.edges_df.sort_values(["edge_risk", "base_amt"], ascending=[False, False])

    if filter_mode == "suspicious":
        candidate_edges = edges_sorted[edges_sorted["is_suspicious"]]
    elif filter_mode == "high_risk":
        hr_nodes = set(data.node_embeddings[data.node_embeddings["risk_score"] > 0.75]["id"])
        candidate_edges = edges_sorted[
            edges_sorted["source"].isin(hr_nodes) | edges_sorted["target"].isin(hr_nodes)
        ]
    else:
        candidate_edges = edges_sorted

    # Pick top seed nodes by risk score
    seed_count = min(50, max_nodes // 6)
    seed_nodes = set(
        data.node_embeddings.nlargest(seed_count, "risk_score")["id"].tolist()
    )

    # Expand: include all edges touching a seed node
    edges_subset = candidate_edges[
        candidate_edges["source"].isin(seed_nodes) | candidate_edges["target"].isin(seed_nodes)
    ]

    # Gather all nodes from these edges
    sel_nodes = set(edges_subset["source"].tolist() + edges_subset["target"].tolist())

    # If still too many, keep seed nodes + highest-risk neighbors
    if len(sel_nodes) > max_nodes:
        neighbor_nodes = sel_nodes - seed_nodes
        neighbor_df = data.node_embeddings[data.node_embeddings["id"].isin(neighbor_nodes)]
        keep_neighbors = set(neighbor_df.nlargest(max_nodes - len(seed_nodes), "risk_score")["id"])
        sel_nodes = seed_nodes | keep_neighbors
        edges_subset = edges_subset[
            edges_subset["source"].isin(sel_nodes) & edges_subset["target"].isin(sel_nodes)
        ]

    # Cap edges for rendering performance
    if len(edges_subset) > max_nodes * 3:
        edges_subset = edges_subset.head(max_nodes * 3)

    G = nx.DiGraph()
    for _, r in edges_subset.iterrows():
        G.add_edge(r["source"], r["target"], amount=r["base_amt"], risk=r["edge_risk"])

    if G.number_of_nodes() == 0:
        return None

    pos = nx.spring_layout(G, k=3 / np.sqrt(G.number_of_nodes()), iterations=50, seed=42)
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    vol_dict = data.node_money.set_index("id")["total_volume"].to_dict() if data.node_money is not None else {}
    txn_dict = data.node_money.set_index("id")["total_transactions"].to_dict() if data.node_money is not None else {}
    node_x = [pos[n][0] for n in G.nodes()]
    node_y = [pos[n][1] for n in G.nodes()]
    n_risk = [node_risk_dict.get(n, 0) for n in G.nodes()]
    n_vol = [vol_dict.get(n, 0) for n in G.nodes()]
    vol_mx = max(n_vol) if n_vol else 1
    n_sizes = [6 + 20 * (v / vol_mx) for v in n_vol]
    hover = [
        f"ID: {str(n)[:16]}<br>Risk: {node_risk_dict.get(n, 0):.4f}<br>"
        f"Volume: ${vol_dict.get(n, 0):,.0f}<br>Txns: {int(txn_dict.get(n, 0)):,}"
        for n in G.nodes()
    ]

    fig = go.Figure(data=[
        go.Scatter(
            x=edge_x, y=edge_y, mode="lines",
            line=dict(width=0.5, color="rgba(150,150,150,0.3)"), hoverinfo="none",
        ),
        go.Scatter(
            x=node_x, y=node_y, mode="markers",
            marker=dict(
                size=n_sizes, color=n_risk, colorscale="RdYlGn_r",
                cmin=0, cmax=1, colorbar=dict(title="Risk"),
                line=dict(width=0.5, color="white"),
            ),
            text=hover, hoverinfo="text",
        ),
    ])
    fig.update_layout(
        title=f"Transaction Network ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)",
        showlegend=False, hovermode="closest", height=650,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(t=40, b=10, l=10, r=10),
    )
    return fig


# --- Transaction Deep Dive (4 charts) ---

def chart_amount_histogram(data: ChartData) -> Optional[go.Figure]:
    """Amount distribution histogram. Source: line 2234."""
    if data.edges_df is None or "base_amt" not in data.edges_df.columns:
        return None

    fig = px.histogram(
        data.edges_df, x="base_amt", nbins=80,
        color_discrete_sequence=[CLR["blue"]],
        labels={"base_amt": "Amount ($)"},
    )
    fig.update_layout(
        title=f"Amount Distribution ({len(data.edges_df):,} txns)",
        yaxis_type="log", yaxis_title="Count (log)", margin=dict(t=40, b=30),
    )
    return fig


def chart_amount_vs_risk(data: ChartData) -> Optional[go.Figure]:
    """Amount vs risk scatter. Source: line 2243."""
    if data.edges_df is None or "edge_risk" not in data.edges_df.columns:
        return None

    samp = data.edges_df.sample(min(5000, len(data.edges_df)), random_state=42) if len(data.edges_df) > 0 else data.edges_df
    fig = px.scatter(
        samp, x="base_amt", y="edge_risk",
        color="edge_risk", color_continuous_scale="RdYlGn_r",
        hover_data=["source", "target", "base_amt", "edge_risk"],
        labels={"base_amt": "Amount ($)", "edge_risk": "Risk"},
    )
    fig.update_layout(title="Amount vs Risk", margin=dict(t=40, b=30))
    return fig


def chart_volume_by_type(data: ChartData) -> Optional[go.Figure]:
    """Volume by transaction type bar. Source: line 2255."""
    if data.edges_df is None or "tx_type" not in data.edges_df.columns:
        return None

    type_vol = data.edges_df.groupby("tx_type")["base_amt"].sum().sort_values(ascending=True).reset_index()
    type_vol["tx_type"] = type_vol["tx_type"].astype(str)
    fig = px.bar(
        type_vol, y="tx_type", x="base_amt", orientation="h",
        color="base_amt", color_continuous_scale="Blues",
        labels={"base_amt": "Volume ($)", "tx_type": "Tx Type"},
    )
    fig.update_layout(title="Volume by Transaction Type", margin=dict(t=40, b=30))
    return fig


def chart_risk_heatmap(data: ChartData) -> Optional[go.Figure]:
    """Risk by node-type pair heatmap. Source: line 2265."""
    if data.edges_df is None or data.nodes_df is None:
        return None
    if "source_type" not in data.edges_df.columns or "edge_risk" not in data.edges_df.columns:
        return None

    hm = data.edges_df.pivot_table(
        values="edge_risk", index="source_type",
        columns="target_type", aggfunc="mean",
    ).fillna(0)
    fig = px.imshow(
        hm, color_continuous_scale="RdYlGn_r",
        labels=dict(x="Target Type", y="Source Type", color="Avg Risk"),
        x=[f"Type {c}" for c in hm.columns],
        y=[f"Type {i}" for i in hm.index], text_auto=".3f",
    )
    fig.update_layout(title="Avg Risk by Node-Type Pair", margin=dict(t=40, b=30))
    return fig


# --- Node Risk Profiles (5 charts) ---

def chart_risk_histogram(data: ChartData) -> Optional[go.Figure]:
    """Risk score distribution with percentiles. Source: line 2277."""
    if data.node_money is None or "risk_score" not in data.node_money.columns:
        return None

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=data.node_money["risk_score"], nbinsx=60,
        marker_color=CLR["blue"], opacity=0.75,
    ))
    for p, clr in [(50, "green"), (75, "yellow"), (90, "orange"), (95, "red"), (99, "darkred")]:
        val = float(np.percentile(data.node_money["risk_score"], p))
        fig.add_vline(x=val, line_dash="dash", line_color=clr, annotation_text=f"P{p}: {val:.3f}")
    fig.update_layout(
        title="Risk Score Distribution", xaxis_title="Risk Score",
        yaxis_title="Nodes", margin=dict(t=40, b=30),
    )
    return fig


def chart_volume_vs_risk(data: ChartData) -> Optional[go.Figure]:
    """Volume vs risk scatter. Source: line 2289."""
    if data.node_money is None or "risk_score" not in data.node_money.columns:
        return None

    fig = px.scatter(
        data.node_money, x="total_volume", y="risk_score",
        color="is_anomaly",
        color_discrete_map={True: CLR["red"], False: CLR["blue"]},
        hover_data=["id", "total_volume", "total_transactions", "risk_score"],
        labels={"total_volume": "Volume ($)", "risk_score": "Risk Score", "is_anomaly": "Anomaly"},
    )
    fig.update_layout(title="Volume vs Risk", margin=dict(t=40, b=30))
    return fig


def chart_risk_by_type_box(data: ChartData) -> Optional[go.Figure]:
    """Risk by node type box plot. Source: line 2310."""
    if data.node_money is None or "type" not in data.node_money.columns:
        return None

    fig = px.box(
        data.node_money, x="type", y="risk_score",
        color="type", color_discrete_sequence=px.colors.qualitative.Set2,
        labels={"type": "Node Type", "risk_score": "Risk Score"},
    )
    fig.update_layout(title="Risk by Node Type", showlegend=False, margin=dict(t=40, b=30))
    return fig


def chart_risk_radar(data: ChartData) -> Optional[go.Figure]:
    """High-risk vs low-risk radar comparison. Source: line 2337."""
    if data.node_money is None or "risk_score" not in data.node_money.columns:
        return None

    high_risk = data.node_money[data.node_money["risk_score"] > 0.75]
    low_risk = data.node_money[data.node_money["risk_score"] <= 0.25]
    radar_cats = ["Avg Volume", "Avg Txns", "Out Flow", "In Flow", "Net Flow Var"]

    def _snorm(s, d):
        return float(s.mean() / d) if d > 0 and len(s) > 0 else 0

    vm = data.node_money["total_volume"].max() or 1
    tm = data.node_money["total_transactions"].max() or 1
    om = data.node_money["outgoing_amt"].max() or 1
    im_ = data.node_money["incoming_amt"].max() or 1
    ns = data.node_money["net_flow"].std() or 1

    hv = [
        _snorm(high_risk["total_volume"], vm), _snorm(high_risk["total_transactions"], tm),
        _snorm(high_risk["outgoing_amt"], om), _snorm(high_risk["incoming_amt"], im_),
        float(high_risk["net_flow"].std() / ns) if len(high_risk) > 1 else 0,
    ]
    lv = [
        _snorm(low_risk["total_volume"], vm), _snorm(low_risk["total_transactions"], tm),
        _snorm(low_risk["outgoing_amt"], om), _snorm(low_risk["incoming_amt"], im_),
        float(low_risk["net_flow"].std() / ns) if len(low_risk) > 1 else 0,
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=hv + [hv[0]], theta=radar_cats + [radar_cats[0]],
        fill="toself", name="High Risk", line_color=CLR["red"],
        fillcolor="rgba(231,76,60,0.2)",
    ))
    fig.add_trace(go.Scatterpolar(
        r=lv + [lv[0]], theta=radar_cats + [radar_cats[0]],
        fill="toself", name="Low Risk", line_color=CLR["green"],
        fillcolor="rgba(46,204,113,0.2)",
    ))
    fig.update_layout(
        title="Risk Profile Comparison",
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        margin=dict(t=50, b=30),
    )
    return fig


def chart_lorenz_curve(data: ChartData) -> Optional[go.Figure]:
    """Risk concentration Lorenz curve. Source: line 2353."""
    if data.node_money is None or "risk_score" not in data.node_money.columns:
        return None

    sorted_by_risk = data.node_money.sort_values("risk_score")
    total_vol = sorted_by_risk["total_volume"].sum()
    if total_vol == 0:
        return None

    cum_vol = sorted_by_risk["total_volume"].cumsum() / total_vol
    x_lorenz = np.linspace(0, 1, len(cum_vol))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_lorenz, y=cum_vol.values, fill="tonexty",
        name="Actual", line_color=CLR["blue"], fillcolor="rgba(52,152,219,0.2)",
    ))
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], line_dash="dash", name="Equal", line_color="grey",
    ))
    fig.update_layout(
        title="Risk Concentration (Lorenz)",
        xaxis_title="Cumulative % Nodes", yaxis_title="Cumulative % Volume",
        margin=dict(t=40, b=30),
    )
    return fig
