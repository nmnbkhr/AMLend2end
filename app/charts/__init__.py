"""
Chart Generation Module — Headless Plotly chart creation for AML Pipeline.

All functions accept DataFrames/arrays and return go.Figure objects.
No Streamlit imports anywhere in this package.
"""

from .exporter import export_all_charts, export_chart_group
