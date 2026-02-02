# AML End-to-End: Graph-Based Anti-Money Laundering Detection

## Overview

This project implements a **Graph Neural Network-based Anti-Money Laundering (AML) detection system** that analyzes transaction networks to identify suspicious activities. The system uses **Node2Vec embeddings** combined with an **Autoencoder-based anomaly detector** to flag potentially fraudulent nodes.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AML DETECTION PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Raw Data → Graph Construction → Node Embeddings → Anomaly Detection → Rules│
│                                                                             │
│  ┌──────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │Nodes │ →  │ Network  │ →  │ Node2Vec │ →  │Autoencoder│ →  │ Patterns │  │
│  │Edges │    │  Graph   │    │ Vectors  │    │  Model   │    │  & Rules │  │
│  └──────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
AMLend2end/
├── 1_create_feature_groups.ipynb      # Data loading & graph creation
├── 2_prep_training_dataset_for_embeddings.ipynb  # Prepare edge data
├── 3_maggy_node_embeddings.ipynb      # Node2Vec hyperparameter tuning
├── 4_compute_node_embeddings.ipynb    # Generate node embeddings
├── 5_predict_and_create_node_embeddings_fg.ipynb  # Create embedding features
├── 6_create_anomaly_detection_td.ipynb # Prepare anomaly detection dataset
├── 7_maggy_adversarial_aml.ipynb      # Autoencoder hyperparameter tuning
├── 8_train_adversarial_aml.ipynb      # Train anomaly detection model
├── 9_aml_model_server.ipynb           # Model serving & inference
├── 10_visualize_results.ipynb         # Visualization & analysis
├── 11_analytical_dashboard.ipynb      # Interactive dashboard
├── 12_aml_pattern_analysis.ipynb      # Pattern extraction & rules
│
├── training_data/                     # Generated datasets
│   ├── edges_td.csv                   # Transaction edges
│   ├── node_td.csv                    # Node information
│   └── gan/                           # Training/eval splits
│
├── output/                            # Results & visualizations
│   ├── node_embeddings_fg.parquet     # Node embeddings with scores
│   ├── *.png                          # Visualization outputs
│   └── aml_rules.json                 # Extracted detection rules
│
├── models/                            # Trained models
│   └── gan_anomaly_*/                 # Saved autoencoder model
│
├── Resources/                         # Configuration files
│   ├── embeddings_best_hp.json        # Best Node2Vec hyperparameters
│   └── gan_best_hp.json               # Best autoencoder hyperparameters
│
└── adversarialaml/                    # Original GAN library (reference)
```

---

## Quick Start

### Prerequisites

```bash
# Create conda environment
conda create -n amlgan python=3.10 -y
conda activate amlgan

# Install dependencies
pip install tensorflow pandas numpy networkx matplotlib scikit-learn
pip install node2vec pyarrow seaborn ipywidgets
```

### Run the Pipeline

Execute notebooks in order (1-12):

```bash
# Option 1: Run in Jupyter
jupyter notebook

