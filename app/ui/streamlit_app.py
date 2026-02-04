"""
AML Pipeline Runner - Streamlit UI

A single-page application with tabs for:
- Run: Start new pipeline runs with profile selection
- Status: Monitor running/completed jobs with auto-refresh
- Dashboard: View visualizations, metrics, and anomaly data
- Analytics: Interactive Plotly charts from run data
- Report: Access and download generated reports
- Interactive: Full interactive dashboard with 5 analysis sub-tabs
- Tier Queue: Risk-ranked entity queue with filtering and export
- Cases: Investigation-ready AML cases with typology detection and network graphs

Run with: streamlit run app/ui/streamlit_app.py
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.utils.paths import (
    get_repo_root,
    get_artifacts_root,
    get_run_dir,
    get_data_dir,
    debug_paths,
)
from app.ui.plotly_theme import apply_modern_terminal_plotly, MODERN_TERMINAL_COLORS, BLOOMBERG_COLORS

# Configuration
API_BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
POLL_INTERVAL = 2  # Auto-refresh interval for running jobs
PROJECT_ROOT = get_repo_root()
ARTIFACTS_ROOT = get_artifacts_root()

# Page configuration
st.set_page_config(
    page_title="AML Pipeline Runner",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Modern Terminal Style Theme
def apply_modern_terminal_css():
    """Inject modern terminal-style CSS into Streamlit."""
    st.markdown(
        """
        <style>
        :root {
          --bg: #0B0F14;
          --panel: #111827;
          --panel2: #0F172A;
          --border: #243042;
          --text: #E5E7EB;
          --muted: #9CA3AF;
          --accent: #FBBF24;
          --cyan: #22D3EE;
          --green: #22C55E;
          --red: #EF4444;
          --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
          --ui: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        }

        /* ===== BASE ===== */
        html, body, [class*="stApp"] {
          background: var(--bg) !important;
          color: var(--text) !important;
          font-family: var(--ui) !important;
        }
        /* Fix top clipping - add proper spacing so tabs aren't cut off */
        .block-container {
          padding-top: 2.5rem !important;
          padding-bottom: 1.2rem;
          max-width: 1320px;
        }
        section.main > div {
          padding-top: 1.5rem !important;
        }
        /* Push content below any Streamlit header */
        [data-testid="stAppViewContainer"] > section > div {
          padding-top: 1rem !important;
        }
        header[data-testid="stHeader"] {
          background: var(--bg) !important;
        }

        /* ===== SCROLLBAR ===== */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

        /* ===== SIDEBAR ===== */
        section[data-testid="stSidebar"] {
          background: linear-gradient(180deg, #0A0F16, #0B0F14) !important;
          border-right: 1px solid var(--border) !important;
        }
        section[data-testid="stSidebar"] * {
          color: var(--text) !important;
        }
        section[data-testid="stSidebar"] .stMarkdown p {
          font-size: 0.9rem;
        }

        /* ===== HEADINGS ===== */
        h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 0.5rem 0; color: var(--text); }
        h2 { font-size: 1.1rem; font-weight: 600; margin: 0.8rem 0 0.4rem 0; color: var(--text); }
        h3 { font-size: 0.95rem; font-weight: 500; margin: 0.6rem 0 0.3rem 0; color: var(--muted); }

        /* ===== TABS (FIXED v6) ===== */
        /* Reset ALL clipping in tabs - use !important everywhere */
        .stTabs,
        .stTabs > div,
        [data-testid="stTabs"],
        [data-testid="stTabs"] > div {
          overflow: visible !important;
          clip-path: none !important;
        }
        /* Tab list container - generous sizing */
        .stTabs [data-baseweb="tab-list"],
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 8px 12px !important;
          gap: 8px !important;
          display: flex !important;
          flex-wrap: nowrap !important;
          min-height: 52px !important;
          height: auto !important;
          align-items: center !important;
          overflow: visible !important;
        }
        /* Individual tab buttons - proper sizing for emojis */
        .stTabs button[role="tab"],
        [data-testid="stTabs"] button[role="tab"],
        [data-baseweb="tab"] {
          all: unset !important;
          display: inline-flex !important;
          align-items: center !important;
          justify-content: center !important;
          background: transparent !important;
          color: var(--muted) !important;
          font-family: var(--mono) !important;
          font-size: 0.85rem !important;
          font-weight: 500 !important;
          border: none !important;
          border-radius: 8px !important;
          padding: 10px 18px !important;
          margin: 0 !important;
          min-height: 36px !important;
          height: auto !important;
          line-height: 1.4 !important;
          white-space: nowrap !important;
          cursor: pointer !important;
          box-sizing: border-box !important;
          overflow: visible !important;
        }
        /* Force text/emoji visibility - use all:unset then restyle */
        .stTabs button[role="tab"] p,
        .stTabs button[role="tab"] span,
        .stTabs button[role="tab"] div,
        [data-testid="stTabs"] button[role="tab"] p,
        [data-testid="stTabs"] button[role="tab"] span,
        [data-testid="stTabs"] button[role="tab"] div,
        [data-baseweb="tab"] p,
        [data-baseweb="tab"] span,
        [data-baseweb="tab"] div {
          all: unset !important;
          color: inherit !important;
          font-family: inherit !important;
          font-size: inherit !important;
          font-weight: inherit !important;
          line-height: inherit !important;
          display: inline !important;
          overflow: visible !important;
        }
        /* Hover state */
        .stTabs button[role="tab"]:hover,
        [data-testid="stTabs"] button[role="tab"]:hover,
        [data-baseweb="tab"]:hover {
          background: rgba(251,191,36,0.12) !important;
          color: var(--text) !important;
        }
        /* Active/selected tab */
        .stTabs button[role="tab"][aria-selected="true"],
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"],
        [data-baseweb="tab"][aria-selected="true"] {
          background: rgba(251,191,36,0.2) !important;
          color: var(--accent) !important;
          font-weight: 600 !important;
        }
        /* Hide default tab decorations (underline, highlight bar) */
        .stTabs [data-baseweb="tab-highlight"],
        .stTabs [data-baseweb="tab-border"],
        [data-testid="stTabs"] [data-baseweb="tab-highlight"],
        [data-testid="stTabs"] [data-baseweb="tab-border"] {
          display: none !important;
          height: 0 !important;
          visibility: hidden !important;
        }
        /* Tab panel content */
        .stTabs [data-baseweb="tab-panel"],
        [data-testid="stTabs"] [data-baseweb="tab-panel"] {
          padding-top: 1rem !important;
          overflow: visible !important;
        }

        /* ===== BUTTONS ===== */
        .stButton > button {
          background: linear-gradient(180deg, var(--panel), var(--panel2)) !important;
          color: var(--text) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 0.5rem 1rem !important;
          font-family: var(--mono) !important;
          font-size: 0.85rem !important;
          font-weight: 500 !important;
          transition: all 150ms ease !important;
        }
        .stButton > button:hover {
          border-color: var(--accent) !important;
          box-shadow: 0 0 0 2px rgba(251,191,36,0.15) !important;
        }
        .stButton > button:active {
          transform: scale(0.98);
        }

        /* ===== INPUTS & TEXT FIELDS ===== */
        div[data-baseweb="input"] {
          background: transparent !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea {
          background: var(--panel2) !important;
          color: var(--text) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
          font-family: var(--mono) !important;
          font-size: 0.85rem !important;
          padding: 0.5rem 0.75rem !important;
        }
        div[data-baseweb="input"] input::placeholder,
        div[data-baseweb="textarea"] textarea::placeholder {
          color: var(--muted) !important;
          opacity: 0.6 !important;
        }
        div[data-baseweb="input"] input:focus,
        div[data-baseweb="textarea"] textarea:focus {
          border-color: var(--accent) !important;
          box-shadow: 0 0 0 2px rgba(251,191,36,0.15) !important;
        }
        /* Input labels */
        .stTextInput label, .stTextArea label, .stNumberInput label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
          font-weight: 500 !important;
        }

        /* ===== SELECT/DROPDOWN ===== */
        div[data-testid="stSelectbox"] label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
          font-weight: 500 !important;
        }
        div[data-baseweb="select"] > div {
          background: var(--panel2) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
        }
        div[data-baseweb="select"] > div:hover {
          border-color: var(--accent) !important;
        }
        div[data-baseweb="select"] [data-baseweb="select"] {
          color: var(--text) !important;
        }
        div[data-baseweb="select"] svg {
          fill: var(--muted) !important;
        }
        /* Dropdown menu */
        div[data-baseweb="popover"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
          box-shadow: 0 8px 24px rgba(0,0,0,0.4) !important;
        }
        div[data-baseweb="popover"] ul {
          background: transparent !important;
        }
        div[data-baseweb="popover"] li {
          background: transparent !important;
          color: var(--text) !important;
          font-size: 0.85rem !important;
        }
        div[data-baseweb="popover"] li:hover {
          background: rgba(251,191,36,0.1) !important;
        }
        div[data-baseweb="popover"] li[aria-selected="true"] {
          background: rgba(251,191,36,0.2) !important;
          color: var(--accent) !important;
        }

        /* ===== MULTISELECT ===== */
        div[data-testid="stMultiSelect"] label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 6px !important;
          color: var(--text) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] span {
          color: var(--text) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"] svg {
          fill: var(--muted) !important;
        }
        div[data-baseweb="select"] [data-baseweb="tag"]:hover svg {
          fill: var(--red) !important;
        }

        /* ===== CHECKBOX ===== */
        div[data-testid="stCheckbox"] {
          padding: 0.25rem 0 !important;
        }
        div[data-testid="stCheckbox"] label {
          color: var(--text) !important;
          font-size: 0.85rem !important;
        }
        div[data-testid="stCheckbox"] label span[data-baseweb="checkbox"] {
          background: var(--panel2) !important;
          border: 2px solid var(--border) !important;
          border-radius: 4px !important;
        }
        div[data-testid="stCheckbox"] label span[data-baseweb="checkbox"]:hover {
          border-color: var(--accent) !important;
        }
        div[data-testid="stCheckbox"] input:checked + span[data-baseweb="checkbox"] {
          background: var(--accent) !important;
          border-color: var(--accent) !important;
        }

        /* ===== RADIO BUTTONS ===== */
        div[data-testid="stRadio"] > label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
          font-weight: 500 !important;
          margin-bottom: 0.5rem !important;
        }
        div[data-testid="stRadio"] label[data-baseweb="radio"] {
          color: var(--text) !important;
          font-size: 0.85rem !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
          background: var(--panel2) !important;
          border: 2px solid var(--border) !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] > label:hover > div:first-child {
          border-color: var(--accent) !important;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] > label[data-baseweb="radio"] input:checked + div {
          background: var(--accent) !important;
          border-color: var(--accent) !important;
        }

        /* ===== TOGGLE/SWITCH ===== */
        div[data-testid="stToggle"] label {
          color: var(--text) !important;
        }
        div[data-testid="stToggle"] div[data-baseweb="toggle"] {
          background: var(--border) !important;
        }
        div[data-testid="stToggle"] div[data-baseweb="toggle"][aria-checked="true"] {
          background: var(--accent) !important;
        }

        /* ===== SLIDER ===== */
        div[data-testid="stSlider"] label {
          color: var(--muted) !important;
          font-size: 0.8rem !important;
        }
        div[data-testid="stSlider"] [data-baseweb="slider"] > div:first-child {
          background: var(--border) !important;
        }
        div[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
          background: var(--accent) !important;
          border: 2px solid var(--accent) !important;
        }
        div[data-testid="stSlider"] [data-baseweb="slider"] > div > div {
          background: var(--accent) !important;
        }

        /* ===== DATAFRAMES ===== */
        div[data-testid="stDataFrame"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 4px !important;
        }
        div[data-testid="stDataFrame"] * {
          color: var(--text) !important;
          font-family: var(--mono) !important;
          font-size: 0.8rem !important;
        }

        /* ===== EXPANDERS ===== */
        div[data-testid="stExpander"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
        }
        div[data-testid="stExpander"] summary {
          color: var(--text) !important;
          font-weight: 500 !important;
        }
        div[data-testid="stExpander"] summary:hover {
          color: var(--accent) !important;
        }

        /* ===== METRICS ===== */
        div[data-testid="stMetric"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          padding: 0.75rem !important;
        }
        div[data-testid="stMetric"] label {
          color: var(--muted) !important;
          font-family: var(--mono) !important;
          font-size: 0.72rem !important;
          text-transform: uppercase !important;
          letter-spacing: 0.05em !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
          color: var(--text) !important;
          font-family: var(--mono) !important;
          font-size: 1.3rem !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
          font-family: var(--mono) !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg {
          display: none;
        }

        /* ===== ALERTS/INFO BOXES ===== */
        div[data-testid="stAlert"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 10px !important;
          color: var(--text) !important;
        }

        /* ===== PROGRESS BAR ===== */
        div[data-testid="stProgress"] > div > div {
          background: var(--accent) !important;
          border-radius: 4px !important;
        }

        /* ===== SPINNER ===== */
        .stSpinner > div {
          border-top-color: var(--accent) !important;
        }

        /* ===== TOOLTIPS ===== */
        div[data-baseweb="tooltip"] {
          background: var(--panel) !important;
          border: 1px solid var(--border) !important;
          border-radius: 6px !important;
          color: var(--text) !important;
        }

        /* ===== LINKS ===== */
        a { color: var(--cyan) !important; text-decoration: none; }
        a:hover { text-decoration: underline; color: var(--accent) !important; }

        /* ===== DIVIDER ===== */
        hr { border-color: var(--border) !important; }

        /* ===== CODE ===== */
        code {
          background: var(--panel2) !important;
          color: var(--accent) !important;
          border: 1px solid var(--border) !important;
          border-radius: 4px !important;
          padding: 0.15rem 0.35rem !important;
          font-family: var(--mono) !important;
        }
        pre {
          background: var(--panel2) !important;
          border: 1px solid var(--border) !important;
          border-radius: 8px !important;
        }

        /* ===== CUSTOM CARD CLASSES ===== */
        .mt-card {
          background: linear-gradient(180deg, var(--panel), var(--panel2));
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 1rem;
          box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
        .mt-title {
          font-family: var(--mono);
          font-size: 0.7rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--muted);
          margin-bottom: 0.4rem;
        }
        .mt-kpi {
          font-family: var(--mono);
          font-size: 1.4rem;
          font-weight: 600;
          color: var(--text);
          line-height: 1.2;
        }
        .mt-sub {
          font-family: var(--mono);
          font-size: 0.75rem;
          color: var(--muted);
          margin-top: 0.3rem;
        }

        /* ===== BADGES ===== */
        .mt-badge {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          padding: 0.2rem 0.6rem;
          border-radius: 999px;
          border: 1px solid var(--border);
          font-family: var(--mono);
          font-size: 0.72rem;
          color: var(--muted);
          background: rgba(17,24,39,0.4);
        }
        .mt-badge.ok { border-color: rgba(34,197,94,0.5); color: var(--green); }
        .mt-badge.warn { border-color: rgba(251,191,36,0.5); color: var(--accent); }
        .mt-badge.err { border-color: rgba(239,68,68,0.5); color: var(--red); }

        /* ===== STATUS CLASSES ===== */
        .status-running { color: var(--cyan) !important; font-weight: 600; }
        .status-completed { color: var(--green) !important; font-weight: 600; }
        .status-failed { color: var(--red) !important; font-weight: 600; }
        .status-pending { color: var(--accent) !important; font-weight: 600; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# Apply themes
apply_modern_terminal_css()
apply_modern_terminal_plotly()


# --- Helper Functions ---

def kpi_card(title: str, value: str, sub: str = ""):
    """Render a styled KPI card with modern terminal theme."""
    st.markdown(
        f"""
        <div class="mt-card">
          <div class="mt-title">{title}</div>
          <div class="mt-kpi">{value}</div>
          <div class="mt-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def api_request(method: str, endpoint: str, timeout: int = 30, **kwargs) -> dict:
    """Make an API request and handle errors."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.HTTPError as e:
        return None
    except Exception as e:
        return None


def format_datetime(dt_str: str) -> str:
    """Format ISO datetime string for display."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if not seconds:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def get_status_emoji(status: str) -> str:
    """Get emoji for status."""
    emojis = {
        "pending": "⏳",
        "running": "🔄",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "🚫",
        "skipped": "⏭️",
    }
    return emojis.get(status.lower(), "❓")


# --- Run Tab ---

def render_run_tab():
    """Render the Run tab with profile selection."""
    st.header("Start New Pipeline Run")

    # Fetch available profiles
    profiles_data = api_request("GET", "/runs/profiles")

    if not profiles_data:
        st.error("Cannot connect to API. Please ensure the server is running.")
        return

    profiles = {p["name"]: p for p in profiles_data.get("profiles", [])}

    # Profile selection with descriptions
    st.subheader("Select Run Profile")

    profile_cols = st.columns(3)

    selected_profile = st.session_state.get("selected_profile", "standard")

    for idx, (name, config) in enumerate(profiles.items()):
        with profile_cols[idx]:
            is_selected = name == selected_profile
            border_color = "#1f77b4" if is_selected else "#ddd"

            # Profile card
            st.markdown(f"""
            <div style="border: 2px solid {border_color}; padding: 15px; border-radius: 10px; margin: 5px 0;">
                <h4 style="margin: 0;">{name.title()}</h4>
                <p style="color: #666; margin: 5px 0;">{config['description']}</p>
                <ul style="margin: 5px 0; padding-left: 20px;">
                    <li>Samples: {config['sample_size']:,}</li>
                    <li>Epochs: {config['epochs']}</li>
                    <li>Threshold: {config['threshold']}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"Select {name.title()}", key=f"select_{name}",
                        type="primary" if is_selected else "secondary"):
                st.session_state["selected_profile"] = name
                st.rerun()

    # Warning for heavy profile
    if selected_profile == "heavy":
        st.warning("**Heavy profile requires 12GB+ VRAM.** Make sure your system has sufficient resources.")

    # Data source selection
    st.divider()
    st.subheader("Data Source")

    data_source = st.radio(
        "Select dataset",
        options=["demo-data", "saml-d"],
        format_func=lambda x: {
            "demo-data": "Demo Data  —  local demodata/ (small synthetic dataset)",
            "saml-d": "SAML-D  —  /mnt/e/xx/demodata/ (9.5M real transactions)",
        }[x],
        horizontal=True,
        key="data_source_select",
    )

    custom_data_path = None
    with st.expander("Custom data path (optional)"):
        custom_data_path = st.text_input(
            "Override data path",
            value="",
            placeholder="/path/to/your/demodata/",
            help="Leave empty to use the default path for the selected data source",
        )
        if custom_data_path:
            st.info(f"Custom path: `{custom_data_path}`")

    # Additional options
    st.divider()
    st.subheader("Additional Options")

    col1, col2, col3 = st.columns(3)

    with col1:
        skip_hp = st.checkbox("Skip HP tuning", value=True,
                             help="Use cached hyperparameters (faster)")
    with col2:
        gen_viz = st.checkbox("Generate visualizations", value=True)
    with col3:
        gen_report = st.checkbox("Generate report", value=True)

    # Custom overrides (expandable)
    with st.expander("Advanced: Custom Parameters"):
        custom_col1, custom_col2, custom_col3 = st.columns(3)
        with custom_col1:
            custom_sample = st.number_input("Sample size override", min_value=1000, max_value=1000000,
                                           value=None, help="Leave empty to use profile default")
        with custom_col2:
            custom_epochs = st.number_input("Epochs override", min_value=1, max_value=100,
                                           value=None, help="Leave empty to use profile default")
        with custom_col3:
            custom_timeout = st.number_input("Notebook timeout (seconds)", min_value=60, max_value=7200,
                                            value=1800, help="Max time per notebook")

    # Start button
    st.divider()

    if st.button("🚀 Start Pipeline Run", type="primary", width="stretch"):
        with st.spinner("Starting pipeline run..."):
            params = {
                "profile": selected_profile,
                "data_source": data_source,
                "skip_hyperparameter_tuning": skip_hp,
                "generate_visualizations": gen_viz,
                "generate_report": gen_report,
                "notebook_timeout": custom_timeout,
            }

            # Add data path override if specified
            if custom_data_path:
                params["data_path"] = custom_data_path

            # Add custom overrides if specified
            if custom_sample:
                params["sample_size"] = custom_sample
            if custom_epochs:
                params["epochs"] = custom_epochs

            result = api_request("POST", "/runs/", json=params)

            if result:
                st.success(f"Pipeline run started! Run ID: `{result['run_id']}`")
                st.session_state["active_run_id"] = result["run_id"]
                st.balloons()
                st.info("Switch to the **Status** tab to monitor progress.")
            else:
                st.error("Failed to start pipeline. Check if the API and Celery worker are running.")

    # Recent runs
    st.divider()
    st.subheader("Recent Runs")

    runs = api_request("GET", "/runs/?limit=5")
    if runs:
        for run in runs:
            status = run["status"]
            emoji = get_status_emoji(status)

            col1, col2, col3, col4, col5 = st.columns([3, 1.5, 2, 1.5, 1])
            with col1:
                st.markdown(f"`{run['id'][:12]}...`")
            with col2:
                st.markdown(f"{emoji} **{status.upper()}**")
            with col3:
                st.markdown(format_datetime(run["created_at"]))
            with col4:
                st.markdown(f"{run['progress_percent']:.0f}%")
            with col5:
                if st.button("View", key=f"view_{run['id']}"):
                    st.session_state["active_run_id"] = run["id"]
                    st.rerun()
    else:
        st.info("No runs yet. Start your first pipeline run above!")


# --- Status Tab ---

def render_status_tab():
    """Render the Status tab with auto-refresh."""
    st.header("Pipeline Status")

    # Run selector
    runs = api_request("GET", "/runs/?limit=20")
    if not runs:
        st.info("No pipeline runs found. Start a new run from the Run tab.")
        return

    run_options = {f"{r['id'][:8]}... ({r['status']}) - {format_datetime(r['created_at'])}": r["id"] for r in runs}

    # Use active run if set
    default_idx = 0
    if "active_run_id" in st.session_state:
        for idx, (label, rid) in enumerate(run_options.items()):
            if rid == st.session_state["active_run_id"]:
                default_idx = idx
                break

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), index=default_idx)
    selected_run_id = run_options[selected_label]
    st.session_state["active_run_id"] = selected_run_id

    # Fetch detailed status
    status_data = api_request("GET", f"/status/{selected_run_id}")
    if not status_data:
        st.error("Could not fetch run status")
        return

    status = status_data["status"]

    # Status overview cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        emoji = get_status_emoji(status)
        st.metric("Status", f"{emoji} {status.upper()}")
    with col2:
        st.metric("Progress", f"{status_data['progress_percent']:.1f}%")
    with col3:
        st.metric("Step", f"{status_data['current_step']}/{status_data['total_steps']}")
    with col4:
        st.metric("Current", status_data["current_step_name"][:18] + "..." if len(status_data["current_step_name"]) > 18 else status_data["current_step_name"])

    # Progress bar (clamp to valid range 0.0–1.0)
    st.progress(max(0.0, min(1.0, status_data["progress_percent"] / 100)))

    # Auto-refresh indicator for running jobs
    if status == "running":
        st.info(f"🔄 Run in progress. Auto-refreshing every {POLL_INTERVAL} seconds...")

    # Timing info
    st.divider()
    time_col1, time_col2, time_col3 = st.columns(3)
    with time_col1:
        st.markdown(f"**Created:** {format_datetime(status_data['created_at'])}")
    with time_col2:
        st.markdown(f"**Started:** {format_datetime(status_data['started_at'])}")
    with time_col3:
        st.markdown(f"**Completed:** {format_datetime(status_data['completed_at'])}")

    # Step details table
    st.divider()
    st.subheader("Pipeline Steps")

    if status_data.get("steps"):
        steps_df = pd.DataFrame(status_data["steps"])
        steps_df["Status"] = steps_df["status"].apply(lambda x: f"{get_status_emoji(x)} {x}")
        steps_df = steps_df.rename(columns={"step_number": "Step", "step_name": "Name"})

        st.dataframe(
            steps_df[["Step", "Name", "Status"]],
            width="stretch",
            hide_index=True,
        )

    # Error display
    if status_data.get("error_message"):
        st.error(f"**Error:** {status_data['error_message']}")

    # Action buttons
    st.divider()
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if status in ["pending", "running"]:
            if st.button("🚫 Cancel Run", type="secondary"):
                result = api_request("POST", f"/runs/{selected_run_id}/cancel")
                if result:
                    st.success("Run cancelled")
                    st.rerun()

    with btn_col2:
        if st.button("🔄 Refresh Now"):
            st.rerun()

    with btn_col3:
        if status == "completed":
            if st.button("📊 View Dashboard"):
                st.session_state["dashboard_run_id"] = selected_run_id

    # Auto-refresh for running jobs
    if status == "running":
        time.sleep(POLL_INTERVAL)
        st.rerun()


