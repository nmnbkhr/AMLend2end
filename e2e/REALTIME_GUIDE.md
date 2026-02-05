# Real-Time AML Simulator — Run Guide

## Prerequisites

Run these notebooks **in order** first (they create model files):

```
00_simulate_transactions.ipynb   → generates demodata/*.csv
01_data_loading_and_features     → creates e2e/data/*.parquet
02_graph_sage_embeddings         → creates e2e/models/graphsage.pt, e2e/embeddings/
03_wgan_gp_anomaly_detector      → creates e2e/models/encoder.pt, generator.pt
04_scoring_and_visualization     → creates e2e/results/
05_predict_and_evaluate          → creates e2e/results/predictions.parquet
```

## Required Files (verify before running)

```bash
# From e2e/ directory, check these exist:
ls models/graphsage.pt models/encoder.pt models/generator.pt
ls models/feature_norm.pt models/training_meta.json models/X_train.npy
ls data/node_features.parquet data/edges.parquet
ls ../demodata/party.csv
```

## Step-by-Step

### Step 1 — Open the notebook

Open `e2e/11_realtime_simulator.ipynb` in VSCode.
Select kernel: **amgan2**

### Step 2 — Run cells 0-7 (setup)

Run cells sequentially:

| Cell | What it does | Expected output |
|------|-------------|-----------------|
| 0 | Markdown header | (nothing) |
| 1 | Imports + GPU check | `Device: cuda`, GPU name, 0.0 MB allocated |
| 2 | Configuration | `80 batches × 50 txns = 4,000 total txns` |
| 3 | GraphSAGE class | `GraphSAGE class defined` |
| 4 | TransactionStream class | `TransactionStream defined` |
| 5 | LiveGraph class | `LiveGraph class defined` |
| 6 | RealtimeScorer class | `RealtimeScorer class defined` |
| 7 | Initialize components | `LiveGraph initialized: 7,500 nodes, 67,100 edges` |
|   |                       | `RealtimeScorer ready` |
|   |                       | `Threshold (P99): X.XXXX` |

**If cell 7 fails:** models are missing. Go back and run notebooks 01-05.

### Step 3 — Run cell 8 (simulation)

This is the **main loop**. It will:
- Generate 80 batches of 50 transactions each
- Score nodes with GraphSAGE + WGAN-GP every 3 batches
- Update a **live 4-panel dashboard** every 0.5 seconds

**What you see (updating live):**

```
┌─────────────────────┬─────────────────────┐
│  Score Time Series  │    Alert Feed       │
│  (rolling line      │    (table of last   │
│   chart + threshold)│     12 alerts)      │
├─────────────────────┼─────────────────────┤
│  Confusion Matrix   │  Score Distribution │
│  (TP/FP/FN/TN       │  (histogram normal  │
│   heatmap)          │   vs SAR)           │
└─────────────────────┴─────────────────────┘

Batch 42/80: 53 txns (3 laundering) | 78 nodes affected | 2 new alerts | 185ms
```

**Duration:** ~2-3 minutes (80 batches × 0.5s + scoring time)

**To stop early:** Interrupt kernel (square button). It will print partial results.

### Step 4 — Run cell 9 (final summary)

Shows complete stats:

```
  REAL-TIME SIMULATION SUMMARY
  Duration:           120.5s
  Transactions:       4,350
  Patterns injected:  8
  Total alerts:       245
  Precision:          0.XXXX
  Recall:             0.XXXX
  Latency — Mean: 150ms, P95: 280ms
  Throughput: 35 txns/sec
```

### Step 5 — Run cell 10 (alert investigation)

Shows the **ego-graph** of the highest-scoring alert node:
- Red node = the flagged account
- Orange nodes = SAR neighbors
- Blue nodes = clean neighbors
- Arrows = money flow direction

### Step 6 — Run cell 11 (latency analysis)

Two charts:
- **Left:** Latency per batch (red bars = full rescore, blue = cached)
- **Right:** Latency histogram with P95 line

Target: P95 < 500ms → PASS

### Step 7 — Run cell 12 (GPU cleanup)

Frees all GPU memory. Run this before opening another notebook.

## What to Check

### The simulation is working if:

1. **Dashboard updates live** — panels refresh every 0.5s
2. **Alerts appear** — red triangles on score time series, entries in alert feed
3. **Confusion matrix changes** — TP count increases as patterns are injected
4. **Score distribution** — SAR histogram (red) is shifted right of normal (blue)
5. **Latency** — rescore batches ~150-300ms, cached batches ~1ms

### Red flags (something wrong):

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No module 'torch_geometric'` | Wrong kernel | Select amgan2 kernel |
| `FileNotFoundError: models/` | Notebooks 01-05 not run | Run pipeline first |
| Dashboard shows 0 alerts after 30+ batches | Threshold too high | Lower `THRESHOLD_PERCENTILE` to 95 |
| Latency > 1000ms | GPU not available | Check `device` prints `cuda` |
| Kernel crashes | GPU OOM | Restart kernel, close other notebooks |

## Configuration Tuning

Edit cell 2 to adjust:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `NUM_BATCHES` | 80 | More batches = longer simulation |
| `BATCH_SIZE` | 50 | More txns per batch = more data |
| `BATCH_INTERVAL` | 0.5 | Seconds between dashboard refreshes |
| `PATTERN_PROB` | 0.10 | Higher = more laundering patterns |
| `RESCORE_INTERVAL` | 3 | Lower = more accurate but slower |
| `THRESHOLD_PERCENTILE` | 99 | Lower = more alerts, more false positives |
