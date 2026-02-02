# AML Pipeline Runner Application

A web-based interface for running and monitoring the AML end-to-end detection pipeline.

## Overview

This application provides:
- **Web UI** (Streamlit): Start runs, monitor progress, view dashboards and reports
- **REST API** (FastAPI): Programmatic access to all functionality
- **Background Processing** (Celery + Redis): Non-blocking notebook execution
- **Artifact Management**: Organized storage of all pipeline outputs

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit UI  │────▶│   FastAPI API   │────▶│  Celery Worker  │
│   (Port 8501)   │     │   (Port 8000)   │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                │                        │
                                ▼                        ▼
                        ┌───────────────┐      ┌─────────────────┐
                        │    SQLite     │      │   Notebooks     │
                        │   Database    │      │  (Papermill)    │
                        └───────────────┘      └────────┬────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │    Artifacts    │
                                               │  /artifacts/    │
                                               └─────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
# Ensure conda environment is activated
conda activate amlgan

# Install app-specific dependencies
pip install -r app/requirements.txt
```

### 2. Start Services (4 terminals)

**Terminal 1 - Redis:**
```bash
redis-server
```

**Terminal 2 - API Server:**
```bash
uvicorn app.api.main:app --reload --port 8000
```

**Terminal 3 - Celery Worker:**
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

**Terminal 4 - Streamlit UI:**
```bash
streamlit run app/ui/streamlit_app.py
```

### 3. Access the Application

- **Web UI**: http://localhost:8501
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/status/health

## Directory Structure

```
/app
├── api/                    # FastAPI REST API
│   ├── main.py            # App entry point
│   └── routes/            # API endpoints
│       ├── runs.py        # Run management
│       ├── status.py      # Status monitoring
│       └── artifacts.py   # Artifact access
├── workers/               # Celery background tasks
│   ├── celery_app.py     # Celery configuration
│   └── tasks.py          # Task definitions
├── pipeline_runner/       # Notebook orchestration
│   ├── orchestrator.py   # Main execution logic
│   ├── artifacts_index.py # Artifact indexing
│   ├── metrics_builder.py # Metrics extraction
│   └── output_map.yaml   # Deterministic output mapping
├── db/                    # Database models
│   ├── models.py         # SQLAlchemy models
│   └── session.py        # Session management
├── reports/              # Report generation
│   ├── generator.py      # Report builder
│   └── templates/        # Jinja2 templates
├── ui/                   # Streamlit interface
│   └── streamlit_app.py  # Single-file app
├── requirements.txt      # Dependencies
└── README_APP.md        # This file

/artifacts
└── runs/
    └── <run_id>/
        ├── data/              # Data files (CSV, Parquet)
        ├── models/            # Trained models
        ├── plots/             # Visualizations (PNG)
        ├── logs/              # Execution logs
        ├── notebooks_executed/ # Executed notebooks
        ├── metrics/           # metrics.json
        ├── report/            # HTML report
        └── artifact_index.json
```

## Run Profiles

| Profile  | Sample Size | Epochs | Threshold | Use Case |
|----------|-------------|--------|-----------|----------|
| Quick    | 5,000       | 2      | 0.99      | Testing  |
| Standard | 20,000      | 5      | 0.99      | Normal   |
| Heavy    | 100,000     | 10     | 0.995     | Full (12GB+ VRAM) |

## API Endpoints

### Runs
- `POST /runs/` - Start new pipeline run
- `GET /runs/` - List all runs
- `GET /runs/{run_id}` - Get run details
- `GET /runs/{run_id}/metrics` - Get run metrics
- `GET /runs/{run_id}/artifact-index` - Get artifact index
- `POST /runs/{run_id}/cancel` - Cancel running pipeline
- `GET /runs/profiles` - Get available run profiles

### Status
- `GET /status/health` - Health check
- `GET /status/{run_id}` - Detailed run status with steps
- `GET /status/{run_id}/logs` - Execution logs

### Artifacts
- `GET /artifacts/{run_id}` - List all artifacts
- `GET /artifacts/{run_id}/plots` - List visualizations
- `GET /artifacts/{run_id}/tables` - List data tables
- `GET /artifacts/{run_id}/table/{name}` - Get paginated table data with sorting
- `GET /artifacts/{run_id}/anomalies` - Get anomaly data (score filtering)
- `GET /artifacts/{run_id}/report` - Get HTML report
- `GET /artifacts/{run_id}/bundle` - Download run bundle ZIP
- `GET /artifacts/{run_id}/summary` - Get run summary with artifact counts
- `GET /artifacts/{run_id}/file/{path}` - Download file

## Run Bundle Download

Each completed run can be exported as a portable ZIP bundle containing all key artifacts:

**Bundle Contents:**
- `metrics/metrics.json` - Pipeline metrics and statistics
- `artifact_index.json` - Index of all generated artifacts
- `report/report.html` - Full HTML report
- `data/alert_nodes_td.csv` - Primary anomalies table (if available)
- `plots/` - Key visualizations:
  - `dashboard_executive.png`
  - `anomaly_distribution.png`
  - `top_anomalies.png`
  - `top_suspicious_by_volume.png`
- `logs/*.log` - Execution logs

**Download Methods:**
1. **Web UI**: Report tab → "Download Run Bundle" button
2. **API**: `GET /artifacts/{run_id}/bundle`

## Output Mapping

The pipeline uses `app/pipeline_runner/output_map.yaml` for deterministic file lookups:

- Maps artifact types to expected file paths
- Provides column aliases for flexible data handling
- Configures bundle contents and key plots
- Falls back to heuristics when exact paths not found

## Troubleshooting

### Redis Connection Failed
```
Error: Cannot connect to Redis at localhost:6379
```
**Solution:** Ensure Redis is running:
```bash
redis-server
# Or check if already running:
redis-cli ping
```

### Celery Worker Not Found
```
Error: No workers available
```
**Solution:** Start the Celery worker:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

### Notebook Execution Failed
Check the logs at:
```
artifacts/runs/<run_id>/logs/<notebook_name>.log
```

Common issues:
- **Kernel not found**: Install ipykernel in your environment
  ```bash
  pip install ipykernel
  python -m ipykernel install --user --name amlgan
  ```
- **Timeout**: Increase timeout in run parameters
- **Memory**: Reduce sample_size or use "quick" profile

### Database Errors
The SQLite database is stored at `app/aml_pipeline.db`. To reset:
```bash
rm app/aml_pipeline.db
# Restart the API server - it will recreate the database
```

## Adding New Notebooks/Steps

The orchestrator automatically discovers notebooks with the pattern `<number>_<name>.ipynb` in the project root.

1. Create your notebook following the naming pattern (e.g., `13_new_step.ipynb`)
2. Restart the API server to detect the new notebook
3. The step will be included in subsequent runs

To use papermill parameters in your notebook:
```python
# First cell tagged with "parameters"
run_id = ""
artifacts_dir = ""
sample_size = 20000
epochs = 5
threshold = 0.99
```

## Development

### Running Tests
```bash
pytest app/tests/
```

### Code Style
```bash
# Format
black app/

# Lint
flake8 app/
```

### Database Migrations
Currently using SQLite with auto-creation. For production, consider:
- Alembic for migrations
- PostgreSQL for concurrent access

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `API_URL` | `http://localhost:8000` | API URL for Streamlit |

## License

Part of the AML End-to-End Detection Pipeline project.
