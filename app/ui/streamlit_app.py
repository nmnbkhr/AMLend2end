"""
AML Pipeline Runner - Streamlit UI

A single-page application with tabs for:
- Run: Start new pipeline runs with profile selection
- Status: Monitor running/completed jobs with auto-refresh
- Dashboard: View visualizations, metrics, and anomaly data
- Report: Access and download generated reports

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


def api_request(method: str, endpoint: str, **kwargs) -> dict:
    """Make an API request and handle errors."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
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

    if st.button("🚀 Start Pipeline Run", type="primary", use_container_width=True):
        with st.spinner("Starting pipeline run..."):
            params = {
                "profile": selected_profile,
                "skip_hyperparameter_tuning": skip_hp,
                "generate_visualizations": gen_viz,
                "generate_report": gen_report,
                "notebook_timeout": custom_timeout,
            }

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

    # Progress bar
    st.progress(status_data["progress_percent"] / 100)

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
            use_container_width=True,
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
        st.markdown(f"""
        <div class="mt-card" style="text-align: center;">
            <div style="font-size: 2rem;">{emoji}</div>
            <div class="mt-kpi" style="color: {status_color};">{status.upper()}</div>
            <div class="mt-title">Status</div>
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
                                st.image(response.content, use_container_width=True)
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
            st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

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
                st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

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
            st.link_button("🔗 Open in Browser", report_url, use_container_width=True)
        with btn_col2:
            try:
                response = requests.get(report_url, timeout=15)
                if response.status_code == 200:
                    st.download_button(
                        label="📥 Download HTML",
                        data=response.content,
                        file_name=f"aml_report_{selected_run_id[:8]}.html",
                        mime="text/html",
                        use_container_width=True,
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
                        use_container_width=True,
                        help="ZIP containing metrics, report, alert data, and key plots"
                    )
                else:
                    st.button("📦 Bundle N/A", disabled=True, use_container_width=True,
                             help="Run bundle not available for this run")
            except Exception as e:
                st.button("📦 Bundle N/A", disabled=True, use_container_width=True)

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

    # Build absolute paths to data files using path utilities
    try:
        data_dir = get_data_dir(selected_run_id)
        run_dir = get_run_dir(selected_run_id)
    except ValueError as e:
        st.error(f"Invalid run ID: {e}")
        return

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
            st.plotly_chart(fig_donut, use_container_width=True)
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
            st.plotly_chart(fig_bar, use_container_width=True)

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
            st.plotly_chart(fig_heatmap, use_container_width=True)
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
                st.plotly_chart(fig_hist, use_container_width=True)

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
                st.plotly_chart(fig_top_degree, use_container_width=True)
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
                        st.plotly_chart(fig_pca, use_container_width=True)

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


# --- Sidebar ---

def render_sidebar():
    """Render the sidebar."""
    with st.sidebar:
        st.title("🔍 AML Pipeline")
        st.markdown("---")

        # System Status
        st.subheader("System Status")
        health = api_request("GET", "/status/health")

        if health:
            status_col1, status_col2 = st.columns(2)
            with status_col1:
                if health.get("database") == "healthy":
                    st.success("DB ✓")
                else:
                    st.error("DB ✗")
            with status_col2:
                celery_status = health.get("celery", "unknown")
                if celery_status == "healthy":
                    st.success("Worker ✓")
                elif celery_status == "no_workers":
                    st.warning("No Workers")
                else:
                    st.error("Worker ✗")
        else:
            st.error("API Offline")
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


# --- Main ---

def main():
    """Main application entry point."""
    render_sidebar()

    # Tab navigation
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🚀 Run", "📊 Status", "📈 Dashboard", "🔬 Analytics", "📄 Report"])

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


if __name__ == "__main__":
    main()
