# AML End-to-End Detection System -- Step-by-Step Run Guide

```text
 =====================================================================
  ANTI-MONEY LAUNDERING DETECTION PIPELINE
  Graph Embeddings + GAN Anomaly Detection
 =====================================================================
```

---

## TABLE OF CONTENTS

1. [System Requirements](#1-system-requirements)
2. [Installation (First-Time Setup)](#2-installation-first-time-setup)
3. [Data Sources & Location](#3-data-sources--location)
4. [Pre-Computed Demo Results (No GPU Needed)](#4-pre-computed-demo-results-no-gpu-needed)
5. [Starting the Services](#5-starting-the-services)
6. [Running the Pipeline](#6-running-the-pipeline)
7. [Pipeline Stages Explained (12 Steps)](#7-pipeline-stages-explained-12-steps)
8. [Where to Find Results](#8-where-to-find-results)
9. [Web Endpoints & API](#9-web-endpoints--api)
10. [Makefile Quick Reference](#10-makefile-quick-reference)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. SYSTEM REQUIREMENTS

```text
 HARDWARE                        SOFTWARE
 ========                        ========
 RAM .... 8 GB minimum           OS ......... Linux / macOS / Windows (WSL2)
          16 GB recommended      Python ..... 3.10 or 3.11
 GPU .... Optional               Conda ...... Miniconda or Anaconda
          (12 GB VRAM for        Redis ...... 6.0+
           "heavy" profile)      Git ........ 2.x+
 Disk ... 5 GB free space
```

---

## 2. INSTALLATION (First-Time Setup)

### Step 1 -- Clone the Repository

```bash
git clone https://github.com/logicalclocks/AMLend2end.git
cd AMLend2end
git checkout v3-enhance
```

### Step 2 -- Create Conda Environment

```bash
conda create -n amlgan python=3.10 -y
conda activate amlgan
```

### Step 3 -- Install Python Dependencies

```bash
# Core ML libraries (TensorFlow, Node2Vec, NetworkX, etc.)
pip install -e .

# Additional graph ML dependencies
pip install -r requirements.txt

# Web app stack (FastAPI, Celery, Streamlit, Papermill, etc.)
pip install -r app/requirements.txt
```

### Step 4 -- Register Jupyter Kernel

```bash
python -m ipykernel install --user --name amlgan --display-name "amlgan"
```

### Step 5 -- Install Redis

```bash
# Ubuntu / Debian / WSL2
sudo apt-get update && sudo apt-get install redis-server -y

# macOS
brew install redis

# Verify
redis-server --version
```

### Step 6 -- Verify Everything

```bash
make check-env
```

Expected output:

```text
  Checking prerequisites...
  -------------------------
  conda env (amlgan):  OK
  redis-server:        OK
  uvicorn:             OK
  celery:              OK
  streamlit:           OK
  -------------------------
  All prerequisites OK
```

### GPU Support (Optional)

```bash
pip install "aml_end_to_end[gpu]"
# Installs nvidia-cudnn-cu12 for CUDA-accelerated TensorFlow
```

---

## 3. DATA SOURCES & LOCATION

### Option A: Built-In Demo Data (Default -- No Download Needed)

```text
Location:  AMLend2end/demodata/
           |
           +-- transactions.csv        32 MB    9.5 million transaction rows
           |   Columns: datetime, id1, id2, amount, type ...
           |
           +-- party.csv               154 KB   ~1,500 account/party records
           |   Columns: id, country, type ...
           |
           +-- alert_transactions.csv   25 KB   Labeled suspicious transactions
               Columns: id1, id2, amount, alert_label ...
```

```text
  This data is INCLUDED in the repo. No external download required.
  Select "demo-data" when starting a pipeline run.
```

### Option B: SAML-D Dataset (Larger, External)

```text
Expected Location:  /mnt/e/xx/saml-d/
                    |
                    +-- transactions.csv       (larger dataset, ~100M+ rows)
                    +-- party.csv
                    +-- alert_transactions.csv
```

- Use notebook `0_map_saml_d_to_demodata.ipynb` for one-time data preparation
- Select `"saml-d"` as data_source when launching a run
- Artifacts are stored at `/mnt/e/xx/saml-d/artifacts/runs/<run_id>/`

### How Data Flows Through the Pipeline

```text
  transactions.csv ----+
                       |
  party.csv -----------+---> [Step 1] Feature Groups ---> edges_td.csv
                       |                                   node_td.csv
  alert_transactions --+
                                    |
                                    v
                           [Step 2-5] Graph Embeddings
                           Node2Vec: random walks on
                           transaction graph
                                    |
                                    v
                           node_embeddings_fg.parquet
                           (32-dimensional vectors per node)
                                    |
                                    v
                           [Step 6-8] GAN Anomaly Detector
                           Autoencoder + Discriminator
                                    |
                                    v
                           anomaly_scores + predictions
                                    |
                                    v
                           [Step 9-12] Visualization,
                           Reports, Cases, Risk Queue
```

---

## 4. PRE-COMPUTED DEMO RESULTS (NO GPU NEEDED)

```text
 =====================================================================
  DON'T HAVE A POWERFUL MACHINE?  NO PROBLEM.
  A complete pipeline run is ALREADY included in the repository.
  You can browse every result, plot, model, case, and report
  without running anything.
 =====================================================================
```

### What's Included

The repo ships with a **fully completed pipeline run** with all artifacts
pre-generated. This means you can explore the entire system output
on any machine -- no GPU, no training, no waiting.

```text
  Pre-computed Run ID:  4b36a26a-43ee-4793-817a-2a16f7ab4124
  Location:             artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/
  Pipeline Status:      COMPLETED (all 12 steps, 0 failures)
  Date Generated:       2026-02-04
```

### Demo Run Statistics

```text
  +----------------------------+-------------------+
  | Metric                     | Value             |
  +----------------------------+-------------------+
  | Transactions processed     | 20,084            |
  | Accounts/nodes analyzed    | 7,347             |
  | Graph edges                | 20,084            |
  | Embedding dimensions       | 32                |
  | Nodes embedded             | 6,897             |
  | Anomalies flagged          | 79                |
  | Anomaly rate               | 1.08%             |
  | Anomaly threshold          | 0.000275          |
  | Model training time        | ~29 seconds       |
  | Investigation cases        | 16                |
  | Entities in cases          | 1,589             |
  | Edges in cases             | 3,967             |
  +----------------------------+-------------------+
```

### Risk Tier Breakdown

```text
  Tier    Count    Description
  ----    -----    ----------------------------------
  T1       37      CRITICAL  -- Immediate investigation
  T2      110      HIGH      -- Priority review
  T3      221      MEDIUM    -- Scheduled review
  T4     6,979     LOW       -- Routine monitoring

  Risk formula: 2.0 * is_sar + 0.5 * log1p(degree)
```

### AML Typologies Detected

```text
  Pattern              Count    Description
  -------              -----    --------------------------------
  CIRCULAR_FLOW          12     Money cycling through loops
  FAN_IN                 12     Many sources -> single sink
  FAN_OUT                12     Single source -> many targets
  SAR_PROXIMITY           7     Near known suspicious accounts
  HUB_DOMINANCE           1     High-degree intermediary node
```

### Pre-Generated Artifacts Tree

```text
artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/
|
+-- data/                              [11 files]
|   +-- transactions_fg.parquet        Raw transaction features
|   +-- party_fg.parquet               Party/account features
|   +-- alert_transactions_fg.parquet  Labeled alert transactions
|   +-- alert_nodes_fg.parquet         Alert node features
|   +-- edges_td.csv                   Transaction graph edges
|   +-- node_td.csv                    Node labels
|   +-- alert_nodes_td.csv             79 detected anomalies
|   +-- node_embeddings.csv            Raw embeddings
|   +-- node_embeddings_fg.csv         Embeddings with features
|   +-- node_embeddings_fg.parquet     Embeddings (Parquet format)
|   +-- aml_rules.json                 Rule definitions
|
+-- models/
|   +-- gan_anomaly_97b5d8ec/
|   |   +-- anomaly_detector.keras     Trained GAN autoencoder
|   |   +-- threshold.npy              Learned anomaly threshold
|   |   +-- metadata.json              Model hyperparameters
|   +-- node_embeddings_a7eb6637/
|       +-- node2vec_model.model       Trained Node2Vec model
|       +-- node_embeddings.csv        Embedding vectors
|       +-- classifier.joblib          Embedding classifier
|       +-- metadata.json              Embedding hyperparameters
|
+-- plots/                             [18 visualizations]
|   +-- dashboard_executive.png        Executive summary dashboard
|   +-- anomaly_distribution.png       Score distribution chart
|   +-- top_anomalies.png              Top flagged entities
|   +-- top_suspicious_by_volume.png   Suspicious by transaction volume
|   +-- transaction_network.png        Full transaction graph
|   +-- degree_distribution.png        Node degree histogram
|   +-- money_flow_network.png         Money flow diagram
|   +-- money_flow_comparison.png      Normal vs suspicious flows
|   +-- transaction_amounts.png        Amount distribution
|   +-- top_anomaly_neighborhood.png   Neighborhood of top anomaly
|   +-- dashboard_loss_savings.png     Loss prevention estimates
|   +-- dashboard_risk_network.png     Risk-colored network
|   +-- dashboard_transaction_deepdive.png  Deep-dive analysis
|   +-- dashboard_node_profiles.png    Node profile comparison
|   +-- pattern_summary.png            AML pattern overview
|   +-- pattern_network.png            Pattern-specific network
|   +-- pattern_amounts.png            Pattern amount distribution
|   +-- pattern_feature_importance.png Feature importance chart
|   +-- styled/                        [18 Bloomberg-styled copies]
|
+-- report/
|   +-- report.html                    Full HTML report (open in browser)
|   +-- report_meta.json               Report metadata
|   +-- run_bundle.zip                 Portable ZIP of everything
|
+-- cases/                             [16 investigation cases]
|   +-- case_summary.json              Overview of all cases
|   +-- case_index.parquet             Searchable case index
|   +-- case_<uuid>.json               Individual case files (x16)
|
+-- queues/
|   +-- risk_queue.parquet             7,347 entities ranked by risk
|   +-- queue_summary.json             Tier counts and statistics
|   +-- operating_point.json           Threshold configuration
|
+-- metrics/
|   +-- metrics.json                   Aggregated run statistics
|
+-- logs/                              [10 execution logs]
|   +-- 1_create_feature_groups.log
|   +-- 2_prep_training_dataset_for_embeddings.log
|   +-- 4_compute_node_embeddings.log
|   +-- 5_predict_and_create_node_embeddings_fg.log
|   +-- 6_create_anomaly_detection_td.log
|   +-- 8_train_adversarial_aml.log
|   +-- 9_aml_model_server.log
|   +-- 10_visualize_results.log
|   +-- 11_analytical_dashboard.log
|   +-- 12_aml_pattern_analysis.log
|
+-- notebooks_executed/                [10 executed notebooks with outputs]
|
+-- artifact_index.json                Master catalog of all artifacts
```

### Pre-Trained Models (Experiment History)

In addition to the run artifacts, the repo includes multiple pre-trained
models from hyperparameter experiments:

```text
models/
|
+-- Node2Vec Embedding Models (8 experiments)
|   +-- node_embeddings_50d5b2b0/
|   +-- node_embeddings_ad7b307a/
|   +-- node_embeddings_eb5f6d0c/
|   +-- node_embeddings_47339e97/
|   +-- node_embeddings_e2366de4/
|   +-- node_embeddings_0cf6becf/
|   +-- node_embeddings_5782f9ca/
|   +-- node_embeddings_124c817d/
|   Each contains: node2vec_model.model, node_embeddings.csv,
|                  classifier.joblib, metadata.json
|
+-- GAN Anomaly Detector Models (7 experiments)
    +-- gan_anomaly_5f5ae592/
    +-- gan_anomaly_4026b40d/
    +-- gan_anomaly_53390658/
    +-- gan_anomaly_6102bcd9/
    +-- gan_anomaly_30a33f36/
    +-- gan_anomaly_884c8bf0/
    +-- gan_anomaly_f6ee3607/
    Each contains: anomaly_detector.keras, threshold.npy, metadata.json
```

```text
  Best hyperparameters are saved in:
    Resources/embeddings_best_hp.json   (Node2Vec)
    Resources/gan_best_hp.json          (GAN Autoencoder)
```

### How to Browse Demo Results Without Running the Pipeline

#### Option 1: Open files directly

```bash
# View the HTML report in your browser
xdg-open artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/report/report.html

# View a plot
xdg-open artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/plots/dashboard_executive.png

# View anomaly data
head -20 artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/data/alert_nodes_td.csv

# View case summary
cat artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/cases/case_summary.json

# View risk queue summary
cat artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/queues/queue_summary.json

# View run metrics
cat artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/metrics/metrics.json
```

#### Option 2: Start the web UI and browse via dashboard

```bash
# Install + start services (see Section 2 & 5)
make run

# Open Streamlit at http://localhost:8501
# The completed run will appear in the Status tab
# Browse all tabs: Dashboard, Analytics, Report, Interactive, Queue, Cases
```

#### Option 3: Use the REST API

```bash
# Start the API server
make run

# List runs (the pre-computed run will appear)
curl http://localhost:8000/runs/

# Get run metrics
curl http://localhost:8000/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/metrics

# List all artifacts
curl http://localhost:8000/artifacts/4b36a26a-43ee-4793-817a-2a16f7ab4124

# Get anomaly data
curl http://localhost:8000/artifacts/4b36a26a-43ee-4793-817a-2a16f7ab4124/anomalies

# Download the full bundle
curl -O http://localhost:8000/artifacts/4b36a26a-43ee-4793-817a-2a16f7ab4124/bundle
```

#### Option 4: Download the portable ZIP bundle

```bash
# The bundle is ready to share -- contains report + key data + plots
ls -lh artifacts/runs/4b36a26a-43ee-4793-817a-2a16f7ab4124/report/run_bundle.zip
```

---

## 5. STARTING THE SERVICES

### Quick Start (One Command)

```bash
cd AMLend2end
conda activate amlgan
make run
```

This starts **4 services** in the correct order:

```text
  +-------------------+     +-------------------+
  |   Redis Server    |     |   FastAPI Server   |
  |   Port: 6379      |<----|   Port: 8000       |
  |   Message Broker   |     |   REST API         |
  +-------------------+     +-------------------+
           ^                         ^
           |                         |
  +-------------------+     +-------------------+
  |   Celery Worker   |     |   Streamlit UI    |
  |   Background Jobs |     |   Port: 8501       |
  |   Runs Notebooks  |     |   Web Dashboard    |
  +-------------------+     +-------------------+
```

### Manual Start (4 Separate Terminals)

#### Terminal 1 -- Redis

```bash
redis-server
```

#### Terminal 2 -- FastAPI

```bash
conda activate amlgan
cd AMLend2end
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

#### Terminal 3 -- Celery Worker

```bash
conda activate amlgan
cd AMLend2end
celery -A app.workers.celery_app worker -l info
```

#### Terminal 4 -- Streamlit UI

```bash
conda activate amlgan
cd AMLend2end
streamlit run app/ui/streamlit_app.py --server.port 8501 --server.headless true
```

### Access Points After Startup

| Service         | URL                                    |
|-----------------|----------------------------------------|
| Streamlit UI    | `http://localhost:8501`                |
| API Docs        | `http://localhost:8000/docs`           |
| Health Check    | `http://localhost:8000/status/health`  |

---

## 6. RUNNING THE PIPELINE

### Option A: Via Streamlit UI (Recommended)

1. Open `http://localhost:8501`
2. Go to the **Run** tab
3. Select a **profile**:

```text
  +----------+----------------+--------+-----------+--------------------+
  | Profile  | Sample Size    | Epochs | Threshold | Use Case           |
  +----------+----------------+--------+-----------+--------------------+
  | quick    | 5,000 nodes    | 2      | 0.99      | Testing & demos    |
  | standard | 20,000 nodes   | 5      | 0.99      | Normal runs        |
  | heavy    | 100,000 nodes  | 10     | 0.995     | Full analysis      |
  +----------+----------------+--------+-----------+--------------------+
```

1. Select **data source**: `demo-data` or `saml-d`
2. Click **Start Run**
3. Switch to the **Status** tab to monitor progress (auto-refreshes every 2s)

### Option B: Via API (cURL)

```bash
# Start a "quick" run with demo data
curl -X POST http://localhost:8000/runs/ \
  -H "Content-Type: application/json" \
  -d '{"profile": "quick", "data_source": "demo-data"}'

# Response:
# {"run_id": "abc123-...", "status": "pending"}
```

```bash
# Check status
curl http://localhost:8000/status/<run_id>

# List all runs
curl http://localhost:8000/runs/

# Cancel a run
curl -X POST http://localhost:8000/runs/<run_id>/cancel
```

### Option C: Run Individual Notebooks Manually

```bash
conda activate amlgan
cd AMLend2end
jupyter lab
```

Open notebooks in order (1 through 12) and run each cell.
Set `artifacts_dir` parameter in each notebook if you want a custom output path.

---

## 7. PIPELINE STAGES EXPLAINED (12 Steps)

```text
 ===================================================================
  PHASE A: DATA INGESTION & GRAPH CONSTRUCTION        [Steps 1-2]
 ===================================================================
```

### Step 1: Create Feature Groups

Notebook: `1_create_feature_groups.ipynb`

```text
  Input:   demodata/transactions.csv, party.csv, alert_transactions.csv
  Output:  edges_td.csv, node_td.csv
  Action:  Feature engineering, encode transaction types,
           build graph edge list from raw transaction data
```

### Step 2: Prepare Training Dataset for Embeddings

Notebook: `2_prep_training_dataset_for_embeddings.ipynb`

```text
  Input:   edges_td.csv
  Output:  Cleaned edge list for Node2Vec
  Action:  Format and clean graph edges for embedding training
```

```text
 ===================================================================
  PHASE B: GRAPH EMBEDDING GENERATION                  [Steps 3-5]
 ===================================================================
```

### Step 3: Node Embedding Hyperparameter Tuning (OPTIONAL)

Notebook: `3_maggy_node_embeddings.ipynb`

```text
  Input:   Edge list
  Output:  embeddings_best_hp.json
  Action:  Grid search over walk_length, walk_number, embedding_size, p, q
  Skip:    Set skip_hyperparameter_tuning=True (uses Resources/embeddings_best_hp.json)
```

### Step 4: Compute Node Embeddings

Notebook: `4_compute_node_embeddings.ipynb`

```text
  Input:   Transaction graph edges
  Output:  32-dimensional embedding per node
  Action:  Biased random walks (Node2Vec) -> Word2Vec training
           Captures structural patterns in the transaction network
```

### Step 5: Create Embeddings Feature Group

Notebook: `5_predict_and_create_node_embeddings_fg.ipynb`

```text
  Input:   Node embeddings + node labels
  Output:  node_embeddings_fg.parquet  [id, is_sar, emb_0 ... emb_31]
  Action:  Combine embeddings with labels for model training
```

```text
 ===================================================================
  PHASE C: ANOMALY DETECTION MODEL                     [Steps 6-8]
 ===================================================================
```

### Step 6: Create Anomaly Detection Training Dataset

Notebook: `6_create_anomaly_detection_td.ipynb`

```text
  Input:   node_embeddings_fg.parquet
  Output:  X_train.npy, y_train.npy, X_eval.npy, y_eval.npy
  Action:  Train/eval split of 32-dim embeddings + binary labels
```

### Step 7: GAN Hyperparameter Tuning (OPTIONAL)

Notebook: `7_maggy_adversarial_aml.ipynb`

```text
  Input:   Training data
  Output:  gan_best_hp.json
  Action:  Grid search over latent_dim, n_layers, activation, dropout_rate, lr
  Skip:    Set skip_hyperparameter_tuning=True (uses Resources/gan_best_hp.json)
```

### Step 8: Train GAN Anomaly Detector

Notebook: `8_train_adversarial_aml.ipynb`

```text
  Input:   X_train.npy, y_train.npy
  Output:  models/gan_anomaly_<uuid>/
           +-- anomaly_detector.keras    (trained model)
           +-- threshold.npy             (anomaly threshold)
           +-- metadata.json             (model info)
  Action:  Train Encoder->Decoder (Autoencoder) + Discriminator (GAN)
           Learn reconstruction threshold from training anomaly scores
```

```text
 ===================================================================
  PHASE D: INFERENCE & VISUALIZATION                   [Steps 9-12]
 ===================================================================
```

### Step 9: Model Inference Testing

Notebook: `9_aml_model_server.ipynb`

```text
  Input:   Trained model + test nodes
  Output:  Anomaly scores + binary predictions
  Action:  Validate model predictions before dashboard generation
```

### Step 10: Visualize Results

Notebook: `10_visualize_results.ipynb`

```text
  Output:  plots/
           +-- dashboard_executive.png
           +-- anomaly_distribution.png
           +-- top_anomalies.png
           +-- top_suspicious_by_volume.png
           +-- transaction_network.png
           +-- pattern_summary.png
```

### Step 11: Analytical Dashboard

Notebook: `11_analytical_dashboard.ipynb`

```text
  Output:  report/report.html          (full HTML report)
           report/report_meta.json     (metadata)
           report/run_bundle.zip       (portable ZIP)
```

### Step 12: AML Pattern Analysis

Notebook: `12_aml_pattern_analysis.ipynb`

```text
  Output:  Pattern classifications (fan-out, hub, cycle, structuring)
           cases/case_index.parquet    (investigation cases)
           queues/risk_queue.parquet   (risk-ranked entity queue)
  Action:  Detect AML typologies:
           - Fan-out:     1 source -> many destinations
           - Hub:         High-degree intermediary nodes
           - Cycles:      Circular money flows
           - Structuring: Frequent small transfers below thresholds
```

```text
 ===================================================================
  COMPLETE PIPELINE FLOW DIAGRAM
 ===================================================================

  [CSV Data]
      |
      v
  +--Step 1--+   +--Step 2--+   +--Step 3--+   +--Step 4--+   +--Step 5--+
  | Feature  |-->| Prep     |-->| HP Tune  |-->| Node2Vec |-->| Embed FG |
  | Groups   |   | Edges    |   | (skip?)  |   | Embeddings|  | Parquet  |
  +----------+   +----------+   +----------+   +----------+   +----------+
                                                                    |
      +-------------------------------------------------------------+
      |
      v
  +--Step 6--+   +--Step 7--+   +--Step 8--+   +--Step 9--+
  | Train/   |-->| HP Tune  |-->| Train    |-->| Inference|
  | Eval     |   | GAN      |   | GAN AE   |   | Test     |
  | Split    |   | (skip?)  |   | Model    |   |          |
  +----------+   +----------+   +----------+   +----------+
                                                    |
      +---------------------------------------------+
      |
      v
  +--Step 10-+   +--Step 11-+   +--Step 12-+
  | Visualize|-->| HTML     |-->| Pattern  |
  | Plots    |   | Report   |   | Analysis |
  +----------+   +----------+   +----------+
                                     |
                                     v
                              [Dashboard Ready]
                              Cases + Risk Queue
```

---

## 8. WHERE TO FIND RESULTS

After a pipeline run completes, all artifacts are stored under:

```text
artifacts/runs/<run_id>/
|
+-- data/                        Processed data files
|   +-- edges_td.csv             Transaction graph edges
|   +-- node_td.csv              Node labels/features
|   +-- alert_nodes_td.csv       Detected anomalies
|   +-- node_embeddings_fg.parquet  32-dim node embeddings
|
+-- models/                      Trained ML models
|   +-- gan_anomaly_<uuid>/
|       +-- anomaly_detector.keras
|       +-- threshold.npy
|       +-- metadata.json
|
+-- plots/                       PNG visualizations
|   +-- dashboard_executive.png
|   +-- anomaly_distribution.png
|   +-- top_anomalies.png
|   +-- transaction_network.png
|   +-- pattern_summary.png
|
+-- logs/                        Per-notebook execution logs
|   +-- 1_create_feature_groups.log
|   +-- 4_compute_node_embeddings.log
|   +-- ...
|
+-- notebooks_executed/          Executed notebook copies (with outputs)
|
+-- metrics/
|   +-- metrics.json             Aggregated statistics
|
+-- report/
|   +-- report.html              Full HTML report
|   +-- run_bundle.zip           Portable download bundle
|
+-- cases/                       AML investigation case files
|   +-- case_index.parquet
|   +-- case_summary.json
|   +-- case_<uuid>.json         Individual case detail
|
+-- queues/                      Risk-ranked entity queue
|   +-- risk_queue.parquet
|   +-- operating_point.json
|   +-- queue_summary.json
|
+-- artifact_index.json          Master catalog of all artifacts
```

---

## 9. WEB ENDPOINTS & API

### Streamlit UI Tabs

```text
  +------+--------+-----------+-----------+--------+-------------+--------+-------+
  | Run  | Status | Dashboard | Analytics | Report | Interactive | Queue  | Cases |
  +------+--------+-----------+-----------+--------+-------------+--------+-------+
    |        |          |           |          |          |           |        |
    |        |          |           |          |          |           |        +-> Investigation cases
    |        |          |           |          |          |           +-> Risk-ranked entities
    |        |          |           |          |          +-> 5 interactive analysis sub-tabs
    |        |          |           |          +-> Download HTML report & ZIP bundle
    |        |          |           +-> Interactive Plotly charts
    |        |          +-> View plots, metrics, anomaly data
    |        +-> Live progress monitoring (auto-refresh 2s)
    +-> Start new run (profile + data source)
```

### REST API Endpoints

| Method | Endpoint                            | Description                         |
|--------|-------------------------------------|-------------------------------------|
| POST   | `/runs/`                            | Create & start a new pipeline run   |
| GET    | `/runs/`                            | List all runs                       |
| GET    | `/runs/{id}`                        | Get run details                     |
| GET    | `/runs/{id}/metrics`                | Get dashboard metrics               |
| POST   | `/runs/{id}/cancel`                 | Cancel running pipeline             |
| GET    | `/runs/profiles`                    | List available profiles             |
| GET    | `/status/health`                    | Health check                        |
| GET    | `/status/{id}`                      | Detailed run status                 |
| GET    | `/status/{id}/logs`                 | Execution logs                      |
| GET    | `/artifacts/{id}`                   | List all artifacts                  |
| GET    | `/artifacts/{id}/plots`             | List visualization files            |
| GET    | `/artifacts/{id}/tables`            | List data tables                    |
| GET    | `/artifacts/{id}/anomalies`         | Get anomaly data                    |
| GET    | `/artifacts/{id}/report`            | Get HTML report                     |
| GET    | `/artifacts/{id}/bundle`            | Download ZIP bundle                 |
| GET    | `/artifacts/{id}/summary`           | Run summary with counts             |

Full interactive docs at: `http://localhost:8000/docs`

---

## 10. MAKEFILE QUICK REFERENCE

```bash
make run          # Start all 4 services (Redis -> API -> Celery -> Streamlit)
make stop         # Stop all services
make status       # Check which services are running
make logs         # Tail all service logs (Ctrl+C to stop)
make clean        # Stop all + delete log files

make redis        # Start Redis only
make api          # Start FastAPI only (auto-starts Redis)
make celery       # Start Celery only (auto-starts Redis)
make ui           # Start Streamlit only (auto-starts API + Redis)

make check-env    # Verify all prerequisites are installed
make kill-orphans # Kill leftover processes from crashed runs
make help         # Show all available commands
```

### Log Files Location

```text
.logs/
+-- redis.log       Redis server log
+-- api.log         FastAPI server log
+-- celery.log      Celery worker log
+-- ui.log          Streamlit UI log
```

---

## 11. TROUBLESHOOTING

### "Redis connection refused"

```bash
# Check if Redis is running
redis-cli ping
# Expected: PONG

# Start Redis manually
redis-server --daemonize yes
```

### "No module named 'adversarialaml'"

```bash
conda activate amlgan
pip install -e .     # Installs the project in editable mode
```

### "Kernel 'amlgan' not found" during pipeline execution

```bash
conda activate amlgan
python -m ipykernel install --user --name amlgan --display-name "amlgan"
```

### Port already in use

```bash
make kill-orphans    # Kills stale processes on ports 8000 and 8501
# or manually:
fuser -k 8000/tcp
fuser -k 8501/tcp
```

### Celery worker crashes or hangs

```bash
make stop
make kill-orphans
make run             # Fresh restart
```

### TensorFlow GPU not detected

```bash
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
# If empty, install GPU support:
pip install "aml_end_to_end[gpu]"
```

### Pipeline stuck at a step

```bash
# Check Celery logs
tail -f .logs/celery.log

# Check specific step log in artifacts
cat artifacts/runs/<run_id>/logs/<step_name>.log

# Cancel and retry
curl -X POST http://localhost:8000/runs/<run_id>/cancel
```

---

## QUICK START SUMMARY

```text
  1.  git clone ... && cd AMLend2end && git checkout v3-enhance
  2.  conda create -n amlgan python=3.10 -y && conda activate amlgan
  3.  pip install -e . && pip install -r requirements.txt && pip install -r app/requirements.txt
  4.  python -m ipykernel install --user --name amlgan
  5.  sudo apt-get install redis-server -y
  6.  make check-env
  7.  make run
  8.  Open http://localhost:8501
  9.  Select "quick" profile + "demo-data" -> Start Run
  10. Monitor in Status tab -> View results in Dashboard tab
```

```text
 =====================================================================
  Demo data is pre-loaded. No external downloads needed.
  The "quick" profile completes the fastest -- use it for first runs.
  Pre-computed results are in artifacts/ -- browse without running.
 =====================================================================
```
