# AML End-to-End: Technical Architecture & Deep Dive

---

## System Overview

A **12-step ML pipeline** that transforms raw financial transaction CSVs into graph-based anomaly detection results, served through a production web application with async task processing.

```
+-----------+     +------------+     +--------+     +-----------+     +-----------+
| Raw CSV   | --> | Graph      | --> | Node   | --> | GAN       | --> | Alerts &  |
| 9.5M rows |     | Construction|     | 2Vec   |     | Autoenc.  |     | Rules     |
+-----------+     +------------+     +--------+     +-----------+     +-----------+
                                                                           |
                        +--------------------------------------------------+
                        |
                        v
              +-------------------+     +----------+     +-----------+
              | FastAPI + Celery  | <-> |  Redis   | <-> | Streamlit |
              | (Orchestration)   |     | (Broker) |     | (UI)      |
              +-------------------+     +----------+     +-----------+
                        |
                        v
              +-------------------+
              | SQLite + Artifacts|
              | (Persistence)     |
              +-------------------+
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **ML Framework** | TensorFlow / Keras | 2.15+ |
| **Graph Embeddings** | Node2Vec + Word2Vec (Gensim) | 0.4.6 |
| **Graph Library** | NetworkX | 3.0+ |
| **Feature Engineering** | PySpark | - |
| **API** | FastAPI + Uvicorn | 0.109+ / 0.27+ |
| **Task Queue** | Celery + Redis | 5.3+ / 5.0+ |
| **UI** | Streamlit + Plotly | 1.30+ / 5.18+ |
| **ORM** | SQLAlchemy (SQLite) | 2.0+ |
| **Notebook Execution** | Papermill + nbclient | 2.5+ / 0.9+ |
| **HP Tuning** | Maggy | - |
| **Language** | Python | 3.10+ |

---

## Pipeline Architecture (12 Steps)

### Phase 1: Data Ingestion & Graph Construction

```
Step 1: Feature Group Creation
+---------------------+      +-----------------------+
| transactions.csv    | ---> | PySpark Feature Eng.  |
| party.csv           |      | - Encode tx types     |
| alert_transactions  |      | - Build edge list     |
+---------------------+      +-----------+-----------+
                                          |
                              +-----------v-----------+
                              | edges_td.csv          |
                              | node_td.csv           |
                              +-----------------------+

Step 2: Prepare Training Dataset
+---------------------+      +-----------------------+
| edges_td.csv        | ---> | Clean & format edges  |
|                     |      | for Node2Vec input    |
+---------------------+      +-----------------------+
```

**Transaction Types Encoded**: CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER, DEPOSIT

---

### Phase 2: Graph Embedding Generation

```
Step 3 (Optional): Node2Vec HP Tuning via Maggy
+------------------------------------------+
| Search Space:                            |
|   walk_length:  [2, 10]                  |
|   walk_number:  [2, 10]                  |
|   emb_size:     {16, 32, 64}            |
|   p (return):   [0.25, 4.0]            |
|   q (in-out):   [0.25, 4.0]            |
+------------------------------------------+
                    |
                    v
         embeddings_best_hp.json
         {walk_length:10, walk_number:10,
          emb_size:32, p:0.5, q:2.0}

Step 4: Compute Node Embeddings
+---------------------+
| Transaction Graph   |
+----------+----------+
           |
    Biased Random Walks
    (p=0.5 controls return,
     q=2.0 controls exploration)
           |
           v
+---------------------+
| "Sentences" of      |
| node sequences       |
+----------+----------+
           |
     Word2Vec Training
           |
           v
+---------------------+
| 32-dim embedding    |
| per node            |
+---------------------+

Step 5: Merge Embeddings + Labels
+---------------------+      +-----------------------+
| Node embeddings     | ---> | node_embeddings_fg    |
| Node labels (is_sar)|      |   .parquet            |
+---------------------+      | [id, is_sar,          |
                              |  emb_0..emb_31]       |
                              +-----------------------+