# Option 2: Run in VS Code
# Open each .ipynb file and run with amlgan kernel
```

**Recommended execution order:**

| Step | Notebook | Purpose | Time |
|------|----------|---------|------|
| 1 | `1_create_feature_groups.ipynb` | Load data, create graph | ~1 min |
| 2 | `2_prep_training_dataset_for_embeddings.ipynb` | Prepare edges | ~1 min |
| 3 | `3_maggy_node_embeddings.ipynb` | Tune Node2Vec params | ~5 min |
| 4 | `4_compute_node_embeddings.ipynb` | Generate embeddings | ~3 min |
| 5 | `5_predict_and_create_node_embeddings_fg.ipynb` | Create features | ~2 min |
| 6 | `6_create_anomaly_detection_td.ipynb` | Prepare training data | ~1 min |
| 7 | `7_maggy_adversarial_aml.ipynb` | Tune autoencoder | ~3 min |
| 8 | `8_train_adversarial_aml.ipynb` | Train model | ~2 min |
| 9 | `9_aml_model_server.ipynb` | Test inference | ~1 min |
| 10 | `10_visualize_results.ipynb` | Visualizations | ~2 min |
| 11 | `11_analytical_dashboard.ipynb` | Dashboard | ~3 min |
| 12 | `12_aml_pattern_analysis.ipynb` | Extract rules | ~2 min |

---

## Detailed Notebook Guide

### Notebook 1: Create Feature Groups
**Purpose:** Load raw transaction data and create the transaction graph.

**Input:** Raw transaction/party data
**Output:** `training_data/edges_td.csv`, `training_data/node_td.csv`

**Key columns:**
- `edges_td.csv`: source, target, tran_id, tx_type, base_amt
- `node_td.csv`: id, type, is_sar (if available)

---

### Notebook 2: Prepare Training Dataset for Embeddings
**Purpose:** Format edge data for Node2Vec processing.

**Output:** Cleaned edge list for graph embedding

---

### Notebook 3: Node2Vec Hyperparameter Tuning
**Purpose:** Find optimal Node2Vec parameters using random search.

**Hyperparameters tuned:**
| Parameter | Description | Search Range |
|-----------|-------------|--------------|
| `walk_length` | Length of random walks | 2-10 |
| `walk_number` | Number of walks per node | 2-10 |
| `emb_size` | Embedding dimension | 16, 32, 64 |

**Output:** `Resources/embeddings_best_hp.json`

---

### Notebook 4: Compute Node Embeddings
**Purpose:** Generate Node2Vec embeddings for all nodes.

**How it works:**
1. Create random walks on the transaction graph
2. Train Word2Vec on walks (nodes as "words")
3. Extract learned node vectors

**Output:** Node embedding vectors (32-dimensional by default)

---

### Notebook 5: Create Node Embeddings Feature Group
**Purpose:** Merge embeddings with node labels.

**Output:** `output/node_embeddings_fg.parquet`

**Columns:** id, is_sar, emb_0, emb_1, ..., emb_31

---

### Notebook 6: Create Anomaly Detection Training Dataset
**Purpose:** Split data for model training.

**Output:**
- `training_data/gan/X_train.npy` - Training embeddings
- `training_data/gan/y_train.npy` - Training labels
- `training_data/gan/X_eval.npy` - Evaluation embeddings
- `training_data/gan/y_eval.npy` - Evaluation labels

---

### Notebook 7: Autoencoder Hyperparameter Tuning
**Purpose:** Find optimal autoencoder architecture.

**Hyperparameters tuned:**
| Parameter | Description | Search Range |
|-----------|-------------|--------------|
| `latent_dim` | Bottleneck size | 8, 16 |
| `n_layers` | Encoder/decoder depth | 2, 3 |
| `activation` | Activation function | relu, tanh |
| `dropout_rate` | Regularization | 0.0, 0.1 |
| `learning_rate` | Optimizer LR | 0.001, 0.0001 |

**Metric:** AUC (Area Under ROC Curve)

**Output:** `Resources/gan_best_hp.json`

---

### Notebook 8: Train Anomaly Detection Model
**Purpose:** Train the final autoencoder model.

**Architecture:**
```
Input (32) → Dense(16) → Dense(8) → Latent(8) → Dense(16) → Dense(32) → Output(32)
```

**Training:**
- Loss: MSE (Mean Squared Error)
- Epochs: 50
- Batch size: 32

**Output:**
- `models/gan_anomaly_*/anomaly_detector.keras`
- `models/gan_anomaly_*/threshold.npy`

---

### Notebook 9: Model Server
**Purpose:** Test model inference on new data.

**Usage:**
```python
# Load model
model = keras.models.load_model("models/gan_anomaly_*/anomaly_detector.keras")
threshold = np.load("models/gan_anomaly_*/threshold.npy")

# Predict
reconstructed = model.predict(embeddings)
anomaly_score = np.mean(np.square(embeddings - reconstructed), axis=1)
is_anomaly = anomaly_score > threshold
```

---

### Notebook 10: Visualize Results
**Purpose:** Generate visualizations of detection results.

**Outputs:**
- `transaction_network.png` - Network graph with anomalies highlighted
- `anomaly_distribution.png` - Score distribution
- `degree_distribution.png` - Network structure
- `money_flow_network.png` - Transaction flows
- `top_anomalies.png` - Highest risk nodes

---

### Notebook 11: Analytical Dashboard
**Purpose:** Multi-tab interactive dashboard.

**Tabs:**
1. **Executive Summary** - KPIs, risk distribution
2. **Loss vs Savings** - Financial impact analysis
3. **Risk Network** - Graph with edge color=risk, edge width=amount
4. **Transaction Deep Dive** - Amount/risk analysis
5. **Node Profiles** - Risk profiles by node type

**Key Features:**
- Edge visualization: **Width = Amount**, **Color = AML Risk**
- ROI calculations for detection program
- Interactive widgets (if ipywidgets installed)

---

### Notebook 12: Pattern Analysis & Rule Extraction
**Purpose:** Extract interpretable rules from detection results.

**Analyzes:**

#### Amount Patterns
- Total transaction volume thresholds
- Average/max transaction sizes
- Variance in amounts

#### Network Patterns
| Pattern | Indicator | AML Type |
|---------|-----------|----------|
| High fan-out | Many recipients | Structuring |
| High fan-in | Many sources | Collection |
| Hub nodes | High connectivity | Laundering hub |
| One-way flow | Imbalanced in/out | Layering |

#### Frequency Patterns
- Transaction counts
- Repeated transactions to same target
- Transaction velocity

**Output:** `output/aml_rules.json`

---

## Understanding Results

### Anomaly Score Interpretation

```
Score Range          Risk Level      Action
─────────────────────────────────────────────
< threshold          LOW             Monitor
threshold - 2x       MEDIUM          Review
2x - 3x threshold    HIGH            Investigate
> 3x threshold       CRITICAL        Escalate
```

### Key Metrics

| Metric | Description | Good Value |
|--------|-------------|------------|
| AUC | Model discrimination | > 0.7 |
| Precision | True positives / predictions | > 0.5 |
| Recall | True positives / actual | > 0.8 |
| Detection Rate | % flagged as suspicious | 1-10% |

### Sample Detection Rules (from notebook 12)

```
AMOUNT RULES:
├── Total volume > $150,000 → 98% suspicious
├── Max single transaction > $2,500 → 96% suspicious
└── High variance in amounts → 94% suspicious

