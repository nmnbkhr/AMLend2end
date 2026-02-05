#!/bin/bash
# ============================================================
# AML E2E Pipeline — Environment Setup & Kernel Fix
# Env: amgan2 (PyTorch 2.6 + CUDA 12.4)
# Usage: ./fix_kernel.sh [--install]
# ============================================================

set -e
ENV_NAME="amgan2"
CONDA_BASE="/opt/miniconda"

echo "========================================"
echo "  AML E2E — Kernel & Environment Fix"
echo "  Environment: $ENV_NAME"
echo "========================================"

# ── 1. Kill stale Jupyter kernels ──
echo ""
echo "[1/5] Killing stale Jupyter kernels..."
pkill -9 -f ipykernel_launcher 2>/dev/null || true
pkill -9 -f "jupyter-notebook" 2>/dev/null || true
pkill -9 -f "jupyter-lab" 2>/dev/null || true
sleep 1

# ── 2. Clear Jupyter runtime files ──
echo "[2/5] Clearing Jupyter runtime files..."
rm -rf /run/user/$(id -u)/jupyter/runtime/* 2>/dev/null || true
rm -rf ~/.local/share/jupyter/runtime/* 2>/dev/null || true
rm -rf /tmp/jupyter-* 2>/dev/null || true

# ── 3. Activate environment ──
echo "[3/5] Activating $ENV_NAME..."
source "$CONDA_BASE/bin/activate" "$ENV_NAME"
echo "  Python: $(python --version)"
echo "  PyTorch: $(python -c 'import torch; print(torch.__version__)')"

# ── 4. Install missing packages ──
if [[ "$1" == "--install" ]]; then
    echo "[4/5] Installing missing packages..."

    # Core ML
    pip install -q scikit-learn seaborn ipykernel ipywidgets

    # PyTorch Geometric (matches torch 2.5.x + cu121)
    pip install -q torch_geometric
    pip install -q torch_scatter torch_sparse torch_cluster torch_spline_conv \
        -f https://data.pyg.org/whl/torch-2.6.0+cu124.html

    # Dashboard
    pip install -q dash dash-bootstrap-components kaleido

    # Background workers & API
    pip install -q celery redis

    # Misc
    pip install -q pyyaml jinja2 Pillow sqlalchemy requests

    echo "  Package install complete."
else
    echo "[4/5] Checking packages (run with --install to fix missing)..."
    MISSING=""
    for pkg in torch_geometric sklearn dash dash_bootstrap_components seaborn ipykernel kaleido celery redis; do
        python -c "import $pkg" 2>/dev/null || MISSING="$MISSING $pkg"
    done
    if [ -n "$MISSING" ]; then
        echo "  MISSING:$MISSING"
        echo "  Run: ./fix_kernel.sh --install"
    else
        echo "  All packages OK."
    fi
fi

# ── 5. Register Jupyter kernel ──
echo "[5/5] Registering $ENV_NAME kernel..."
python -m ipykernel install --user --name "$ENV_NAME" --display-name "$ENV_NAME"

echo ""
echo "========================================"
echo "  Done! Next steps in VS Code:"
echo "  1. Ctrl+Shift+P → Developer: Reload Window"
echo "  2. Open notebook → Select kernel: $ENV_NAME"
echo "========================================"