```

**Why Node2Vec?** Captures local graph topology. Nodes with similar transaction patterns (similar neighborhoods) get similar embeddings. Money laundering chains create distinctive structural fingerprints.

---

### Phase 3: Anomaly Detection Model

```
Step 6: Train/Eval Split
+---------------------+      +-----------------------+
| node_embeddings_fg  | ---> | X_train.npy (embeddings)|
|   .parquet          |      | y_train.npy (labels)    |
+---------------------+      | X_eval.npy              |
                              | y_eval.npy              |
                              +-----------------------+

Step 7 (Optional): Autoencoder HP Tuning via Maggy
+------------------------------------------+
| Search Space:                            |
|   latent_dim:    {8, 16}                |
|   n_layers:      {2, 3}                |
|   activation:    {relu, tanh}           |
|   dropout_rate:  {0.0, 0.1}            |
|   learning_rate: {0.001, 0.0001}        |
| Metric: AUC                             |
+------------------------------------------+
                    |
                    v
         gan_best_hp.json
         {latent_dim:8, n_layers:2,
          activation:relu, dropout:0.0,
          lr:0.0001}

Step 8: Train GAN Autoencoder
+-------------------------------------------------------+
|                 GAN Anomaly Detector                   |
|                                                        |
|  Generator: Latent(z) -> Dense -> Dense -> Fake(32d)  |
|  Discriminator: Input(32d) -> Dense -> Dense -> Real?  |
|  Encoder: Input(32d) -> Dense -> Dense -> Latent(z)   |
|                                                        |
|  Training Loop:                                        |
|    1. Train D on real embeddings vs G(z)               |
|    2. Train G to fool D                                |
|    3. Train E to reconstruct via G(E(x)) ~ x          |
|                                                        |
|  Loss: Wasserstein + Gradient Penalty (lambda=10)      |
|  Anomaly Score = MSE(x, G(E(x)))                      |
|  Threshold = percentile-based cutoff                   |
+-------------------------------------------------------+
```

**Autoencoder Architecture (default)**:
```
Input(32) -> Dense(16) -> Dense(8) -> [Latent(8)] -> Dense(16) -> Dense(32) -> Output(32)
                    Encoder                              Decoder
```

**Anomaly Detection Logic**:
```python
reconstructed = model.predict(embeddings)
anomaly_score = mean_squared_error(original, reconstructed, axis=1)
is_anomaly = anomaly_score > threshold  # Learned from training data
```

---

### Phase 4: Inference & Analysis

```
Step 9: Model Inference
+---------------------+      +-----------------------+
| New embeddings      | ---> | Anomaly scores        |
| Trained model       |      | Binary labels         |
| Threshold           |      | (anomaly / normal)    |
+---------------------+      +-----------------------+

Step 10: Visualization Generation
+-----------------------+
| Outputs:              |
| - transaction_network |  <-- NetworkX graph with risk coloring
| - anomaly_distribution|  <-- Score histogram
| - degree_distribution |  <-- Network topology analysis
| - money_flow_network  |  <-- Directed flow visualization
| - top_anomalies       |  <-- Highest-risk nodes
+-----------------------+

Step 11: Analytical Dashboard (Jupyter Widgets)
+-----------------------+
| Tabs:                 |
| 1. Executive Summary  |  <-- KPIs, risk distribution
| 2. Loss vs Savings    |  <-- Financial impact, ROI
| 3. Risk Network       |  <-- Interactive graph
| 4. Transaction Drill  |  <-- Amount/risk scatter
| 5. Node Profiles      |  <-- Per-node risk cards
+-----------------------+