NETWORK RULES:
├── Sends to > 15 unique recipients → 97% suspicious (STRUCTURING)
├── Receives from > 10 unique senders → 95% suspicious (COLLECTION)
└── Flow imbalance > 80% → 93% suspicious (LAYERING)

FREQUENCY RULES:
├── Total transactions > 50 → 96% suspicious
└── Repeated transactions to same target > 5 → 94% suspicious
```

---

## Customization

### Using Your Own Data

1. **Prepare edge data** (CSV):
```csv
source,target,tran_id,tx_type,base_amt
account_1,account_2,1,transfer,1000.00
account_2,account_3,2,payment,500.00
```

2. **Prepare node data** (CSV):
```csv
id,type,is_sar
account_1,0,0
account_2,1,1
```

3. **Update paths** in notebook 1:
```python
edges_df = pd.read_csv("your_edges.csv")
nodes_df = pd.read_csv("your_nodes.csv")
```

### Tuning Detection Sensitivity

**More sensitive (more alerts):**
```python
threshold = threshold * 0.8  # Lower threshold
```

**Less sensitive (fewer alerts):**
```python
threshold = threshold * 1.2  # Higher threshold
```

### Adding New Features

Edit notebook 12 to add custom features:
```python
# Example: Add time-based features
node_features['txn_per_day'] = node_features['total_txns'] / time_period
node_features['weekend_ratio'] = weekend_txns / total_txns
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `CuDNN version mismatch` | `pip install --upgrade nvidia-cudnn-cu12>=9.3.0` |
| `No module named seaborn` | `pip install seaborn` |
| `Widget CDN error` | Add `"jupyter.widgetScriptSources": ["jsdelivr.com", "unpkg.com"]` to VS Code settings |
| `Out of memory` | Reduce `MAX_NODES_VIS` in visualization notebooks |
| `KeyError: 'src'` | Check column names: use 'source'/'target' not 'src'/'dst' |

### GPU Issues

```bash
# Check GPU availability
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"

# Check CuDNN version
python -c "import tensorflow as tf; print(tf.sysconfig.get_build_info()['cudnn_version'])"
```

---

## Output Files Summary

| File | Location | Description |
|------|----------|-------------|
| `edges_td.csv` | training_data/ | Transaction edges |
| `node_td.csv` | training_data/ | Node information |
| `node_embeddings_fg.parquet` | output/ | Embeddings + scores |
| `anomaly_detector.keras` | models/gan_anomaly_*/ | Trained model |
| `threshold.npy` | models/gan_anomaly_*/ | Detection threshold |
| `aml_rules.json` | output/ | Extracted rules |
| `*.png` | output/ | Visualizations |

---

## Technical Details

### Node2Vec Algorithm

Node2Vec generates node embeddings by:
1. Performing biased random walks on the graph
2. Treating walks as "sentences" and nodes as "words"
3. Training Word2Vec to learn node representations

Parameters `p` and `q` control walk behavior:
- `p` (return): Likelihood of returning to previous node
- `q` (in-out): Likelihood of exploring outward

### Autoencoder Anomaly Detection

The autoencoder learns to compress and reconstruct **normal** transaction patterns:

```
Normal node → Encode → Latent → Decode → Low reconstruction error
AML node    → Encode → Latent → Decode → HIGH reconstruction error
```

High reconstruction error = Model hasn't seen this pattern = Anomaly

### Why This Approach Works

1. **Graph structure captures relationships** - Money laundering involves chains of transactions
2. **Embeddings encode neighborhood** - Similar transaction patterns have similar vectors
3. **Unsupervised learning** - Doesn't require labeled AML cases for training
4. **Interpretable rules** - Pattern analysis provides explainable alerts

---

## References

- [Node2Vec Paper](https://arxiv.org/abs/1607.00653)
- [GAN Anomaly Detection Paper](https://arxiv.org/pdf/1905.11034.pdf)
- [Original Hopsworks AML Demo](https://github.com/logicalclocks/hopsworks-tutorials)

---

## Contact & Support

For issues with this project:
1. Check the Troubleshooting section above
2. Review notebook outputs for error messages
3. Ensure all dependencies are installed in `amlgan` environment

---

*Generated: 2024 | AML End-to-End Detection System*
