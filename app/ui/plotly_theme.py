"""
Modern Terminal Style Plotly Theme

Provides a dark terminal-style theme for Plotly charts with:
- Dark panel backgrounds
- Terminal-style monospace fonts
- Amber/orange accents
- Cyan/green/red status colors
"""

import plotly.io as pio
import plotly.graph_objects as go

# Modern terminal color palette
MODERN_TERMINAL_COLORS = {
    "bg": "#0B0F14",
    "panel": "#111827",
    "panel2": "#0F172A",
    "border": "#243042",
    "text": "#E5E7EB",
    "muted": "#9CA3AF",
    "accent": "#FBBF24",  # Terminal amber/gold
    "cyan": "#22D3EE",
    "green": "#22C55E",
    "red": "#EF4444",
    "amber": "#F59E0B",
}

# Backward compatibility alias
BLOOMBERG_COLORS = MODERN_TERMINAL_COLORS

# Monospace font stack
MONO_FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def apply_modern_terminal_plotly():
    """
    Register and set the modern terminal-style Plotly template as default.

    Call this once at app startup to apply the theme globally.
    """
    pio.templates["modern_terminal"] = {
        "layout": {
            "paper_bgcolor": MODERN_TERMINAL_COLORS["bg"],
            "plot_bgcolor": MODERN_TERMINAL_COLORS["panel"],
            "font": {
                "family": MONO_FONT,
                "color": MODERN_TERMINAL_COLORS["text"],
                "size": 12,
            },
            "title": {
                "x": 0.02,
                "xanchor": "left",
                "font": {"size": 14, "color": MODERN_TERMINAL_COLORS["text"]},
            },
            "margin": {"l": 40, "r": 20, "t": 42, "b": 36},
            "xaxis": {
                "gridcolor": "rgba(36,48,66,0.5)",
                "zerolinecolor": "rgba(36,48,66,0.65)",
                "linecolor": "rgba(36,48,66,0.9)",
                "tickfont": {"size": 11, "color": MODERN_TERMINAL_COLORS["muted"]},
                "title": {"font": {"size": 12, "color": MODERN_TERMINAL_COLORS["text"]}},
            },
            "yaxis": {
                "gridcolor": "rgba(36,48,66,0.5)",
                "zerolinecolor": "rgba(36,48,66,0.65)",
                "linecolor": "rgba(36,48,66,0.9)",
                "tickfont": {"size": 11, "color": MODERN_TERMINAL_COLORS["muted"]},
                "title": {"font": {"size": 12, "color": MODERN_TERMINAL_COLORS["text"]}},
            },
            "hoverlabel": {
                "bgcolor": MODERN_TERMINAL_COLORS["panel2"],
                "bordercolor": "rgba(251,191,36,0.6)",
                "font": {
                    "family": MONO_FONT,
                    "color": MODERN_TERMINAL_COLORS["text"],
                },
            },
            "legend": {
                "bgcolor": "rgba(0,0,0,0)",
                "bordercolor": "rgba(36,48,66,0.8)",
                "borderwidth": 1,
                "font": {"size": 11, "color": MODERN_TERMINAL_COLORS["text"]},
            },
            "colorway": [
                MODERN_TERMINAL_COLORS["accent"],
                MODERN_TERMINAL_COLORS["cyan"],
                MODERN_TERMINAL_COLORS["green"],
                MODERN_TERMINAL_COLORS["red"],
                "#A78BFA",  # Purple
                "#14B8A6",  # Teal
                "#FB923C",  # Orange
                "#F472B6",  # Pink
            ],
        }
    }
    pio.templates.default = "modern_terminal"


# Backward compatibility alias
def apply_bloomberg_plotly_template():
    """Backward compatibility alias for apply_modern_terminal_plotly."""
    apply_modern_terminal_plotly()


def get_bloomberg_colorscale():
    """
    Get a Bloomberg-style continuous colorscale for heatmaps.

    Returns:
        List of [position, color] pairs for Plotly colorscale
    """
    return [
        [0.0, BLOOMBERG_COLORS["panel"]],
        [0.2, "#1a2332"],
        [0.4, "#2d3d52"],
        [0.6, "#c47800"],
        [0.8, BLOOMBERG_COLORS["accent"]],
        [1.0, "#FFD54F"],
    ]


def get_diverging_colorscale():
    """
    Get a diverging colorscale (red-neutral-green) for Bloomberg style.

    Returns:
        List of [position, color] pairs
    """
    return [
        [0.0, BLOOMBERG_COLORS["red"]],
        [0.5, BLOOMBERG_COLORS["panel"]],
        [1.0, BLOOMBERG_COLORS["green"]],
    ]


def style_pie_chart(fig: go.Figure) -> go.Figure:
    """
    Apply Bloomberg styling to a pie/donut chart.

    Args:
        fig: Plotly figure to style

    Returns:
        Styled figure
    """
    fig.update_traces(
        textfont={"family": MONO_FONT, "size": 11},
        marker=dict(
            line=dict(color=BLOOMBERG_COLORS["bg"], width=2)
        ),
    )
    fig.update_layout(
        paper_bgcolor=BLOOMBERG_COLORS["bg"],
        plot_bgcolor=BLOOMBERG_COLORS["panel"],
    )
    return fig


def style_bar_chart(fig: go.Figure) -> go.Figure:
    """
    Apply Bloomberg styling to a bar chart.

    Args:
        fig: Plotly figure to style

    Returns:
        Styled figure
    """
    fig.update_traces(
        marker=dict(
            line=dict(color=BLOOMBERG_COLORS["border"], width=1)
        ),
    )
    return fig


def get_status_colors():
    """
    Get status indicator colors for Bloomberg style.

    Returns:
        Dict with ok, warn, error colors
    """
    return {
        "ok": BLOOMBERG_COLORS["green"],
        "warn": BLOOMBERG_COLORS["accent"],
        "error": BLOOMBERG_COLORS["red"],
        "info": BLOOMBERG_COLORS["cyan"],
        "muted": BLOOMBERG_COLORS["muted"],
    }