Step 12: Pattern Analysis & Rule Extraction
+-----------------------+
| aml_rules.json        |
| Extracted patterns:   |
|   Amount patterns     |  <-- Volume, avg, max, variance thresholds
|   Network patterns    |  <-- Fan-out, fan-in, hub, flow analysis
|   Frequency patterns  |  <-- Count, velocity, repetition
|                       |
| Pattern -> Label:     |
|   High fan-out -> STRUCTURING/SMURFING
|   High fan-in  -> COLLECTION/AGGREGATION
|   Hub node     -> LAUNDERING HUB
|   One-way flow -> LAYERING
+-----------------------+
```

---

## Web Application Architecture

```
+-------------------------------------------------------------------+
|                        Streamlit UI (:8501)                        |
|   [Run Tab] [Status Tab] [Dashboard Tab] [Report Tab]            |
|   Terminal-dark theme | Plotly Bloomberg charts                   |
+-----+----------------------------------+-------------------------+
      |  HTTP                              |  HTTP
      v                                    v
+-------------------------------------------------------------------+
|                      FastAPI API (:8000)                           |
|                                                                    |
|  POST /runs          - Create pipeline run                        |
|  GET  /runs          - List all runs                              |
|  GET  /runs/{id}     - Run status + progress                     |
|  DELETE /runs/{id}   - Cancel run                                |
|  GET  /artifacts/... - Download plots, data, models               |
|  GET  /status/health - Health check                               |
|                                                                    |
|  CORS enabled | Pydantic validation | Path traversal protection  |
+-----+---------------------------------------------------------+--+
      |                                                          |
      v                                                          v
+------------------+                               +----------------+
|   Celery Worker  |                               |    SQLite DB   |
|   (2 concurrent) |                               |                |
|                  |                               | pipeline_runs  |
| run_pipeline_task|                               | step_logs      |
| cleanup_old_runs |                               |                |
| rebuild_index    |                               +----------------+
+--------+---------+
         |
         v
+------------------+      +-------------------------------------+
|   Redis (:6379)  |      |        Artifact Storage             |
|   Message Broker |      |                                     |
|   Result Backend |      |  artifacts/runs/{run_id}/           |
+------------------+      |    data/      (CSV, Parquet, NPY)   |
                          |    models/    (Keras, threshold)     |
                          |    plots/     (PNG visualizations)   |
                          |    report/    (HTML report)          |
                          |    logs/      (Execution logs)       |
                          |    notebooks_executed/               |
                          +-------------------------------------+
```

---

## Pipeline Orchestration

```python
# app/pipeline_runner/orchestrator.py (803 lines)

class PipelineOrchestrator:
    """
    Discovers numbered notebooks (1_*.ipynb, 2_*.ipynb, ...)
    Executes them sequentially via Papermill (nbclient fallback)
    Injects parameters per run profile
    Tracks progress via callbacks -> DB updates
    Collects artifacts into organized run directories
    """

# Execution flow:
notebooks = discover_notebooks()  # Glob for [0-9]*_*.ipynb
for i, notebook in enumerate(notebooks):
    update_progress(step=i, name=notebook.stem)
    execute_notebook(notebook, parameters=profile_params)
    collect_artifacts(notebook)
```

**Run Profiles**:
```
Quick:    { sample_size: 5K,   epochs: 2,  threshold: 0.99  }
Standard: { sample_size: 20K,  epochs: 5,  threshold: 0.99  }
Heavy:    { sample_size: 100K, epochs: 10, threshold: 0.995 }
```

**Task Limits**:
```
Hard timeout:  4 hours (14400s)
Soft timeout:  3h 45min (13500s)
Per-notebook:  30 min (1800s)
Concurrency:   2 workers max
```

---

## Data Flow Diagram

```
+----------------+     +------------------+     +-------------------+
| transactions   |     | PySpark Feature  |     | edges_td.csv      |
| .csv (9.5M)   | --> | Engineering      | --> | node_td.csv       |
| party.csv      |     | (Step 1-2)       |     |                   |
+----------------+     +------------------+     +---------+---------+
                                                          |
                                                          v
                                                +-------------------+
                                                | Node2Vec          |
                                                | Random Walks      |
                                                | Word2Vec Training |
                                                | (Step 3-5)        |
                                                +---------+---------+
                                                          |
                                                          v
                                                +-------------------+
                                                | 32-dim embeddings |
                                                | per node          |
                                                | + is_sar labels   |
                                                +---------+---------+
                                                          |
                                              +-----------+-----------+
                                              |                       |
                                              v                       v
                                    +----------------+     +-------------------+
                                    | Train/Eval     |     | GAN Autoencoder   |
                                    | Split          |     | Training          |
                                    | (Step 6)       |     | (Step 7-8)        |
                                    +-------+--------+     +---------+---------+
                                            |                        |
                                            +--------+  +------------+
                                                     |  |
                                                     v  v
                                            +-------------------+
                                            | Inference         |
                                            | Score = MSE(x,    |
                                            |   reconstruct(x)) |
                                            | (Step 9)          |
                                            +---------+---------+
                                                      |
                                        +-------------+-------------+
                                        |             |             |
                                        v             v             v
                              +------------+  +-------------+  +-----------+
                              | Viz & Plots|  | Dashboard   |  | Rule      |
                              | (Step 10)  |  | (Step 11)   |  | Extraction|
                              +------------+  +-------------+  | (Step 12) |
                                                               +-----------+
                                                                     |
                                                                     v
                                                              aml_rules.json