# --- Dashboard Tab ---

def render_dashboard_tab():
    """Render the Dashboard tab with visualizations and data tables."""
    st.header("Analytics Dashboard")

    # Run selector - show all runs, not just completed
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found.")
        return

    # Filter to show completed runs first
    completed_runs = [r for r in runs if r["status"] == "completed"]
    other_runs = [r for r in runs if r["status"] != "completed"]
    sorted_runs = completed_runs + other_runs

    run_options = {
        f"{r['id'][:8]}... ({r['status']}) - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in sorted_runs
    }

    # Use dashboard_run_id if set
    default_idx = 0
    if "dashboard_run_id" in st.session_state:
        for idx, (label, rid) in enumerate(run_options.items()):
            if rid == st.session_state["dashboard_run_id"]:
                default_idx = idx
                break

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), index=default_idx,
                                  key="dashboard_run_select")
    selected_run_id = run_options[selected_label]

    # Fetch run info, summary and metrics
    run_info = api_request("GET", f"/runs/{selected_run_id}")
    summary = api_request("GET", f"/artifacts/{selected_run_id}/summary")
    metrics = api_request("GET", f"/runs/{selected_run_id}/metrics")

    if not summary:
        st.warning("Could not fetch run summary")
        return

    # KPI Cards at top (status, progress, num_flagged, threshold) - Bloomberg style
    st.subheader("Run Overview")
    kpi_cols = st.columns(4)

    with kpi_cols[0]:
        status = run_info.get("status", "unknown") if run_info else "unknown"
        emoji = get_status_emoji(status)
        status_color = "#22D3EE" if status == "running" else "#00C853" if status == "completed" else "#FF5252" if status == "failed" else "#FFB000"
        run_params = run_info.get("params", {}) if run_info else {}
        ds_label = run_params.get("data_source", "demo-data").upper()
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div style="font-size: 2rem;">{emoji}</div>
            <div class="mt-kpi" style="color: {status_color};">{status.upper()}</div>
            <div class="mt-title">Status</div>
            <div class="mt-sub">Dataset: {ds_label}</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_cols[1]:
        progress = run_info.get("progress_percent", 0) if run_info else 0
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div class="mt-kpi" style="color: #00C853;">{progress:.0f}%</div>
            <div class="mt-title">Progress</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_cols[2]:
        num_flagged = "N/A"
        if metrics and metrics.get("anomalies", {}).get("num_flagged") is not None:
            num_flagged = f"{metrics['anomalies']['num_flagged']:,}"
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div class="mt-kpi" style="color: #FF5252;">{num_flagged}</div>
            <div class="mt-title">Flagged Anomalies</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_cols[3]:
        threshold = "N/A"
        if metrics and metrics.get("anomalies", {}).get("threshold") is not None:
            threshold = f"{metrics['anomalies']['threshold']:.4f}"
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div class="mt-kpi" style="color: #FFB000;">{threshold}</div>
            <div class="mt-title">Threshold</div>
        </div>
        """, unsafe_allow_html=True)

    # Key metrics row
    st.divider()
    st.subheader("Key Metrics")
    metric_cols = st.columns(5)

    results = summary.get("results", {})
    with metric_cols[0]:
        st.metric("Total Nodes", f"{results.get('total_nodes') or 'N/A':,}" if results.get('total_nodes') else "N/A")
    with metric_cols[1]:
        st.metric("Transactions", f"{results.get('total_transactions') or 'N/A':,}" if results.get('total_transactions') else "N/A")
    with metric_cols[2]:
        st.metric("Anomalies", f"{results.get('anomalies_detected') or 'N/A':,}" if results.get('anomalies_detected') else "N/A")
    with metric_cols[3]:
        if metrics and metrics.get("anomalies", {}).get("anomaly_rate"):
            st.metric("Anomaly Rate", f"{metrics['anomalies']['anomaly_rate']}%")
        else:
            st.metric("Anomaly Rate", "N/A")
    with metric_cols[4]:
        artifacts = summary.get("artifacts", {})
        st.metric("Artifacts", artifacts.get("total_files", 0))

    # Detailed metrics from metrics.json
    if metrics and not metrics.get("status") == "metrics_not_available":
        st.divider()
        st.subheader("Detailed Metrics")

        detail_tabs = st.tabs(["Dataset", "Training", "Anomalies", "Embedding"])

        with detail_tabs[0]:
            dataset = metrics.get("dataset", {})
            if dataset:
                ds_col1, ds_col2, ds_col3 = st.columns(3)
                with ds_col1:
                    st.metric("Transactions", f"{dataset.get('num_transactions') or 'N/A':,}" if dataset.get('num_transactions') else "N/A")
                with ds_col2:
                    st.metric("Accounts", f"{dataset.get('num_accounts') or 'N/A':,}" if dataset.get('num_accounts') else "N/A")
                with ds_col3:
                    if dataset.get("data_files"):
                        st.metric("Data Files", len(dataset["data_files"]))

        with detail_tabs[1]:
            training = metrics.get("training", {})
            if training:
                tr_col1, tr_col2, tr_col3, tr_col4 = st.columns(4)
                with tr_col1:
                    st.metric("Epochs", training.get("epochs") or "N/A")
                with tr_col2:
                    if training.get("final_loss"):
                        st.metric("Final Loss", f"{training['final_loss']:.6f}")
                    else:
                        st.metric("Final Loss", "N/A")
                with tr_col3:
                    st.metric("Duration", format_duration(training.get("duration_seconds")))
                with tr_col4:
                    if training.get("threshold"):
                        st.metric("Threshold", f"{training['threshold']:.4f}")
                    else:
                        st.metric("Threshold", "N/A")

                # Show model path and files
                if training.get("model_path"):
                    st.markdown(f"**Model Path:** `{training['model_path']}`")
                if training.get("model_files"):
                    st.markdown(f"**Model Files:** {', '.join(training['model_files'])}")

        with detail_tabs[2]:
            anomalies = metrics.get("anomalies", {})
            if anomalies:
                an_col1, an_col2, an_col3, an_col4 = st.columns(4)
                with an_col1:
                    st.metric("Flagged", f"{anomalies.get('num_flagged') or 'N/A':,}" if anomalies.get('num_flagged') else "N/A")
                with an_col2:
                    if anomalies.get("threshold"):
                        st.metric("Threshold", f"{anomalies['threshold']:.6f}")
                    else:
                        st.metric("Threshold", "N/A")
                with an_col3:
                    st.metric("Anomaly Rate (Table)", f"{anomalies.get('anomaly_rate') or 'N/A'}%")
                with an_col4:
                    if anomalies.get("anomaly_rate_nodes_pct") is not None:
                        st.metric("Rate (All Nodes)", f"{anomalies['anomaly_rate_nodes_pct']:.2f}%")
                    else:
                        st.metric("Rate (All Nodes)", "N/A")

        with detail_tabs[3]:
            embedding = metrics.get("embedding", {})
            if embedding:
                emb_col1, emb_col2, emb_col3 = st.columns(3)
                with emb_col1:
                    st.metric("Dimensions", embedding.get("dim") or "N/A")
                with emb_col2:
                    st.metric("Nodes", f"{embedding.get('num_nodes') or 'N/A':,}" if embedding.get('num_nodes') else "N/A")
                with emb_col3:
                    st.metric("Edges", f"{embedding.get('num_edges') or 'N/A':,}" if embedding.get('num_edges') else "N/A")

    # Debug paths expander (for development/troubleshooting)
    with st.expander("🔧 Debug: Artifact Paths", expanded=False):
        paths_data = api_request("GET", f"/runs/{selected_run_id}/paths")
        if paths_data:
            st.markdown("**Explicit artifact paths from metrics.json:**")

            path_cols = st.columns(2)
            with path_cols[0]:
                st.markdown("**Anomalies Table:**")
                st.code(paths_data.get("anomalies_table_path") or "Not found")

                st.markdown("**Model Path:**")
                st.code(paths_data.get("model_path") or "Not found")

                st.markdown("**Model Files:**")
                model_files = paths_data.get("model_files", [])
                if model_files:
                    for f in model_files:
                        st.text(f"  • {f}")
                else:
                    st.text("  No model files found")

            with path_cols[1]:
                st.markdown("**Report Path:**")
                st.code(paths_data.get("report_path") or "Not found")

                st.markdown("**Bundle Path:**")
                st.code(paths_data.get("bundle_path") or "Not found")

                st.markdown("**Key Plots:**")
                key_plots = paths_data.get("key_plots_paths", [])
                if key_plots:
                    for p in key_plots[:6]:  # Show first 6
                        st.text(f"  • {p}")
                    if len(key_plots) > 6:
                        st.text(f"  ... and {len(key_plots) - 6} more")
                else:
                    st.text("  No key plots found")

            st.markdown("**Base Artifacts Directory:**")
            st.code(paths_data.get("artifacts_base") or "N/A")
        else:
            st.warning("Could not fetch paths data")

    # Visualizations
    st.divider()
    st.subheader("Visualizations")

    # Get the styled plots toggle state
    show_styled = st.session_state.get("show_styled_plots", True)

    # Fetch all plots first to check if styled versions exist
    plots = api_request("GET", f"/artifacts/{selected_run_id}/plots")
    original_plots = plots.get("plots", []) if plots else []

    # Check for styled plots in the artifact index
    artifact_index = api_request("GET", f"/artifacts/{selected_run_id}")
    styled_plots = []
    has_styled = False

    if artifact_index and artifact_index.get("artifacts"):
        styled_plots = [a for a in artifact_index["artifacts"] if "plots/styled" in a.get("path", "")]
        has_styled = len(styled_plots) > 0

    # Determine which plots to show
    if show_styled and has_styled:
        plot_list = styled_plots
        plot_type_label = "Bloomberg-styled"
    else:
        plot_list = original_plots
        plot_type_label = "Original"

    if plot_list:
        # Show info with plot type indicator
        info_msg = f"Found {len(plot_list)} {plot_type_label.lower()} visualization(s)"
        if has_styled:
            info_msg += f" | {'Styled' if show_styled else 'Original'} view"
        st.info(info_msg)

        # Create a grid of plots
        cols_per_row = 2
        for i in range(0, len(plot_list), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                if i + j < len(plot_list):
                    plot = plot_list[i + j]
                    with col:
                        st.markdown(f"**{plot['name']}**")
                        img_url = f"{API_BASE_URL}/artifacts/{selected_run_id}/file/{plot['path']}"
                        try:
                            response = requests.get(img_url, timeout=10)
                            if response.status_code == 200:
                                st.image(response.content, width="stretch")
                        except:
                            st.warning(f"Could not load: {plot['name']}")
    else:
        st.info("No visualizations available for this run.")

    # Anomalies data table
    st.divider()
    st.subheader("Anomaly Data")

    # First try to get alert_nodes_td.csv via the table endpoint (preferred)
    table_data = api_request("GET", f"/artifacts/{selected_run_id}/table/alert_nodes_td.csv?limit=500")

    if table_data and table_data.get("data"):
        st.info(f"📋 **Primary source: alert_nodes_td.csv** | Showing {len(table_data['data'])} of {table_data['total_rows']} rows")

        df = pd.DataFrame(table_data["data"])
        original_df = df.copy()

        # Quick filters in expandable section
        with st.expander("🔍 Quick Filters", expanded=True):
            filter_cols = st.columns(4)

            # is_sar filter (if column exists)
            with filter_cols[0]:
                if "is_sar" in df.columns:
                    sar_options = ["All", "SAR Only (1)", "Non-SAR Only (0)"]
                    sar_filter = st.selectbox("SAR Status", sar_options, key="sar_filter")
                    if sar_filter == "SAR Only (1)":
                        df = df[df["is_sar"] == 1]
                    elif sar_filter == "Non-SAR Only (0)":
                        df = df[df["is_sar"] == 0]

            # Score filter (if column exists)
            with filter_cols[1]:
                score_col = None
                for col in ["score", "anomaly_score", "risk_score"]:
                    if col in df.columns:
                        score_col = col
                        break
                if score_col:
                    min_score = st.slider("Min Score", 0.0, 1.0, 0.0, key="min_score_filter")
                    df = df[df[score_col] >= min_score]

            # ID search (if column exists)
            with filter_cols[2]:
                if "id" in df.columns:
                    id_search = st.text_input("Search ID", key="id_search")
                    if id_search:
                        df = df[df["id"].astype(str).str.contains(id_search, case=False, na=False)]

            # Column selector
            with filter_cols[3]:
                available_cols = df.columns.tolist()
                default_cols = [c for c in ["id", "type", "is_sar", "score", "amount", "degree", "risk"] if c in available_cols]
                if not default_cols:
                    default_cols = available_cols[:5]

        # Show filter stats
        if len(df) != len(original_df):
            st.caption(f"Filtered: {len(df)} rows (from {len(original_df)} total)")

        # Column selector outside expander
        show_cols = st.multiselect("Display Columns", available_cols,
                                  default=default_cols if default_cols else available_cols[:5],
                                  key="show_cols_select")

        # Display table
        if show_cols and len(df) > 0:
            st.dataframe(df[show_cols], width="stretch", hide_index=True)

            # Download buttons
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                csv = df[show_cols].to_csv(index=False)
                st.download_button(
                    label="📥 Download Filtered CSV",
                    data=csv,
                    file_name=f"alert_nodes_{selected_run_id[:8]}.csv",
                    mime="text/csv",
                )
            with btn_col2:
                full_csv = original_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Full Table",
                    data=full_csv,
                    file_name=f"alert_nodes_full_{selected_run_id[:8]}.csv",
                    mime="text/csv",
                )
        elif len(df) == 0:
            st.warning("No records match the current filters.")
    else:
        # Fallback to the anomalies endpoint
        anomalies_data = api_request("GET", f"/artifacts/{selected_run_id}/anomalies?limit=100")

        if anomalies_data and anomalies_data.get("anomalies"):
            st.info(f"Showing top {anomalies_data['returned_count']} anomalies out of {anomalies_data['total_records']} total records")

            # Convert to dataframe
            df = pd.DataFrame(anomalies_data["anomalies"])

            # Add filter controls
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                if anomalies_data.get("score_column") in df.columns:
                    min_score = st.slider("Minimum Score", 0.0, 1.0, 0.0)
                    df = df[df[anomalies_data["score_column"]] >= min_score]
            with filter_col2:
                show_cols = st.multiselect("Show Columns", df.columns.tolist(),
                                          default=df.columns.tolist()[:6])

            # Display table
            if show_cols:
                st.dataframe(df[show_cols], width="stretch", hide_index=True)

                # Download button
                csv = df[show_cols].to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"anomalies_{selected_run_id[:8]}.csv",
                    mime="text/csv",
                )
        else:
            st.info("No anomaly data available for this run.")


# --- Report Tab ---

def render_report_tab():
    """Render the Report tab."""
    st.header("Run Reports")

    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]

    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view reports.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r['completed_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), key="report_run_select")
    selected_run_id = run_options[selected_label]

    # Get report metadata
    report_meta = api_request("GET", f"/artifacts/{selected_run_id}/report?format=json")

    if report_meta and report_meta.get("status") != "report_not_generated":
        st.success("✅ Report available!")

        # Metadata display
        meta_col1, meta_col2 = st.columns(2)
        with meta_col1:
            st.markdown(f"**Run ID:** `{report_meta.get('run_id', 'N/A')}`")
            st.markdown(f"**Generated:** {report_meta.get('generated_at', 'N/A')}")
        with meta_col2:
            st.markdown(f"**Status:** {report_meta.get('status', 'N/A')}")
            metrics = report_meta.get("metrics", {})
            if metrics.get("anomalies_detected"):
                st.markdown(f"**Anomalies:** {metrics['anomalies_detected']:,}")

        # Action buttons
        st.divider()
        report_url = f"{API_BASE_URL}/artifacts/{selected_run_id}/report?format=html"
        bundle_url = f"{API_BASE_URL}/artifacts/{selected_run_id}/bundle"

        btn_col1, btn_col2, btn_col3 = st.columns(3)
        with btn_col1:
            st.link_button("🔗 Open in Browser", report_url, width="stretch")
        with btn_col2:
            try:
                response = requests.get(report_url, timeout=15)
                if response.status_code == 200:
                    st.download_button(
                        label="📥 Download HTML",
                        data=response.content,
                        file_name=f"aml_report_{selected_run_id[:8]}.html",
                        mime="text/html",
                        width="stretch",
                    )
            except:
                st.warning("Could not fetch report")
        with btn_col3:
            try:
                bundle_response = requests.get(bundle_url, timeout=30)
                if bundle_response.status_code == 200:
                    st.download_button(
                        label="📦 Download Run Bundle",
                        data=bundle_response.content,
                        file_name=f"aml_run_{selected_run_id[:8]}_bundle.zip",
                        mime="application/zip",
                        width="stretch",
                        help="ZIP containing metrics, report, alert data, and key plots"
                    )
                else:
                    st.button("📦 Bundle N/A", disabled=True, width="stretch",
                             help="Run bundle not available for this run")
            except Exception as e:
                st.button("📦 Bundle N/A", disabled=True, width="stretch")

        # Inline preview
        st.divider()
        st.subheader("Report Preview")

        try:
            response = requests.get(report_url, timeout=15)
            if response.status_code == 200:
                st.components.v1.html(response.text, height=800, scrolling=True)
        except Exception as e:
            st.warning(f"Could not load report preview: {e}")

    else:
        st.warning("Report not generated for this run.")
        st.markdown("""
        Reports are generated when a pipeline run completes with the "Generate report" option enabled.

        **Report contents:**
        - Run summary and metrics
        - Dataset overview
        - Anomaly detection results
        - Visualizations
        - Detection rules
        """)


# --- Analytics (Interactive) Tab ---

def render_analytics_tab():
    """Render the Analytics (Interactive) tab with Plotly charts."""
    st.header("Analytics (Interactive)")

    # Run selector
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view analytics.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), key="analytics_run_select")
    selected_run_id = run_options[selected_label]

    # Resolve artifact path from the run record (handles SAML-D custom paths)
    run_info = api_request("GET", f"/runs/{selected_run_id}")
    if run_info and run_info.get("artifact_path"):
        artifact_path = Path(run_info["artifact_path"])
        if not artifact_path.is_absolute():
            artifact_path = (get_repo_root() / artifact_path).resolve()
        run_dir = artifact_path
    else:
        run_dir = get_run_dir(selected_run_id)
    data_dir = run_dir / "data"

    # Load data files
    alert_nodes_path = data_dir / "alert_nodes_td.csv"
    node_td_path = data_dir / "node_td.csv"
    edges_td_path = data_dir / "edges_td.csv"
    embeddings_path = data_dir / "node_embeddings_fg.parquet"
    rules_path = data_dir / "aml_rules.json"

    # Load alert_nodes_td.csv (required)
    if not alert_nodes_path.exists():
        st.warning(f"alert_nodes_td.csv not found at: `data/alert_nodes_td.csv`")
        return

    try:
        alert_df = pd.read_csv(alert_nodes_path)
    except Exception as e:
        st.error(f"Failed to load alert_nodes_td.csv: {e}")
        return

    # Load optional files
    node_df = None
    edges_df = None
    embeddings_df = None
    rules_data = None

    if node_td_path.exists():
        try:
            node_df = pd.read_csv(node_td_path)
        except Exception as e:
            st.warning(f"Could not load node_td.csv: {e}")

    if edges_td_path.exists():
        try:
            edges_df = pd.read_csv(edges_td_path)
        except Exception as e:
            st.warning(f"Could not load edges_td.csv: {e}")

    if embeddings_path.exists():
        try:
            embeddings_df = pd.read_parquet(embeddings_path)
        except Exception as e:
            st.warning(f"Could not load node_embeddings_fg.parquet: {e}")

    if rules_path.exists():
        try:
            with open(rules_path) as f:
                rules_data = json.load(f)
        except Exception as e:
            st.warning(f"Could not load aml_rules.json: {e}")

    # --- Sidebar Filters ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Analytics Filters")

    # SAR filter
    sar_filter = st.sidebar.radio(
        "SAR Status",
        options=["All", "SAR Only", "Non-SAR Only"],
        key="analytics_sar_filter"
    )

    # Type multiselect (if type column exists)
    type_col = None
    for col in ["type", "node_type", "account_type", "party_type"]:
        if col in alert_df.columns:
            type_col = col
            break

    selected_types = None
    if type_col:
        unique_types = alert_df[type_col].dropna().unique().tolist()
        selected_types = st.sidebar.multiselect(
            "Filter by Type",
            options=unique_types,
            default=unique_types,
            key="analytics_type_filter"
        )

    # ID search substring
    id_search = st.sidebar.text_input("Search ID (substring)", key="analytics_id_search")

    # Deduplicate toggle
    deduplicate = st.sidebar.checkbox("Deduplicate IDs", value=False, key="analytics_deduplicate")

    # --- Apply Filters ---
    filtered_df = alert_df.copy()

    # SAR filter
    if "is_sar" in filtered_df.columns:
        if sar_filter == "SAR Only":
            filtered_df = filtered_df[filtered_df["is_sar"] == 1]
        elif sar_filter == "Non-SAR Only":
            filtered_df = filtered_df[filtered_df["is_sar"] == 0]

    # Type filter
    if type_col and selected_types is not None:
        filtered_df = filtered_df[filtered_df[type_col].isin(selected_types)]

    # ID search
    if id_search and "id" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["id"].astype(str).str.contains(id_search, case=False, na=False)]

    # Deduplicate
    if deduplicate and "id" in filtered_df.columns:
        filtered_df = filtered_df.drop_duplicates(subset=["id"], keep="first")

    # Show filter stats
    st.info(f"Showing {len(filtered_df):,} of {len(alert_df):,} records after filtering")

    # --- Charts ---
    chart_tabs = st.tabs(["SAR Overview", "Type Analysis", "Degree Analysis", "Embeddings PCA"])

    # --- Tab 1: SAR Overview ---
    with chart_tabs[0]:
        st.subheader("SAR vs Non-SAR Distribution")

        if "is_sar" in filtered_df.columns:
            sar_counts = filtered_df["is_sar"].value_counts().reset_index()
            sar_counts.columns = ["is_sar", "count"]
            sar_counts["label"] = sar_counts["is_sar"].map({1: "SAR", 0: "Non-SAR"})

            fig_donut = px.pie(
                sar_counts,
                values="count",
                names="label",
                title="SAR vs Non-SAR Distribution",
                hole=0.4,
                color="label",
                color_discrete_map={"SAR": "#d62728", "Non-SAR": "#2ca02c"},
            )
            fig_donut.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>Count: %{value:,}<br>Percent: %{percent}<extra></extra>"
            )
            st.plotly_chart(fig_donut, width="stretch")
        else:
            st.warning("is_sar column not found in data")

    # --- Tab 2: Type Analysis ---
    with chart_tabs[1]:
        st.subheader("Type Distribution Analysis")

        if type_col and "is_sar" in filtered_df.columns:
            # Top 30 types by count, split by is_sar
            type_sar_counts = filtered_df.groupby([type_col, "is_sar"]).size().reset_index(name="count")
            type_totals = type_sar_counts.groupby(type_col)["count"].sum().sort_values(ascending=False)
            top_30_types = type_totals.head(30).index.tolist()
            type_sar_filtered = type_sar_counts[type_sar_counts[type_col].isin(top_30_types)]
            type_sar_filtered["sar_label"] = type_sar_filtered["is_sar"].map({1: "SAR", 0: "Non-SAR"})

            # Stacked bar chart
            fig_bar = px.bar(
                type_sar_filtered,
                x=type_col,
                y="count",
                color="sar_label",
                title=f"Top 30 Types by Count (Split by SAR Status)",
                barmode="stack",
                color_discrete_map={"SAR": "#d62728", "Non-SAR": "#2ca02c"},
                labels={type_col: "Type", "count": "Count", "sar_label": "Status"},
            )
            fig_bar.update_traces(
                hovertemplate="<b>Type:</b> %{x}<br><b>Count:</b> %{y:,}<extra></extra>"
            )
            fig_bar.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_bar, width="stretch")

            # Heatmap: type x SAR counts
            st.subheader("Type x SAR Heatmap")
            pivot_df = type_sar_filtered.pivot(index=type_col, columns="sar_label", values="count").fillna(0)

            fig_heatmap = px.imshow(
                pivot_df.values,
                x=pivot_df.columns.tolist(),
                y=pivot_df.index.tolist(),
                color_continuous_scale="Reds",
                title="Heatmap: Type x SAR Status",
                labels={"x": "SAR Status", "y": "Type", "color": "Count"},
                aspect="auto",
            )
            fig_heatmap.update_traces(
                hovertemplate="<b>Type:</b> %{y}<br><b>Status:</b> %{x}<br><b>Count:</b> %{z:,}<extra></extra>"
            )
            st.plotly_chart(fig_heatmap, width="stretch")
        elif type_col:
            st.warning("is_sar column not found for type analysis")
        else:
            st.warning("No type column found in data")

    # --- Tab 3: Degree Analysis ---
    with chart_tabs[2]:
        st.subheader("Node Degree Analysis")

        if edges_df is not None:
            # Compute degree from edges
            src_col = None
            dst_col = None
            for col in ["source", "src", "from", "sender"]:
                if col in edges_df.columns:
                    src_col = col
                    break
            for col in ["target", "dst", "to", "receiver"]:
                if col in edges_df.columns:
                    dst_col = col
                    break

            if src_col and dst_col:
                # Count degree (in + out)
                src_counts = edges_df[src_col].value_counts()
                dst_counts = edges_df[dst_col].value_counts()
                degree_df = pd.DataFrame({
                    "id": list(set(src_counts.index) | set(dst_counts.index))
                })
                degree_df["out_degree"] = degree_df["id"].map(src_counts).fillna(0).astype(int)
                degree_df["in_degree"] = degree_df["id"].map(dst_counts).fillna(0).astype(int)
                degree_df["degree"] = degree_df["out_degree"] + degree_df["in_degree"]

                # Merge with alert_df for type/is_sar info
                if "id" in filtered_df.columns:
                    degree_df = degree_df.merge(
                        filtered_df[["id"] + ([type_col] if type_col else []) + (["is_sar"] if "is_sar" in filtered_df.columns else [])].drop_duplicates(),
                        on="id",
                        how="left"
                    )

                # Histogram of degree
                fig_hist = px.histogram(
                    degree_df,
                    x="degree",
                    nbins=50,
                    title="Node Degree Distribution",
                    labels={"degree": "Degree", "count": "Count"},
                )
                fig_hist.update_traces(
                    hovertemplate="<b>Degree:</b> %{x}<br><b>Count:</b> %{y:,}<extra></extra>"
                )
                st.plotly_chart(fig_hist, width="stretch")

                # Top 20 nodes by degree
                st.subheader("Top 20 Nodes by Degree")
                top_20 = degree_df.nlargest(20, "degree")

                hover_cols = ["id", "degree"]
                if type_col and type_col in top_20.columns:
                    hover_cols.append(type_col)
                if "is_sar" in top_20.columns:
                    hover_cols.append("is_sar")

                custom_data = [top_20[col] for col in hover_cols[1:]]  # exclude id which is x

                fig_top_degree = px.bar(
                    top_20,
                    x="id",
                    y="degree",
                    title="Top 20 Nodes by Degree",
                    labels={"id": "Node ID", "degree": "Degree"},
                    color="degree",
                    color_continuous_scale="Blues",
                )

                # Build hover template
                hover_parts = ["<b>ID:</b> %{x}"]
                for i, col in enumerate(hover_cols[1:]):
                    hover_parts.append(f"<b>{col}:</b> %{{customdata[{i}]}}")
                hover_template = "<br>".join(hover_parts) + "<extra></extra>"

                fig_top_degree.update_traces(
                    customdata=np.stack(custom_data, axis=-1) if custom_data else None,
                    hovertemplate=hover_template
                )
                fig_top_degree.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_top_degree, width="stretch")
            else:
                st.warning(f"Could not identify source/target columns in edges_td.csv. Found: {edges_df.columns.tolist()}")
        else:
            st.warning("edges_td.csv not found - cannot compute node degrees")

    # --- Tab 4: Embeddings PCA ---
    with chart_tabs[3]:
        st.subheader("Embeddings PCA Visualization")

        if embeddings_df is not None:
            try:
                from sklearn.decomposition import PCA

                # Find embedding columns (emb_0, emb_1, ... or similar)
                emb_cols = [c for c in embeddings_df.columns if c.startswith("emb_")]
                if not emb_cols:
                    emb_cols = [c for c in embeddings_df.columns if c.startswith("embedding_")]
                if not emb_cols:
                    # Try numeric columns excluding known non-embedding ones
                    exclude = {"id", "is_sar", "type", "score", "amount", "degree"}
                    emb_cols = [c for c in embeddings_df.select_dtypes(include=[np.number]).columns if c not in exclude]

                if len(emb_cols) >= 2:
                    # Sample up to 5000 for performance
                    sample_size = min(5000, len(embeddings_df))
                    sample_df = embeddings_df.sample(n=sample_size, random_state=42) if len(embeddings_df) > sample_size else embeddings_df.copy()

                    # Apply filters from sidebar
                    if "is_sar" in sample_df.columns:
                        if sar_filter == "SAR Only":
                            sample_df = sample_df[sample_df["is_sar"] == 1]
                        elif sar_filter == "Non-SAR Only":
                            sample_df = sample_df[sample_df["is_sar"] == 0]

                    if type_col and type_col in sample_df.columns and selected_types:
                        sample_df = sample_df[sample_df[type_col].isin(selected_types)]

                    if id_search and "id" in sample_df.columns:
                        sample_df = sample_df[sample_df["id"].astype(str).str.contains(id_search, case=False, na=False)]

                    if len(sample_df) < 10:
                        st.warning("Not enough data points after filtering for PCA visualization")
                    else:
                        # PCA
                        X = sample_df[emb_cols].values
                        pca = PCA(n_components=2)
                        pca_result = pca.fit_transform(X)

                        sample_df = sample_df.copy()
                        sample_df["PCA1"] = pca_result[:, 0]
                        sample_df["PCA2"] = pca_result[:, 1]

                        # Prepare hover data
                        hover_data = {}
                        if "id" in sample_df.columns:
                            hover_data["id"] = True
                        if type_col and type_col in sample_df.columns:
                            hover_data[type_col] = True
                        if "is_sar" in sample_df.columns:
                            hover_data["is_sar"] = True

                        # Color by is_sar if available
                        color_col = None
                        color_map = None
                        if "is_sar" in sample_df.columns:
                            sample_df["sar_label"] = sample_df["is_sar"].map({1: "SAR", 0: "Non-SAR", None: "Unknown"})
                            color_col = "sar_label"
                            color_map = {"SAR": "#d62728", "Non-SAR": "#2ca02c", "Unknown": "#7f7f7f"}

                        fig_pca = px.scatter(
                            sample_df,
                            x="PCA1",
                            y="PCA2",
                            color=color_col,
                            color_discrete_map=color_map,
                            title=f"PCA Visualization of Embeddings (n={len(sample_df):,})",
                            hover_data=hover_data,
                            labels={"PCA1": f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
                                   "PCA2": f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)"},
                        )
                        fig_pca.update_traces(marker=dict(size=5, opacity=0.7))
                        fig_pca.update_layout(legend_title_text="SAR Status")
                        st.plotly_chart(fig_pca, width="stretch")

                        st.caption(f"Explained variance: PC1={pca.explained_variance_ratio_[0]*100:.1f}%, PC2={pca.explained_variance_ratio_[1]*100:.1f}%")
                else:
                    st.warning(f"Not enough embedding columns found. Found: {len(emb_cols)} columns")
            except ImportError:
                st.error("scikit-learn is required for PCA. Install with: pip install scikit-learn")
            except Exception as e:
                st.error(f"Error during PCA: {e}")
        else:
            st.warning("node_embeddings_fg.parquet not found - cannot visualize embeddings")

    # --- Debug: Resolved Paths ---
    with st.expander("Debug: Resolved Paths", expanded=False):
        # Get debug paths info
        try:
            paths_info = debug_paths(selected_run_id)

            st.markdown("**System Paths:**")
            st.code(f"repo_root: {paths_info['repo_root']}")
            st.code(f"artifacts_root: {paths_info['artifacts_root']}")
            st.code(f"run_dir: {paths_info['run_dir']} {'(exists)' if paths_info['run_dir_exists'] else '(NOT FOUND)'}")
            st.code(f"data_dir: {paths_info['data_dir']} {'(exists)' if paths_info['data_dir_exists'] else '(NOT FOUND)'}")

            st.markdown("**Data Files:**")
            for fname, info in paths_info.get("files", {}).items():
                status = "✅" if info.get("exists") else "❌"
                st.text(f"  {status} {fname}")
                if not info.get("exists"):
                    st.caption(f"      Expected: {info.get('path')}")

        except Exception as e:
            st.error(f"Failed to get debug paths: {e}")

        st.divider()
        st.markdown("**File Status (from local check):**")
        files_status = {
            "alert_nodes_td.csv": alert_nodes_path.exists(),
            "node_td.csv": node_td_path.exists(),
            "edges_td.csv": edges_td_path.exists(),
            "node_embeddings_fg.parquet": embeddings_path.exists(),
            "aml_rules.json": rules_path.exists(),
        }
        for fname, exists in files_status.items():
            status = "✅" if exists else "❌"
            st.text(f"  {status} {fname}")


# --- Interactive Dashboard Tab ---

def render_interactive_dashboard_tab():
    """Render the Interactive Dashboard tab — Plotly charts from completed run artifacts."""
    st.header("Interactive Dashboard")

    # ── Run selector (same pattern as analytics tab) ──
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found. Start a new run from the Run tab.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run first.")
        return

    run_options = {
        f"{r['id'][:8]}... - {r.get('params', {}).get('data_source', 'demo-data')} - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox("Select Run", options=list(run_options.keys()), key="idash_run_select")
    selected_run_id = run_options[selected_label]

    # ── Resolve artifact paths ──
    run_info = api_request("GET", f"/runs/{selected_run_id}")
    if run_info and run_info.get("artifact_path"):
        artifact_path = Path(run_info["artifact_path"])
        if not artifact_path.is_absolute():
            artifact_path = (get_repo_root() / artifact_path).resolve()
        run_dir = artifact_path
    else:
        run_dir = get_run_dir(selected_run_id)
    data_dir = run_dir / "data"
    models_dir = run_dir / "models"

    data_source = run_info.get("params", {}).get("data_source", "demo-data") if run_info else "demo-data"

    # ── Validate required files ──
    edges_path = data_dir / "edges_td.csv"
    nodes_path = data_dir / "node_td.csv"
    embeddings_path = data_dir / "node_embeddings_fg.parquet"

    missing = []
    if not edges_path.exists():
        missing.append("edges_td.csv")
    if not embeddings_path.exists():
        missing.append("node_embeddings_fg.parquet")
    if missing:
        st.warning(f"Missing required files in `{data_dir}`: {', '.join(missing)}")
        return

    model_dirs = sorted([d for d in models_dir.iterdir() if d.is_dir() and d.name.startswith("gan_anomaly_")]) if models_dir.exists() else []
    if not model_dirs:
        st.warning(f"No trained model found in `{models_dir}`")
        return

    # ── Load data ──
    with st.spinner("Loading run data..."):
        edges_df = pd.read_csv(edges_path)
        nodes_df = pd.read_csv(nodes_path) if nodes_path.exists() else None
        node_embeddings = pd.read_parquet(embeddings_path)

        latest_model_dir = model_dirs[-1]
        threshold_val = float(np.load(latest_model_dir / "threshold.npy"))

        # Compute anomaly scores
        emb_cols = [c for c in node_embeddings.columns if c.startswith("emb_")]
        from tensorflow import keras
        model = keras.models.load_model(str(latest_model_dir / "anomaly_detector.keras"))
        all_embeddings = node_embeddings[emb_cols].values
        reconstructed = model.predict(all_embeddings, verbose=0)
        anomaly_scores = np.mean(np.square(all_embeddings - reconstructed), axis=1)

        node_embeddings["anomaly_score"] = anomaly_scores
        node_embeddings["is_anomaly"] = anomaly_scores > threshold_val
        score_min, score_max = anomaly_scores.min(), anomaly_scores.max()
        node_embeddings["risk_score"] = (anomaly_scores - score_min) / (score_max - score_min) if score_max > score_min else 0.0

        # Map risk onto edges
        node_risk_dict = node_embeddings.set_index("id")["risk_score"].to_dict()
        node_anomaly_dict = node_embeddings.set_index("id")["is_anomaly"].to_dict()

        edges_df["source_risk"] = edges_df["source"].map(node_risk_dict).fillna(0)
        edges_df["target_risk"] = edges_df["target"].map(node_risk_dict).fillna(0)
        edges_df["edge_risk"] = edges_df[["source_risk", "target_risk"]].max(axis=1)
        edges_df["source_anomaly"] = edges_df["source"].map(node_anomaly_dict).fillna(False)
        edges_df["target_anomaly"] = edges_df["target"].map(node_anomaly_dict).fillna(False)
        edges_df["is_suspicious"] = edges_df["source_anomaly"] | edges_df["target_anomaly"]

        # Money flow per node
        outgoing = edges_df.groupby("source").agg({"base_amt": "sum", "tran_id": "count"}).rename(
            columns={"base_amt": "outgoing_amt", "tran_id": "outgoing_count"})
        incoming = edges_df.groupby("target").agg({"base_amt": "sum", "tran_id": "count"}).rename(
            columns={"base_amt": "incoming_amt", "tran_id": "incoming_count"})

        node_money = node_embeddings[["id", "anomaly_score", "is_anomaly", "risk_score"]].copy()
        if "is_sar" in node_embeddings.columns:
            node_money["is_sar"] = node_embeddings["is_sar"]
        node_money = node_money.merge(outgoing, left_on="id", right_index=True, how="left")
        node_money = node_money.merge(incoming, left_on="id", right_index=True, how="left")
        node_money = node_money.fillna(0)
        node_money["total_volume"] = node_money["outgoing_amt"] + node_money["incoming_amt"]
        node_money["total_transactions"] = node_money["outgoing_count"] + node_money["incoming_count"]
        node_money["net_flow"] = node_money["incoming_amt"] - node_money["outgoing_amt"]

        if nodes_df is not None:
            node_type_dict = nodes_df.set_index("id")["type"].to_dict()
            node_money = node_money.merge(nodes_df[["id", "type"]], on="id", how="left")
            edges_df["source_type"] = edges_df["source"].map(node_type_dict).fillna(-1).astype(int)
            edges_df["target_type"] = edges_df["target"].map(node_type_dict).fillna(-1).astype(int)

        # Loss/savings
        n_anomalies = int(node_embeddings["is_anomaly"].sum())
        n_normal = len(node_embeddings) - n_anomalies
        suspicious_txn_value = float(edges_df[edges_df["is_suspicious"]]["base_amt"].sum())

        DEMO_CONFIG = {
            "avg_loss_per_undetected_aml": 0.15,
            "investigation_cost_per_alert": 500,
            "false_positive_cost": 200,
            "regulatory_fine_multiplier": 3.0,
            "recovery_rate_detected": 0.70,
        }

        if "is_sar" in node_embeddings.columns:
            tp = int(((node_embeddings["is_sar"] == 1) & (node_embeddings["is_anomaly"])).sum())
            fp = int(((node_embeddings["is_sar"] == 0) & (node_embeddings["is_anomaly"])).sum())
            fn = int(((node_embeddings["is_sar"] == 1) & (~node_embeddings["is_anomaly"])).sum())
            tn = int(((node_embeddings["is_sar"] == 0) & (~node_embeddings["is_anomaly"])).sum())
        else:
            tp = int(n_anomalies * 0.10)
            fp = n_anomalies - tp
            fn = int(n_normal * 0.01)
            tn = n_normal - fn

        cfg = DEMO_CONFIG
        avg_suspicious_txn = suspicious_txn_value / max(n_anomalies, 1)
        potential_loss_detected = tp * avg_suspicious_txn * cfg["avg_loss_per_undetected_aml"]
        recovered_amount = potential_loss_detected * cfg["recovery_rate_detected"]
        normal_txn_value = float(edges_df[~edges_df["is_suspicious"]]["base_amt"].sum())
        avg_normal_txn = normal_txn_value / max(n_normal, 1)
        potential_loss_undetected = fn * avg_normal_txn * cfg["avg_loss_per_undetected_aml"]
        regulatory_fine_risk = potential_loss_undetected * cfg["regulatory_fine_multiplier"]
        investigation_cost = n_anomalies * cfg["investigation_cost_per_alert"]
        false_positive_cost = fp * cfg["false_positive_cost"]
        total_operational_cost = investigation_cost + false_positive_cost
        net_savings = recovered_amount - total_operational_cost

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * (precision * recall) / max(precision + recall, 1e-9)

    # ── Header badges ──
    src_color = "red" if data_source == "saml-d" else "blue"
    st.markdown(
        f"**`{data_source.upper()}`** &nbsp; Run `{selected_run_id[:8]}…` &nbsp; | &nbsp; "
        f"**{len(node_embeddings):,}** nodes &nbsp; **{len(edges_df):,}** txns &nbsp; **{n_anomalies:,}** anomalies &nbsp; "
        f"Threshold: `{threshold_val:.6f}`"
    )
    st.divider()

    # ── Colour constants ──
    CLR = dict(blue="#3498db", green="#2ecc71", red="#e74c3c", purple="#9b59b6",
               orange="#e67e22", yellow="#f1c40f")
    RISK_COLORS = [CLR["green"], CLR["yellow"], CLR["orange"], CLR["red"]]
    RISK_LABELS = ["Low", "Medium", "High", "Critical"]

    # ══════════════════════════════════════════════════════════════════════
    #  Sub-tabs
    # ══════════════════════════════════════════════════════════════════════
    stab1, stab2, stab3, stab4, stab5 = st.tabs([
        "Executive Summary", "Financial Impact", "Network Graph",
        "Transaction Deep Dive", "Node Risk Profiles",
    ])

    # ── TAB 1: Executive Summary ──
    with stab1:
        # KPI row
        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.metric("Total Transactions", f"{len(edges_df):,}")
        kc2.metric("Total Volume", f"${edges_df['base_amt'].sum():,.0f}")
        kc3.metric("Anomalies Detected", f"{n_anomalies:,}")
        kc4.metric("Detection Rate", f"{100 * node_embeddings['is_anomaly'].mean():.1f}%")

        col1, col2 = st.columns(2)

        # Risk distribution bar
        risk_cat = pd.cut(node_embeddings["risk_score"], bins=[0, 0.25, 0.5, 0.75, 1.0],
                          labels=RISK_LABELS, include_lowest=True)
        risk_counts = risk_cat.value_counts().reindex(RISK_LABELS).fillna(0)
        fig_risk_bar = go.Figure(go.Bar(
            x=RISK_LABELS, y=risk_counts.values, marker_color=RISK_COLORS,
            text=[f"{int(v):,}" for v in risk_counts.values], textposition="outside"))
        fig_risk_bar.update_layout(title="Risk Distribution", yaxis_title="Nodes", margin=dict(t=40, b=30))
        col1.plotly_chart(fig_risk_bar, width="stretch")

        # Suspicious vs normal pie
        susp_vol = float(edges_df[edges_df["is_suspicious"]]["base_amt"].sum())
        norm_vol = float(edges_df[~edges_df["is_suspicious"]]["base_amt"].sum())
        fig_pie = go.Figure(go.Pie(
            labels=["Normal", "Suspicious"], values=[norm_vol, susp_vol],
            marker_colors=[CLR["blue"], CLR["red"]], hole=0.45, textinfo="label+percent",
            hovertemplate="%{label}<br>$%{value:,.0f}<extra></extra>"))
        fig_pie.update_layout(title="Volume: Normal vs Suspicious", margin=dict(t=40, b=10))
        col2.plotly_chart(fig_pie, width="stretch")

        col3, col4 = st.columns(2)

        # Top 10 risk nodes
        top10 = node_money.nlargest(10, "risk_score")
        fig_top10 = go.Figure(go.Bar(
            y=[f"{r['id'][:10]}… ({r['risk_score']:.2f})" for _, r in top10.iterrows()],
            x=top10["total_volume"], orientation="h",
            marker_color=px.colors.sample_colorscale("Reds", top10["risk_score"].values),
            hovertemplate="Node: %{y}<br>Volume: $%{x:,.0f}<extra></extra>"))
        fig_top10.update_layout(title="Top 10 Risk Nodes by Volume", xaxis_title="Volume ($)",
                                yaxis=dict(autorange="reversed"), margin=dict(t=40, b=30, l=160))
        col3.plotly_chart(fig_top10, width="stretch")

        # Anomaly score curve
        sorted_scores = np.sort(anomaly_scores)
        fig_curve = go.Figure()
        fig_curve.add_trace(go.Scatter(
            x=list(range(len(sorted_scores))), y=sorted_scores,
            fill="tozeroy", fillcolor="rgba(52,152,219,0.2)",
            line=dict(color=CLR["blue"], width=2),
            hovertemplate="Node %{x}<br>Score: %{y:.6f}<extra></extra>"))
        fig_curve.add_hline(y=threshold_val, line_dash="dash", line_color="red",
                            annotation_text=f"Threshold {threshold_val:.6f}")
        fig_curve.update_layout(title="Anomaly Score Curve", xaxis_title="Nodes (sorted)",
                                yaxis_title="Score", margin=dict(t=40, b=30))
        col4.plotly_chart(fig_curve, width="stretch")

    # ── TAB 2: Financial Impact ──
    with stab2:
        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.metric("Recovered", f"${recovered_amount:,.0f}")
        kc2.metric("Operational Cost", f"${total_operational_cost:,.0f}")
        kc3.metric("Net Savings", f"${net_savings:,.0f}")
        kc4.metric("Regulatory Risk", f"${regulatory_fine_risk:,.0f}")

        col1, col2 = st.columns([5, 7])

        # Confusion matrix
        cm = np.array([[tn, fp], [fn, tp]])
        fig_cm = px.imshow(cm, text_auto=True,
                           x=["Predicted Normal", "Predicted Anomaly"],
                           y=["Actual Normal", "Actual AML"],
                           color_continuous_scale="RdYlGn_r", labels=dict(color="Count"))
        fig_cm.update_layout(title="Detection Matrix", margin=dict(t=40, b=30))
        col1.plotly_chart(fig_cm, width="stretch")

        # Waterfall
        fig_wf = go.Figure(go.Waterfall(
            x=["Suspicious<br>Value", "Loss<br>Avoided", "Recovered",
               "Investigation<br>Cost", "FP Cost", "Net Savings"],
            y=[suspicious_txn_value, -potential_loss_detected, recovered_amount,
               -investigation_cost, -false_positive_cost, net_savings],
            measure=["absolute", "relative", "relative", "relative", "relative", "total"],
            connector_line_color="rgba(200,200,200,0.3)",
            increasing_marker_color=CLR["green"], decreasing_marker_color=CLR["red"],
            totals_marker_color=CLR["purple"],
            texttemplate="$%{y:,.0f}", textposition="outside"))
        fig_wf.update_layout(title="Loss vs Savings Waterfall", yaxis_title="Amount ($)",
                             margin=dict(t=40, b=30))
        col2.plotly_chart(fig_wf, width="stretch")

        # Gauges
        fig_gauges = make_subplots(rows=1, cols=3, specs=[[{"type": "indicator"}] * 3],
                                   subplot_titles=["Precision", "Recall", "F1 Score"])
        for i, (name, val, color) in enumerate([
            ("Precision", precision, CLR["blue"]),
            ("Recall", recall, CLR["green"]),
            ("F1", f1, CLR["purple"])
        ], 1):
            fig_gauges.add_trace(go.Indicator(
                mode="gauge+number", value=val * 100, number_suffix="%",
                gauge=dict(axis=dict(range=[0, 100]), bar_color=color,
                           steps=[dict(range=[0, 50], color="rgba(255,0,0,0.15)"),
                                  dict(range=[50, 80], color="rgba(255,255,0,0.10)"),
                                  dict(range=[80, 100], color="rgba(0,255,0,0.10)")])), row=1, col=i)
        fig_gauges.update_layout(height=280, margin=dict(t=40, b=10))
        st.plotly_chart(fig_gauges, width="stretch")

    # ── TAB 3: Network Graph ──
    with stab3:
        import networkx as nx

        filter_mode = st.selectbox("Filter", ["All Nodes", "Suspicious Only", "High-Risk Neighborhood"],
                                   key="idash_net_filter")
        filter_map = {"All Nodes": "all", "Suspicious Only": "suspicious",
                      "High-Risk Neighborhood": "high_risk"}
        fmode = filter_map[filter_mode]
        max_nodes = 300

        edges_sorted = edges_df.sort_values(["edge_risk", "base_amt"], ascending=[False, False])
        if fmode == "suspicious":
            edges_subset = edges_sorted[edges_sorted["is_suspicious"]].head(max_nodes * 3)
        elif fmode == "high_risk":
            hr_nodes = set(node_embeddings[node_embeddings["risk_score"] > 0.75]["id"])
            edges_subset = edges_sorted[
                edges_sorted["source"].isin(hr_nodes) | edges_sorted["target"].isin(hr_nodes)
            ].head(max_nodes * 3)
        else:
            edges_subset = edges_sorted.head(max_nodes * 3)

        sel_nodes = set(edges_subset["source"].tolist() + edges_subset["target"].tolist())
        if len(sel_nodes) > max_nodes:
            top_n = node_embeddings[node_embeddings["id"].isin(sel_nodes)].nlargest(max_nodes, "risk_score")["id"]
            sel_nodes = set(top_n)
            edges_subset = edges_subset[
                edges_subset["source"].isin(sel_nodes) & edges_subset["target"].isin(sel_nodes)]

        G = nx.DiGraph()
        for _, r in edges_subset.iterrows():
            G.add_edge(r["source"], r["target"], amount=r["base_amt"], risk=r["edge_risk"])

        if G.number_of_nodes() == 0:
            st.info("No nodes match the selected filter.")
        else:
            pos = nx.spring_layout(G, k=3 / np.sqrt(G.number_of_nodes()), iterations=50, seed=42)
            edge_x, edge_y = [], []
            for u, v in G.edges():
                x0, y0 = pos[u]; x1, y1 = pos[v]
                edge_x += [x0, x1, None]; edge_y += [y0, y1, None]

            vol_dict = node_money.set_index("id")["total_volume"].to_dict()
            txn_dict = node_money.set_index("id")["total_transactions"].to_dict()
            node_x = [pos[n][0] for n in G.nodes()]
            node_y = [pos[n][1] for n in G.nodes()]
            n_risk = [node_risk_dict.get(n, 0) for n in G.nodes()]
            n_vol = [vol_dict.get(n, 0) for n in G.nodes()]
            vol_mx = max(n_vol) if n_vol else 1
            n_sizes = [6 + 20 * (v / vol_mx) for v in n_vol]
            hover = [
                f"ID: {n[:16]}<br>Risk: {node_risk_dict.get(n,0):.4f}<br>"
                f"Volume: ${vol_dict.get(n,0):,.0f}<br>Txns: {int(txn_dict.get(n,0)):,}"
                for n in G.nodes()]

            fig_net = go.Figure(data=[
                go.Scatter(x=edge_x, y=edge_y, mode="lines",
                           line=dict(width=0.5, color="rgba(150,150,150,0.3)"), hoverinfo="none"),
                go.Scatter(x=node_x, y=node_y, mode="markers",
                           marker=dict(size=n_sizes, color=n_risk, colorscale="RdYlGn_r",
                                       cmin=0, cmax=1, colorbar=dict(title="Risk"),
                                       line=dict(width=0.5, color="white")),
                           text=hover, hoverinfo="text"),
            ])
            fig_net.update_layout(
                title=f"Transaction Network ({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)",
                showlegend=False, hovermode="closest", height=650,
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                margin=dict(t=40, b=10, l=10, r=10))
            st.plotly_chart(fig_net, width="stretch")

    # ── TAB 4: Transaction Deep Dive ──
    with stab4:
        amt_range = st.slider("Amount Range ($)", min_value=0.0,
                              max_value=float(edges_df["base_amt"].quantile(0.99)),
                              value=(0.0, float(edges_df["base_amt"].quantile(0.99))),
                              step=100.0, key="idash_amt_slider")
        filtered = edges_df[(edges_df["base_amt"] >= amt_range[0]) & (edges_df["base_amt"] <= amt_range[1])]

        col1, col2 = st.columns(2)

        # Amount histogram
        fig_hist = px.histogram(filtered, x="base_amt", nbins=80,
                                color_discrete_sequence=[CLR["blue"]],
                                labels={"base_amt": "Amount ($)"})
        fig_hist.update_layout(title=f"Amount Distribution ({len(filtered):,} txns)",
                               yaxis_type="log", yaxis_title="Count (log)", margin=dict(t=40, b=30))
        col1.plotly_chart(fig_hist, width="stretch")

        # Amount vs risk scatter
        samp = filtered.sample(min(5000, len(filtered)), random_state=42) if len(filtered) > 0 else filtered
        fig_scatter = px.scatter(samp, x="base_amt", y="edge_risk",
                                 color="edge_risk", color_continuous_scale="RdYlGn_r",
                                 hover_data=["source", "target", "base_amt", "edge_risk"],
                                 labels={"base_amt": "Amount ($)", "edge_risk": "Risk"})
        fig_scatter.update_layout(title="Amount vs Risk", margin=dict(t=40, b=30))
        col2.plotly_chart(fig_scatter, width="stretch")

        col3, col4 = st.columns(2)

        # Volume by tx_type
        type_vol = edges_df.groupby("tx_type")["base_amt"].sum().sort_values(ascending=True).reset_index()
        type_vol["tx_type"] = type_vol["tx_type"].astype(str)
        fig_type = px.bar(type_vol, y="tx_type", x="base_amt", orientation="h",
                          color="base_amt", color_continuous_scale="Blues",
                          labels={"base_amt": "Volume ($)", "tx_type": "Tx Type"})
        fig_type.update_layout(title="Volume by Transaction Type", margin=dict(t=40, b=30))
        col3.plotly_chart(fig_type, width="stretch")

        # Risk heatmap
        if nodes_df is not None and "source_type" in edges_df.columns:
            hm = edges_df.pivot_table(values="edge_risk", index="source_type",
                                      columns="target_type", aggfunc="mean").fillna(0)
            fig_hm = px.imshow(hm, color_continuous_scale="RdYlGn_r",
                               labels=dict(x="Target Type", y="Source Type", color="Avg Risk"),
                               x=[f"Type {c}" for c in hm.columns],
                               y=[f"Type {i}" for i in hm.index], text_auto=".3f")
            fig_hm.update_layout(title="Avg Risk by Node-Type Pair", margin=dict(t=40, b=30))
            col4.plotly_chart(fig_hm, width="stretch")

    # ── TAB 5: Node Risk Profiles ──
    with stab5:
        col1, col2 = st.columns(2)

        # Risk histogram with percentiles
        fig_rh = go.Figure()
        fig_rh.add_trace(go.Histogram(x=node_money["risk_score"], nbinsx=60,
                                      marker_color=CLR["blue"], opacity=0.75))
        for p, clr in [(50, "green"), (75, "yellow"), (90, "orange"), (95, "red"), (99, "darkred")]:
            val = float(np.percentile(node_money["risk_score"], p))
            fig_rh.add_vline(x=val, line_dash="dash", line_color=clr,
                             annotation_text=f"P{p}: {val:.3f}")
        fig_rh.update_layout(title="Risk Score Distribution", xaxis_title="Risk Score",
                             yaxis_title="Nodes", margin=dict(t=40, b=30))
        col1.plotly_chart(fig_rh, width="stretch")

        # Volume vs risk scatter
        fig_vr = px.scatter(node_money, x="total_volume", y="risk_score",
                            color="is_anomaly", color_discrete_map={True: CLR["red"], False: CLR["blue"]},
                            hover_data=["id", "total_volume", "total_transactions", "risk_score"],
                            labels={"total_volume": "Volume ($)", "risk_score": "Risk Score", "is_anomaly": "Anomaly"})
        fig_vr.update_layout(title="Volume vs Risk", margin=dict(t=40, b=30))
        col2.plotly_chart(fig_vr, width="stretch")

        # Top 20 table
        st.subheader("Top 20 Highest Risk Nodes")
        top20 = node_money.nlargest(20, "risk_score")[
            ["id", "risk_score", "total_volume", "total_transactions", "is_anomaly", "net_flow"]].copy()
        top20["risk_score"] = top20["risk_score"].round(4)
        top20["total_volume"] = top20["total_volume"].apply(lambda x: f"${x:,.0f}")
        top20["net_flow"] = top20["net_flow"].apply(lambda x: f"${x:,.0f}")
        top20["total_transactions"] = top20["total_transactions"].astype(int)
        st.dataframe(top20, width="stretch", hide_index=True)

        col3, col4, col5 = st.columns(3)

        # Box plot by node type
        if "type" in node_money.columns:
            fig_box = px.box(node_money, x="type", y="risk_score",
                             color="type", color_discrete_sequence=px.colors.qualitative.Set2,
                             labels={"type": "Node Type", "risk_score": "Risk Score"})
            fig_box.update_layout(title="Risk by Node Type", showlegend=False, margin=dict(t=40, b=30))
            col3.plotly_chart(fig_box, width="stretch")

        # Radar chart
        high_risk = node_money[node_money["risk_score"] > 0.75]
        low_risk = node_money[node_money["risk_score"] <= 0.25]
        radar_cats = ["Avg Volume", "Avg Txns", "Out Flow", "In Flow", "Net Flow Var"]

        def _snorm(s, d):
            return float(s.mean() / d) if d > 0 and len(s) > 0 else 0

        vm = node_money["total_volume"].max() or 1
        tm = node_money["total_transactions"].max() or 1
        om = node_money["outgoing_amt"].max() or 1
        im_ = node_money["incoming_amt"].max() or 1
        ns = node_money["net_flow"].std() or 1

        hv = [_snorm(high_risk["total_volume"], vm), _snorm(high_risk["total_transactions"], tm),
              _snorm(high_risk["outgoing_amt"], om), _snorm(high_risk["incoming_amt"], im_),
              float(high_risk["net_flow"].std() / ns) if len(high_risk) > 1 else 0]
        lv = [_snorm(low_risk["total_volume"], vm), _snorm(low_risk["total_transactions"], tm),
              _snorm(low_risk["outgoing_amt"], om), _snorm(low_risk["incoming_amt"], im_),
              float(low_risk["net_flow"].std() / ns) if len(low_risk) > 1 else 0]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=hv + [hv[0]], theta=radar_cats + [radar_cats[0]],
            fill="toself", name="High Risk", line_color=CLR["red"], fillcolor="rgba(231,76,60,0.2)"))
        fig_radar.add_trace(go.Scatterpolar(
            r=lv + [lv[0]], theta=radar_cats + [radar_cats[0]],
            fill="toself", name="Low Risk", line_color=CLR["green"], fillcolor="rgba(46,204,113,0.2)"))
        fig_radar.update_layout(title="Risk Profile Comparison",
                                polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                                margin=dict(t=50, b=30))
        col4.plotly_chart(fig_radar, width="stretch")

        # Lorenz curve
        sorted_by_risk = node_money.sort_values("risk_score")
        cum_vol = sorted_by_risk["total_volume"].cumsum() / sorted_by_risk["total_volume"].sum()
        x_lorenz = np.linspace(0, 1, len(cum_vol))
        fig_lorenz = go.Figure()
        fig_lorenz.add_trace(go.Scatter(x=x_lorenz, y=cum_vol.values, fill="tonexty",
                                        name="Actual", line_color=CLR["blue"],
                                        fillcolor="rgba(52,152,219,0.2)"))
        fig_lorenz.add_trace(go.Scatter(x=[0, 1], y=[0, 1], line_dash="dash",
                                        name="Equal", line_color="grey"))
        fig_lorenz.update_layout(title="Risk Concentration (Lorenz)",
                                 xaxis_title="Cumulative % Nodes", yaxis_title="Cumulative % Volume",
                                 margin=dict(t=40, b=30))
        col5.plotly_chart(fig_lorenz, width="stretch")


# --- Sidebar ---

def render_sidebar():
    """Render the sidebar."""
    with st.sidebar:
        st.title("🔍 AML Pipeline")
        st.markdown("---")

        # System Status
        st.subheader("System Status")
        # Use lightweight /ping (no Celery/DB check) to avoid 5s+ blocking
        ping = api_request("GET", "/ping", timeout=3)

        if ping:
            st.success("API Online")
        else:
            st.error("API Offline")
            if st.button("Retry Connection"):
                st.rerun()
            st.markdown("Start the API server:")
            st.code("uvicorn app.api.main:app --reload", language="bash")

        st.markdown("---")

        # Quick Links
        st.subheader("Quick Links")
        st.markdown(f"[📚 API Docs]({API_BASE_URL}/docs)")
        st.markdown(f"[❤️ Health Check]({API_BASE_URL}/status/health)")

        st.markdown("---")

        # Plot Style Toggle
        st.subheader("Display Options")
        st.toggle(
            "Show Styled Plots",
            value=True,
            key="show_styled_plots",
            help="Toggle between Bloomberg-terminal styled plots and original plots"
        )

        st.markdown("---")

        # Help
        with st.expander("❓ Help"):
            st.markdown("""
            **Prerequisites:**
            1. Redis server running
            2. API server running
            3. Celery worker running

            **Commands:**
            ```bash
            # Terminal 1 - Redis
            redis-server

            # Terminal 2 - API
            uvicorn app.api.main:app --reload

            # Terminal 3 - Celery
            celery -A app.workers.celery_app worker -l info

            # Terminal 4 - Streamlit
            streamlit run app/ui/streamlit_app.py
            ```
            """)

        with st.expander("📖 About"):
            st.markdown("""
            **AML Pipeline Runner** v2.0

            A web UI for running and monitoring
            the AML end-to-end detection pipeline.

            Features:
            - Run profiles (Quick/Standard/Heavy)
            - Real-time progress monitoring
            - Interactive dashboard
            - Report generation
            """)


# --- Tier Queue Tab ---

def render_tier_queue_tab():
    """Render the Tier Queue tab with risk-ranked entities."""
    st.header("Tier Queue — Risk-Ranked Entities")

    # Run selector (same pattern as Analytics tab)
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found. Start a run first.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view the risk queue.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox(
        "Select Run", options=list(run_options.keys()), key="tier_queue_run_select"
    )
    selected_run_id = run_options[selected_label]

    # Load summary
    summary = api_request("GET", f"/runs/{selected_run_id}/risk-summary")
    if not summary or summary.get("detail"):
        st.warning(
            "Risk queue not available for this run. "
            "Re-run the pipeline or ensure `data/alert_nodes_td.csv` exists."
        )
        return

    # --- Label sparse warning ---
    sar_stats = summary.get("sar_label_stats", {})
    if sar_stats.get("label_sparse", False):
        sar_ct = sar_stats.get("sar_count", 0)
        sar_rt = sar_stats.get("sar_rate_pct", 0)
        st.warning(
            f"**Labels are sparse:** Only {sar_ct} SAR-labelled entities "
            f"({sar_rt:.3f}% of total). Risk ranking relies primarily on "
            f"network connectivity (degree). Consider enriching labels or "
            f"using a larger sample size for more robust scoring."
        )

    # --- Filter controls ---
    st.markdown("---")
    col_tier, col_pct, col_type, col_sar, col_search = st.columns([1.2, 1.2, 1.2, 1, 1.4])

    tier_counts = summary.get("tier_counts", {})

    with col_tier:
        tier_labels = [
            f"T1 ({tier_counts.get('T1', 0)})",
            f"T2 ({tier_counts.get('T2', 0)})",
            f"T3 ({tier_counts.get('T3', 0)})",
            f"T4 ({tier_counts.get('T4', 0)})",
        ]
        tier_values = ["T1", "T2", "T3", "T4"]
        selected_tier_labels = st.multiselect(
            "Tier Filter",
            options=tier_labels,
            default=[tier_labels[0], tier_labels[1]],
            key="tq_tier",
        )
        # Map labels back to values
        selected_tiers = [
            tier_values[tier_labels.index(lbl)]
            for lbl in selected_tier_labels
            if lbl in tier_labels
        ]

    with col_pct:
        max_percentile = st.slider(
            "Investigate Top X%", min_value=0.5, max_value=100.0,
            value=5.0, step=0.5, key="tq_pct",
        )

    with col_type:
        # Gather entity types from summary
        all_types = set()
        for tier_types in summary.get("top_types_per_tier", {}).values():
            all_types.update(tier_types.keys())
        all_types = sorted(all_types)
        selected_types = st.multiselect(
            "Entity Types", options=all_types, default=[], key="tq_etype",
        )

    with col_sar:
        sar_option = st.radio(
            "SAR Filter", ["All", "SAR Only", "Non-SAR"], key="tq_sar",
        )

    with col_search:
        search_text = st.text_input(
            "Search Entity ID", value="", key="tq_search",
        )

    # --- Reasons filter ---
    reason_options = ["SAR_LABEL", "HIGH_CONNECTIVITY"]
    selected_reasons = st.multiselect(
        "Filter by Reasons", options=reason_options, default=[], key="tq_reasons",
    )

    # --- Build query params ---
    params = {"limit": 500, "offset": 0, "max_percentile": max_percentile}
    if selected_tiers:
        params["tier"] = selected_tiers
    if selected_types:
        params["entity_type"] = selected_types
    if sar_option == "SAR Only":
        params["is_sar"] = 1
    elif sar_option == "Non-SAR":
        params["is_sar"] = 0
    if search_text.strip():
        params["search"] = search_text.strip()

    # Fetch filtered queue
    queue_data = api_request("GET", f"/runs/{selected_run_id}/risk-queue", params=params)
    if not queue_data or queue_data.get("detail"):
        st.warning("Could not load risk queue data.")
        return

    rows = queue_data.get("rows", [])

    # Client-side reasons filter
    if selected_reasons and rows:
        rows = [
            r for r in rows
            if any(reason in (r.get("reasons") or "") for reason in selected_reasons)
        ]

    total_filtered = len(rows)

    # --- KPI cards ---
    st.markdown("---")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    with kpi1:
        st.metric("Total Entities", f"{summary.get('total_entities', 0):,}")
    with kpi2:
        st.metric("Filtered Results", f"{total_filtered:,}")
    with kpi3:
        sar_count = summary.get("sar_count", 0)
        st.metric("SAR-Labelled", f"{sar_count:,}")
    with kpi4:
        # Top entity type in filtered results
        if rows:
            type_counts = {}
            for row in rows:
                t = row.get("entity_type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            top_type = max(type_counts, key=type_counts.get)
            st.metric("Top Type (filtered)", str(top_type))
        else:
            st.metric("Top Type (filtered)", "N/A")

    # --- Tier breakdown bar ---
    tier_cols = st.columns(4)
    tier_colors = {"T1": "#EF4444", "T2": "#F59E0B", "T3": "#3B82F6", "T4": "#6B7280"}
    for i, tier_name in enumerate(["T1", "T2", "T3", "T4"]):
        with tier_cols[i]:
            count = tier_counts.get(tier_name, 0)
            pct = (count / max(summary.get("total_entities", 1), 1)) * 100
            color = tier_colors[tier_name]
            st.markdown(
                f"<div style='text-align:center;padding:0.5rem;border-radius:6px;"
                f"border:1px solid {color};'>"
                f"<span style='color:{color};font-weight:700;font-size:1.1rem;'>{tier_name}</span><br>"
                f"<span style='color:#E5E7EB;font-size:1.3rem;font-weight:600;'>{count:,}</span><br>"
                f"<span style='color:#9CA3AF;font-size:0.85rem;'>{pct:.1f}%</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("")

    # --- Data table ---
    if rows:
        df = pd.DataFrame(rows)

        # Column ordering
        display_cols = [
            c for c in ["rank", "tier", "entity_id", "entity_type", "is_sar",
                         "risk_score", "degree", "percentile", "reasons"]
            if c in df.columns
        ]
        df = df[display_cols]

        # Format risk_score and percentile
        if "risk_score" in df.columns:
            df["risk_score"] = df["risk_score"].round(4)
        if "percentile" in df.columns:
            df["percentile"] = df["percentile"].round(2)

        st.dataframe(
            df,
            width="stretch",
            height=500,
            column_config={
                "rank": st.column_config.NumberColumn("Rank", format="%d"),
                "tier": st.column_config.TextColumn("Tier"),
                "entity_id": st.column_config.TextColumn("Entity ID"),
                "entity_type": st.column_config.TextColumn("Type"),
                "is_sar": st.column_config.NumberColumn("SAR", format="%d"),
                "risk_score": st.column_config.NumberColumn("Risk Score", format="%.4f"),
                "degree": st.column_config.NumberColumn("Degree", format="%d"),
                "percentile": st.column_config.NumberColumn("Pctile %", format="%.2f"),
                "reasons": st.column_config.TextColumn("Reasons"),
            },
        )

        # Download button
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="Download Filtered Queue (CSV)",
            data=csv_data,
            file_name=f"risk_queue_{selected_run_id[:8]}_filtered.csv",
            mime="text/csv",
            key="tq_download",
        )
    else:
        st.info("No entities match the current filters.")

    # --- Operating Point Panel ---
    st.markdown("---")
    st.subheader("Operating Point")

    # Load existing operating point if saved
    saved_op = api_request("GET", f"/runs/{selected_run_id}/operating-point")

    op_col1, op_col2 = st.columns([2, 1])
    with op_col1:
        if saved_op and not saved_op.get("detail"):
            saved_payload = saved_op.get("payload", {})
            saved_at = saved_op.get("saved_at", "")
            st.markdown(
                f"**Saved:** {saved_at[:19]}Z &nbsp;|&nbsp; "
                f"Top {saved_payload.get('top_percent', '?')}% &nbsp;|&nbsp; "
                f"Tiers: {', '.join(saved_payload.get('tiers', []))} &nbsp;|&nbsp; "
                f"SAR: {saved_payload.get('sar_filter', 'All')}"
            )
        else:
            st.caption("No operating point saved for this run yet.")

    with op_col2:
        if st.button("Save Operating Point", key="tq_save_op"):
            op_body = {
                "top_percent": max_percentile,
                "tiers": selected_tiers if selected_tiers else ["T1", "T2", "T3", "T4"],
                "entity_types": selected_types,
                "sar_filter": sar_option,
                "search": search_text.strip(),
            }
            result = api_request("POST", f"/runs/{selected_run_id}/operating-point", json=op_body)
            if result and not result.get("detail"):
                st.success("Operating point saved.")
            else:
                detail = result.get("detail", "Unknown error") if result else "API unavailable"
                st.error(f"Failed to save: {detail}")

    # Score distribution chart
    if rows and len(rows) > 5:
        st.markdown("---")
        st.subheader("Risk Score Distribution")
        df_chart = pd.DataFrame(rows)
        if "risk_score" in df_chart.columns and "tier" in df_chart.columns:
            fig = px.histogram(
                df_chart,
                x="risk_score",
                color="tier",
                nbins=40,
                color_discrete_map=tier_colors,
                labels={"risk_score": "Risk Score", "tier": "Tier"},
            )
            apply_modern_terminal_plotly()
            fig.update_layout(
                height=340,
                margin=dict(l=40, r=20, t=30, b=40),
                barmode="overlay",
                legend=dict(orientation="h", y=1.08),
            )
            fig.update_traces(opacity=0.75)
            st.plotly_chart(fig, width="stretch")


# --- Cases Tab ---

def render_cases_tab():
    """Render the Cases tab for investigation-ready AML cases."""
    st.header("Investigation Cases")

    # Run selector
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found. Start a run first.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view cases.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox(
        "Select Run", options=list(run_options.keys()), key="cases_run_select"
    )
    selected_run_id = run_options[selected_label]

    # Load cases summary
    summary = api_request("GET", f"/runs/{selected_run_id}/cases/summary")
    if not summary or summary.get("detail"):
        st.warning("Cases not available for this run. Re-run the pipeline to generate cases.")
        return

    total_cases = summary.get("total_cases", 0)
    if total_cases == 0:
        st.info("No cases generated — no seed entities matched the operating point criteria.")
        return

    # --- KPI cards ---
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Total Cases", f"{total_cases:,}")
    with kpi2:
        st.metric("Seed Entities", f"{summary.get('seed_count', 0):,}")
    with kpi3:
        st.metric("Entities in Cases", f"{summary.get('total_entities_in_cases', 0):,}")
    with kpi4:
        st.metric("SARs in Cases", f"{summary.get('total_sar_in_cases', 0):,}")

    # Typology counts bar
    typology_counts = summary.get("typology_counts", {})
    if typology_counts:
        typ_cols = st.columns(len(typology_counts))
        typ_colors = {
            "FAN_OUT": "#F59E0B", "FAN_IN": "#3B82F6", "CIRCULAR_FLOW": "#EF4444",
            "HUB_DOMINANCE": "#8B5CF6", "SAR_PROXIMITY": "#22C55E",
        }
        for i, (typ_name, typ_count) in enumerate(sorted(typology_counts.items())):
            with typ_cols[i]:
                color = typ_colors.get(typ_name, "#9CA3AF")
                st.markdown(
                    f"<div style='text-align:center;padding:0.4rem;border-radius:6px;"
                    f"border:1px solid {color};'>"
                    f"<span style='color:{color};font-weight:600;font-size:0.85rem;'>"
                    f"{typ_name}</span><br>"
                    f"<span style='color:#E5E7EB;font-size:1.2rem;font-weight:700;'>"
                    f"{typ_count}</span></div>",
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # --- Filters ---
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        tier_filter = st.multiselect(
            "Tier Filter", ["T1", "T2", "T3", "T4"], default=[], key="cases_tier",
        )
    with filter_col2:
        typology_options = sorted(typology_counts.keys()) if typology_counts else []
        typology_filter = st.multiselect(
            "Typology Filter", typology_options, default=[], key="cases_typology",
        )
    with filter_col3:
        min_entities = st.number_input(
            "Min Entities", min_value=1, value=1, step=1, key="cases_min_ent",
        )

    # Build query params
    params = {"limit": 200, "offset": 0}
    if tier_filter:
        params["tier"] = tier_filter
    if typology_filter:
        params["typology"] = typology_filter
    if min_entities > 1:
        params["min_entities"] = min_entities

    # Fetch case list
    cases_data = api_request("GET", f"/runs/{selected_run_id}/cases", params=params)
    if not cases_data or cases_data.get("detail"):
        st.warning("Could not load cases.")
        return

    cases_list = cases_data.get("cases", [])

    if not cases_list:
        st.info("No cases match the current filters.")
        return

    # --- Case list table ---
    cases_df = pd.DataFrame(cases_list)
    display_cols = [
        c for c in ["case_id", "tier", "risk_score", "entity_count", "edge_count",
                     "sar_count", "typologies", "seed_count"]
        if c in cases_df.columns
    ]
    cases_df_display = cases_df[display_cols].copy()
    if "case_id" in cases_df_display.columns:
        cases_df_display["case_id"] = cases_df_display["case_id"].str[:12] + "..."
    if "risk_score" in cases_df_display.columns:
        cases_df_display["risk_score"] = cases_df_display["risk_score"].round(4)

    st.dataframe(
        cases_df_display,
        width="stretch",
        height=min(400, 35 * len(cases_df_display) + 60),
        column_config={
            "case_id": st.column_config.TextColumn("Case ID"),
            "tier": st.column_config.TextColumn("Tier"),
            "risk_score": st.column_config.NumberColumn("Risk Score", format="%.4f"),
            "entity_count": st.column_config.NumberColumn("Entities", format="%d"),
            "edge_count": st.column_config.NumberColumn("Edges", format="%d"),
            "sar_count": st.column_config.NumberColumn("SARs", format="%d"),
            "typologies": st.column_config.TextColumn("Typologies"),
            "seed_count": st.column_config.NumberColumn("Seeds", format="%d"),
        },
    )

    # --- Case detail view ---
    st.markdown("---")
    st.subheader("Case Detail")

    case_ids_full = cases_df["case_id"].tolist() if "case_id" in cases_df.columns else []
    if not case_ids_full:
        return

    case_select_options = {
        f"{cid[:12]}... (Tier {cases_df.iloc[i].get('tier', '?')}, "
        f"{cases_df.iloc[i].get('entity_count', 0)} entities)": cid
        for i, cid in enumerate(case_ids_full)
    }

    selected_case_label = st.selectbox(
        "Select Case to Inspect", options=list(case_select_options.keys()),
        key="cases_detail_select",
    )
    selected_case_id = case_select_options[selected_case_label]

    case_detail = api_request("GET", f"/runs/{selected_run_id}/cases/{selected_case_id}")
    if not case_detail or case_detail.get("detail"):
        st.warning("Could not load case detail.")
        return

    # Stats row
    stat1, stat2, stat3, stat4 = st.columns(4)
    with stat1:
        st.metric("Entities", case_detail.get("entity_count", 0))
    with stat2:
        st.metric("Edges", case_detail.get("edge_count", 0))
    with stat3:
        st.metric("SARs", case_detail.get("sar_count", 0))
    with stat4:
        st.metric("Risk Score", f"{case_detail.get('risk_score', 0):.4f}")

    # Typology badges
    case_typologies = case_detail.get("typologies", [])
    if case_typologies:
        badge_html = " ".join(
            f"<span style='display:inline-block;padding:0.25rem 0.6rem;"
            f"border-radius:12px;background:{typ_colors.get(t, '#374151')}22;"
            f"color:{typ_colors.get(t, '#9CA3AF')};font-weight:600;"
            f"font-size:0.85rem;margin-right:0.4rem;border:1px solid "
            f"{typ_colors.get(t, '#374151')};'>{t}</span>"
            for t in case_typologies
        )
        st.markdown(f"**Typologies:** {badge_html}", unsafe_allow_html=True)

    # Reasons
    case_reasons = case_detail.get("reasons", [])
    if case_reasons:
        st.markdown(f"**Reasons:** {', '.join(case_reasons)}")

    # Entity table
    entities = case_detail.get("entities", [])
    if entities:
        st.markdown("**Entities:**")
        ent_df = pd.DataFrame(entities)
        ent_display = [
            c for c in ["entity_id", "entity_type", "is_seed", "is_sar",
                         "risk_score", "tier", "degree"]
            if c in ent_df.columns
        ]
        ent_df = ent_df[ent_display]
        if "risk_score" in ent_df.columns:
            ent_df["risk_score"] = ent_df["risk_score"].round(4)
        st.dataframe(ent_df, width="stretch", height=250)

    # Interactive network graph (Plotly)
    edges = case_detail.get("edges", [])
    if entities and len(entities) > 1:
        st.markdown("**Network Graph:**")
        _render_case_network(entities, edges, case_typologies)

    # Download case JSON
    case_json_str = json.dumps(case_detail, indent=2)
    st.download_button(
        label="Download Case JSON",
        data=case_json_str,
        file_name=f"case_{selected_case_id[:12]}.json",
        mime="application/json",
        key="cases_download",
    )


def _render_case_network(entities: list, edges: list, typologies: list):
    """Render an interactive Plotly network graph for a case."""
    import math

    node_ids = [e["entity_id"] for e in entities]
    node_map = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)

    # Circular layout
    positions = {}
    for i, nid in enumerate(node_ids):
        angle = 2 * math.pi * i / n
        positions[nid] = (math.cos(angle), math.sin(angle))

    # Edge traces
    edge_x, edge_y = [], []
    for e in edges:
        src, dst = e.get("src"), e.get("dst")
        if src in positions and dst in positions:
            x0, y0 = positions[src]
            x1, y1 = positions[dst]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=0.8, color="#4B5563"),
        hoverinfo="none",
    )

    # Node traces
    node_x = [positions[nid][0] for nid in node_ids]
    node_y = [positions[nid][1] for nid in node_ids]
    node_colors = []
    node_sizes = []
    node_texts = []

    for e in entities:
        if e.get("is_seed"):
            node_colors.append("#EF4444" if e.get("is_sar") else "#FBBF24")
            node_sizes.append(14)
        elif e.get("is_sar"):
            node_colors.append("#22C55E")
            node_sizes.append(11)
        else:
            node_colors.append("#6B7280")
            node_sizes.append(8)
        node_texts.append(
            f"ID: {e['entity_id'][:12]}<br>"
            f"Type: {e.get('entity_type', '?')}<br>"
            f"Tier: {e.get('tier', '?')}<br>"
            f"Score: {e.get('risk_score', 0):.4f}<br>"
            f"Degree: {e.get('degree', 0)}<br>"
            f"SAR: {'Yes' if e.get('is_sar') else 'No'}<br>"
            f"Seed: {'Yes' if e.get('is_seed') else 'No'}"
        )

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers",
        marker=dict(size=node_sizes, color=node_colors, line=dict(width=1, color="#1F2937")),
        text=node_texts,
        hoverinfo="text",
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    apply_modern_terminal_plotly()
    fig.update_layout(
        showlegend=False,
        height=450,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    )

    # Legend annotation
    legend_text = (
        "<span style='color:#FBBF24'>● Seed</span> &nbsp; "
        "<span style='color:#EF4444'>● Seed+SAR</span> &nbsp; "
        "<span style='color:#22C55E'>● SAR</span> &nbsp; "
        "<span style='color:#6B7280'>● Other</span>"
    )
    st.markdown(legend_text, unsafe_allow_html=True)
    st.plotly_chart(fig, width="stretch")


# --- AML Scores Tab ---

def render_aml_scores_tab():
    """Render the AML Scores tab with composite risk scores per party."""
    st.header("AML Risk Scores — Composite Party Scoring")

    # Run selector
    runs = api_request("GET", "/runs/?limit=15")
    if not runs:
        st.info("No pipeline runs found. Start a run first.")
        return

    completed_runs = [r for r in runs if r["status"] == "completed"]
    if not completed_runs:
        st.info("No completed runs found. Complete a pipeline run to view AML scores.")
        return

    run_options = {
        f"{r['id'][:8]}... - {format_datetime(r.get('completed_at') or r['created_at'])}": r["id"]
        for r in completed_runs
    }

    selected_label = st.selectbox(
        "Select Run", options=list(run_options.keys()), key="aml_scores_run_select"
    )
    selected_run_id = run_options[selected_label]

    # Load summary (or offer to compute)
    summary = api_request("GET", f"/runs/{selected_run_id}/aml-summary")
    if not summary or summary.get("detail"):
        st.info("AML scores have not been computed for this run yet.")
        if st.button("Compute AML Scores", key="aml_compute_init"):
            with st.spinner("Computing AML scores..."):
                result = api_request("POST", f"/runs/{selected_run_id}/aml-scores/compute")
            if result and not result.get("detail"):
                st.success(
                    f"AML scores computed for {result.get('total_scored', '?')} parties. "
                    "Refresh the page to view results."
                )
                st.rerun()
            else:
                detail = result.get("detail", "Unknown error") if result else "API unavailable"
                st.error(f"Scoring failed: {detail}")
        return

    band_dist = summary.get("band_distribution", {})
    band_colors = {
        "Critical": "#EF4444", "High": "#F59E0B",
        "Medium": "#3B82F6", "Low": "#6B7280",
    }

    # Degraded mode notice
    signals_available = summary.get("signals_available", [])
    all_signals = {"sar", "laundering", "network", "geo", "volume"}
    missing_signals = all_signals - set(signals_available)
    if missing_signals:
        missing_labels = ", ".join(sorted(missing_signals))
        st.warning(
            f"**Degraded scoring mode:** {len(signals_available)}/5 signals active "
            f"({', '.join(signals_available)}). "
            f"Missing signals ({missing_labels}) require enrichment data "
            f"(`extra_info.csv`). Band distribution may show empty bands."
        )

    # --- Filter controls ---
    st.markdown("---")
    col_band, col_score, col_sar, col_laun, col_search = st.columns([1.5, 1.5, 1, 1, 1.5])

    with col_band:
        band_labels = [
            f"Critical ({band_dist.get('Critical', 0)})",
            f"High ({band_dist.get('High', 0)})",
            f"Medium ({band_dist.get('Medium', 0)})",
            f"Low ({band_dist.get('Low', 0)})",
        ]
        band_values = ["Critical", "High", "Medium", "Low"]
        selected_band_labels = st.multiselect(
            "Risk Band", options=band_labels,
            default=[band_labels[0], band_labels[1]],
            key="aml_band",
        )
        selected_bands = [
            band_values[band_labels.index(lbl)]
            for lbl in selected_band_labels if lbl in band_labels
        ]

    with col_score:
        score_range = st.slider(
            "Score Range", min_value=0.0, max_value=100.0,
            value=(0.0, 100.0), step=1.0, key="aml_score_range",
        )

    with col_sar:
        sar_option = st.radio(
            "SAR Filter", ["All", "SAR Only", "Non-SAR"], key="aml_sar",
        )

    with col_laun:
        laun_option = st.radio(
            "Laundering", ["All", "Has Laundering"], key="aml_laun",
        )

    with col_search:
        search_text = st.text_input(
            "Search Entity ID", value="", key="aml_search",
        )

    # Sort controls
    sort_col1, sort_col2 = st.columns([1, 1])
    with sort_col1:
        sort_by = st.selectbox(
            "Sort By",
            options=["aml_score", "sar_signal", "laundering_signal",
                     "network_signal", "geo_signal", "volume_signal",
                     "txn_count", "total_amt"],
            index=0, key="aml_sort_by",
        )
    with sort_col2:
        sort_order = st.selectbox(
            "Order", options=["desc", "asc"], index=0, key="aml_sort_order",
        )

    # Build query params
    params = {
        "limit": 500, "offset": 0,
        "sort_by": sort_by, "sort_order": sort_order,
    }
    if selected_bands:
        params["band"] = selected_bands
    if score_range[0] > 0:
        params["min_score"] = score_range[0]
    if score_range[1] < 100:
        params["max_score"] = score_range[1]
    if sar_option == "SAR Only":
        params["is_sar"] = 1
    elif sar_option == "Non-SAR":
        params["is_sar"] = 0
    if laun_option == "Has Laundering":
        params["has_laundering"] = 1
    if search_text.strip():
        params["search"] = search_text.strip()

    # Fetch filtered scores
    score_data = api_request("GET", f"/runs/{selected_run_id}/aml-scores", params=params)
    if not score_data or score_data.get("detail"):
        st.warning("Could not load AML score data.")
        return

    rows = score_data.get("rows", [])
    total_filtered = len(rows)

    # --- KPI cards + recompute ---
    st.markdown("---")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi_btn = st.columns([1, 1, 1, 1, 1, 0.8])

    with kpi1:
        st.metric("Total Scored", f"{summary.get('total_scored', 0):,}")
    with kpi2:
        st.metric("Filtered", f"{total_filtered:,}")
    with kpi3:
        st.metric("Mean Score", f"{summary.get('mean_score', 0):.1f}")
    with kpi4:
        critical_ct = band_dist.get("Critical", 0)
        high_ct = band_dist.get("High", 0)
        st.metric("Critical + High", f"{critical_ct + high_ct:,}")
    with kpi5:
        st.metric("Median Score", f"{summary.get('median_score', 0):.1f}")
    with kpi_btn:
        st.caption("")  # spacer for alignment
        if st.button("Recompute", key="aml_recompute"):
            with st.spinner("Recomputing AML scores..."):
                result = api_request("POST", f"/runs/{selected_run_id}/aml-scores/compute")
            if result and not result.get("detail"):
                st.success("Scores recomputed.")
                st.rerun()
            else:
                detail = result.get("detail", "Unknown error") if result else "API unavailable"
                st.error(f"Failed: {detail}")

    # --- Band breakdown ---
    band_cols = st.columns(4)
    for i, band_name in enumerate(["Critical", "High", "Medium", "Low"]):
        with band_cols[i]:
            count = band_dist.get(band_name, 0)
            total_scored = max(summary.get("total_scored", 1), 1)
            pct = (count / total_scored) * 100
            color = band_colors[band_name]
            st.markdown(
                f"<div style='text-align:center;padding:0.5rem;border-radius:6px;"
                f"border:1px solid {color};'>"
                f"<span style='color:{color};font-weight:700;font-size:1.1rem;'>{band_name}</span><br>"
                f"<span style='color:#E5E7EB;font-size:1.3rem;font-weight:600;'>{count:,}</span><br>"
                f"<span style='color:#9CA3AF;font-size:0.85rem;'>{pct:.1f}%</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("")

    # --- Data table ---
    if rows:
        df = pd.DataFrame(rows)

        display_cols = [
            c for c in [
                "entity_id", "risk_band", "aml_score", "is_sar",
                "sar_signal", "laundering_signal", "network_signal",
                "geo_signal", "volume_signal",
                "degree", "txn_count", "total_amt",
                "laundering_txn_count", "cross_border_count",
                "reasons",
            ]
            if c in df.columns
        ]
        df_display = df[display_cols].copy()

        # Round numeric columns
        for col in ["aml_score", "sar_signal", "laundering_signal",
                     "network_signal", "geo_signal", "volume_signal", "total_amt"]:
            if col in df_display.columns:
                df_display[col] = df_display[col].round(3)

        st.dataframe(
            df_display,
            width="stretch",
            height=500,
            column_config={
                "entity_id": st.column_config.TextColumn("Entity ID"),
                "risk_band": st.column_config.TextColumn("Band"),
                "aml_score": st.column_config.NumberColumn("AML Score", format="%.1f"),
                "is_sar": st.column_config.NumberColumn("SAR", format="%d"),
                "sar_signal": st.column_config.NumberColumn("SAR Sig", format="%.3f"),
                "laundering_signal": st.column_config.NumberColumn("Laun Sig", format="%.3f"),
                "network_signal": st.column_config.NumberColumn("Net Sig", format="%.3f"),
                "geo_signal": st.column_config.NumberColumn("Geo Sig", format="%.3f"),
                "volume_signal": st.column_config.NumberColumn("Vol Sig", format="%.3f"),
                "degree": st.column_config.NumberColumn("Degree", format="%d"),
                "txn_count": st.column_config.NumberColumn("Txn Count", format="%d"),
                "total_amt": st.column_config.NumberColumn("Total Amt", format="%.2f"),
                "laundering_txn_count": st.column_config.NumberColumn("Laun Txns", format="%d"),
                "cross_border_count": st.column_config.NumberColumn("Cross-Border", format="%d"),
                "reasons": st.column_config.TextColumn("Reasons"),
            },
        )

        # Download
        csv_data = df_display.to_csv(index=False)
        st.download_button(
            label="Download Filtered AML Scores (CSV)",
            data=csv_data,
            file_name=f"aml_scores_{selected_run_id[:8]}_filtered.csv",
            mime="text/csv",
            key="aml_download",
        )
        # --- Per-entity signal contribution ---
        st.markdown("---")
        st.subheader("Signal Contribution — Entity Detail")
        signal_cols_detail = ["sar_signal", "laundering_signal", "network_signal",
                              "geo_signal", "volume_signal"]
        signal_labels = {"sar_signal": "SAR", "laundering_signal": "Laundering",
                         "network_signal": "Network", "geo_signal": "Geo",
                         "volume_signal": "Volume"}
        signal_colors_map = {"SAR": "#EF4444", "Laundering": "#F59E0B",
                             "Network": "#8B5CF6", "Geo": "#3B82F6", "Volume": "#22C55E"}

        entity_options = df_display["entity_id"].head(50).tolist()
        if entity_options:
            selected_entity = st.selectbox(
                "Select entity to inspect",
                options=entity_options,
                key="aml_entity_detail",
            )
            entity_row = df[df["entity_id"] == selected_entity].iloc[0]

            detail_vals = []
            detail_labels = []
            detail_colors = []
            for sc in signal_cols_detail:
                if sc in entity_row.index:
                    val = float(entity_row[sc])
                    label = signal_labels[sc]
                    detail_vals.append(val)
                    detail_labels.append(label)
                    detail_colors.append(signal_colors_map.get(label, "#6B7280"))

            if detail_vals:
                fig_bar = go.Figure(go.Bar(
                    x=detail_labels,
                    y=detail_vals,
                    marker_color=detail_colors,
                    text=[f"{v:.3f}" for v in detail_vals],
                    textposition="outside",
                ))
                apply_modern_terminal_plotly()
                fig_bar.update_layout(
                    height=300,
                    margin=dict(l=40, r=20, t=30, b=40),
                    yaxis=dict(range=[0, 1.15], title="Signal Strength"),
                    xaxis=dict(title=""),
                )
                col_chart, col_info = st.columns([2, 1])
                with col_chart:
                    st.plotly_chart(fig_bar, width="stretch")
                with col_info:
                    st.markdown(f"**Entity:** `{selected_entity}`")
                    st.markdown(f"**AML Score:** {entity_row.get('aml_score', 0):.1f}")
                    st.markdown(f"**Band:** {entity_row.get('risk_band', 'N/A')}")
                    st.markdown(f"**SAR:** {'Yes' if entity_row.get('is_sar', 0) else 'No'}")
                    st.markdown(f"**Degree:** {int(entity_row.get('degree', 0))}")
                    reasons = entity_row.get("reasons", "")
                    if reasons:
                        st.markdown("**Reasons:**")
                        for r in str(reasons).split(", "):
                            st.markdown(f"- `{r}`")
    else:
        st.info("No entities match the current filters.")

    # --- Score distribution histogram ---
    if rows and len(rows) > 5:
        st.markdown("---")
        st.subheader("AML Score Distribution")
        df_chart = pd.DataFrame(rows)
        if "aml_score" in df_chart.columns and "risk_band" in df_chart.columns:
            fig = px.histogram(
                df_chart,
                x="aml_score",
                color="risk_band",
                nbins=50,
                color_discrete_map=band_colors,
                labels={"aml_score": "AML Score", "risk_band": "Risk Band"},
            )
            apply_modern_terminal_plotly()
            fig.update_layout(
                height=340,
                margin=dict(l=40, r=20, t=30, b=40),
                barmode="overlay",
                legend=dict(orientation="h", y=1.08),
            )
            fig.update_traces(opacity=0.75)
            st.plotly_chart(fig, width="stretch")

    # --- Signal radar chart for top entities ---
    if rows and len(rows) > 0:
        st.markdown("---")
        st.subheader("Signal Breakdown — Top Entities")

        signal_cols = ["sar_signal", "laundering_signal", "network_signal",
                       "geo_signal", "volume_signal"]
        df_radar = pd.DataFrame(rows[:10])  # top 10 by current sort

        if all(c in df_radar.columns for c in signal_cols):
            fig_radar = go.Figure()
            categories = ["SAR", "Laundering", "Network", "Geo", "Volume"]

            for _, row in df_radar.head(5).iterrows():
                values = [row[c] for c in signal_cols]
                values.append(values[0])  # close the radar
                eid = str(row.get("entity_id", "?"))[:12]
                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=categories + [categories[0]],
                    name=eid,
                    fill="toself",
                    opacity=0.5,
                ))

            apply_modern_terminal_plotly()
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 1]),
                    bgcolor="rgba(0,0,0,0)",
                ),
                height=420,
                margin=dict(l=60, r=60, t=40, b=40),
                legend=dict(orientation="h", y=-0.15),
            )
            st.plotly_chart(fig_radar, width="stretch")


# --- Main ---

def main():
    """Main application entry point."""
    render_sidebar()

    # Tab navigation
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "🚀 Run", "📊 Status", "📈 Dashboard", "🔬 Analytics",
        "📄 Report", "🎛 Interactive", "⚡ Tier Queue", "🧩 Cases",
        "🎯 AML Scores",
    ])

    with tab1:
        render_run_tab()

    with tab2:
        render_status_tab()

    with tab3:
        render_dashboard_tab()

    with tab4:
        render_analytics_tab()

    with tab5:
        render_report_tab()

    with tab6:
        render_interactive_dashboard_tab()

    with tab7:
        render_tier_queue_tab()

    with tab8:
        render_cases_tab()

    with tab9:
        render_aml_scores_tab()


if __name__ == "__main__":
    main()