```

---

## Model Architecture Details

### GAN Anomaly Detector (`adversarialaml/gan_enc_ano.py`)

```
                    TRAINING PHASE
                    ==============

Real Embeddings (x)                    Random Noise (z)
       |                                      |
       v                                      v
+-------------+                      +-------------+
| Discriminator|  <--- Wasserstein   | Generator   |
| Dense(32)    |       Loss +        | Dense(z)    |
| Dense(16)    |       Gradient      | Dense(16)   |
| Dense(1)     |       Penalty       | Dense(32)   |
| -> Real/Fake |       (lambda=10)   | -> Fake(x') |
+-------------+                      +------+------+
                                            |
                    INFERENCE PHASE          |
                    ===============          |
                                            |
Real Embeddings (x)                         |
       |                                    |
       v                                    v
+-------------+                      +-------------+
| Encoder     |  ------> z -------> | Generator   |
| Dense(32)   |                      | (Decoder)   |
| Dense(16)   |                      | Dense(z)    |
| Dense(8)    |                      | Dense(16)   |
| -> Latent   |                      | Dense(32)   |
+-------------+                      +------+------+
       |                                    |
       |         x vs x'                    |
       +----------> MSE <------------------+
                     |
                     v
              Anomaly Score
              (high = suspicious)
```

### Node2Vec Embedding Process

```
Transaction Graph                     Random Walks
+---+     +---+                      Walk 1: A -> B -> C -> D -> B
| A |---->| B |----->+---+           Walk 2: A -> C -> A -> B -> D
+---+     +---+      | C |           Walk 3: B -> A -> C -> D -> C
  |                  +---+           ...
  v                    |
+---+                  v             Word2Vec
| D |<----------------+             +---+---+---+---+---+
+---+                               |0.2|0.5|..|0.1|0.3|  <- Node A (32-dim)
                                    +---+---+---+---+---+
p=0.5 (moderate return tendency)    |0.8|0.1|..|0.4|0.6|  <- Node B (32-dim)
q=2.0 (prefer local exploration)    +---+---+---+---+---+
```

---

## Database Schema

```sql
-- pipeline_runs
CREATE TABLE pipeline_runs (
    id              VARCHAR(36) PRIMARY KEY,  -- UUID
    status          ENUM('pending','running','completed','failed','cancelled'),
    current_step    INTEGER,
    total_steps     INTEGER,
    current_step_name VARCHAR(255),
    progress_percent FLOAT,
    created_at      DATETIME,
    started_at      DATETIME,
    completed_at    DATETIME,
    params          JSON,                     -- Run config
    total_nodes     INTEGER,                  -- Result metrics
    total_transactions INTEGER,
    anomalies_detected INTEGER,
    error_message   TEXT,
    celery_task_id  VARCHAR(255),
    artifact_path   VARCHAR(512)
);

-- step_logs
CREATE TABLE step_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          VARCHAR(36) REFERENCES pipeline_runs(id),
    step_number     INTEGER,
    step_name       VARCHAR(255),
    status          VARCHAR(50),  -- pending/running/completed/failed/skipped
    started_at      DATETIME,
    completed_at    DATETIME,
    log_output      TEXT,
    error_message   TEXT,
    metrics         JSON
);
```

---

## Service Orchestration (Makefile)

```
make run          Start all services
                  |
                  +-- make redis     Redis (:6379)       Message broker
                  +-- make api       FastAPI (:8000)      REST API + CORS
                  +-- make celery    Celery Worker        Background tasks
                  +-- make ui        Streamlit (:8501)    Dashboard UI

make stop         Graceful shutdown (SIGTERM -> SIGKILL)
make status       Health check all services
make logs         Tail all logs (redis.log, api.log, celery.log, ui.log)
make clean        Stop + remove .logs/

Dependency Chain: UI -> API -> Redis <- Celery
Conda env:        amlgan
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph embeddings | Node2Vec over GCN | Scalable to millions of nodes, no GPU required for embedding |
| Anomaly detection | GAN Autoencoder over Isolation Forest | Captures non-linear patterns in high-dimensional embeddings |
| Task processing | Celery over threading | Fault-tolerant, timeout control, distributed scaling |
| Notebook execution | Papermill | Parameterized runs, reproducibility, artifact capture |
| Database | SQLite over Postgres | Zero-config deployment, sufficient for single-instance |
| UI | Streamlit over React | Rapid iteration, Python-native, built-in data widgets |
| API | FastAPI over Flask | Async support, auto OpenAPI docs, Pydantic validation |

---

## Artifact Structure Per Run

```
artifacts/runs/{uuid}/
  +-- data/
  |     +-- edges_td.csv
  |     +-- node_td.csv
  |     +-- node_embeddings_fg.parquet
  |     +-- X_train.npy, y_train.npy
  |     +-- X_eval.npy, y_eval.npy
  +-- models/
  |     +-- anomaly_detector.keras
  |     +-- threshold.npy
  |     +-- metadata.json
  +-- plots/
  |     +-- transaction_network.png
  |     +-- anomaly_distribution.png
  |     +-- degree_distribution.png
  |     +-- money_flow_network.png
  |     +-- top_anomalies.png
  +-- report/
  |     +-- report.html
  +-- logs/
  |     +-- pipeline.log
  |     +-- metrics.json
  +-- notebooks_executed/
        +-- 1_create_feature_groups.ipynb
        +-- 2_prep_training_dataset.ipynb
        +-- ... (all executed notebooks with outputs)
```

---

## API Reference (Quick)

```
POST   /runs                          Create run (profile, data_source, params)
GET    /runs                          List all runs
GET    /runs/{id}                     Run status, progress, results
DELETE /runs/{id}                     Cancel running pipeline

GET    /artifacts/runs/{id}           List artifacts
GET    /artifacts/runs/{id}/files/*   Download specific file
GET    /artifacts/runs/{id}/index     JSON artifact manifest
GET    /artifacts/runs/{id}/plots     List visualization files
GET    /artifacts/runs/{id}/data      List data files

GET    /status/health                 API health check
GET    /status/profiles               Available run profiles
GET    /ping                          Simple ping
```

---

## Environment & Configuration

```bash
# Required
conda activate amlgan
redis-server                          # Message broker

# Environment Variables
REDIS_URL=redis://localhost:6379/0    # Celery broker URL
REPO_ROOT=/path/to/project            # Project root override
ARTIFACTS_ROOT=/custom/path           # Artifact storage override
API_URL=http://localhost:8000         # API endpoint for UI

# Data Sources
demo-data  -> /demodata/              # Built-in synthetic data (AMLSim)
saml-d     -> /mnt/e/xx/saml-d.csv   # External real-world benchmark
```

---

*Stack: Python 3.10+ | TensorFlow | Node2Vec | FastAPI | Celery | Redis | Streamlit | SQLAlchemy*
