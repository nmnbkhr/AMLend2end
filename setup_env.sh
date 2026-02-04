#!/usr/bin/env bash
# =============================================================================
# AML End-to-End — Environment Setup Script
# =============================================================================
# Usage:
#   chmod +x setup_env.sh
#   ./setup_env.sh          # CPU-only install
#   ./setup_env.sh --gpu    # Include GPU (CUDA) support
#
# What this script does:
#   1. Checks prerequisites (conda, Python >= 3.10)
#   2. Creates (or updates) a conda environment named "amlgan"
#   3. Installs all Python dependencies from requirements.txt
#   4. Installs the project in editable mode (pip install -e .)
#   5. Installs Redis server (via apt or conda)
#   6. Runs a quick verification of key imports
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
ENV_NAME="amlgan"
PYTHON_VERSION="3.10"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU=false

# ── Parse arguments ──────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --gpu) GPU=true ;;
        --help|-h)
            echo "Usage: $0 [--gpu]"
            echo "  --gpu   Install NVIDIA CUDA/cuDNN support for GPU training"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--gpu]"
            exit 1
            ;;
    esac
done

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "  ${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "  ${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "  ${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "  ${RED}[FAIL]${NC}  $*"; exit 1; }

echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║   AML End-to-End — Environment Setup                ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Check prerequisites ─────────────────────────────────────────────
info "Checking prerequisites..."

# Check conda
if ! command -v conda &>/dev/null; then
    fail "conda not found. Install Miniconda or Anaconda first:
         https://docs.conda.io/en/latest/miniconda.html"
fi
ok "conda found: $(conda --version)"

# ── Step 2: Create or update conda environment ──────────────────────────────
if conda env list 2>/dev/null | grep -q "^${ENV_NAME} "; then
    info "Conda environment '${ENV_NAME}' already exists — will update it"
else
    info "Creating conda environment '${ENV_NAME}' with Python ${PYTHON_VERSION}..."
    conda create -y -n "${ENV_NAME}" python="${PYTHON_VERSION}"
    ok "Conda environment '${ENV_NAME}' created"
fi

# Activate environment
info "Activating environment '${ENV_NAME}'..."
eval "$(conda shell.bash hook)"
conda activate "${ENV_NAME}"
ok "Active Python: $(python --version) at $(which python)"

# ── Step 3: Upgrade pip ─────────────────────────────────────────────────────
info "Upgrading pip, setuptools, wheel..."
pip install --upgrade pip setuptools wheel -q
ok "pip $(pip --version | awk '{print $2}')"

# ── Step 4: Install Python dependencies ─────────────────────────────────────
info "Installing Python dependencies from requirements.txt..."
pip install -r "${SCRIPT_DIR}/requirements.txt"
ok "All Python dependencies installed"

# ── Step 5: GPU support (optional) ──────────────────────────────────────────
if [ "$GPU" = true ]; then
    info "Installing GPU support (nvidia-cudnn-cu12)..."
    pip install "nvidia-cudnn-cu12>=9.3.0"
    ok "GPU dependencies installed"
else
    info "Skipping GPU dependencies (use --gpu to include them)"
fi

# ── Step 6: Install project in editable mode ────────────────────────────────
info "Installing project in editable mode (pip install -e .)..."
pip install -e "${SCRIPT_DIR}"
ok "Project 'aml_end_to_end' installed"

# ── Step 7: Install Redis ───────────────────────────────────────────────────
if command -v redis-server &>/dev/null; then
    ok "Redis already installed: $(redis-server --version | head -c 40)"
else
    info "Installing Redis server..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq redis-server
    else
        conda install -y -c conda-forge redis
    fi
    if command -v redis-server &>/dev/null; then
        ok "Redis installed"
    else
        warn "Could not install Redis automatically. Please install it manually."
    fi
fi

# ── Step 8: Create required directories ─────────────────────────────────────
info "Creating project directories..."
mkdir -p "${SCRIPT_DIR}"/{.logs,artifacts/runs,output,savedmodels}
ok "Directories ready"

# ── Step 9: Verify installation ─────────────────────────────────────────────
info "Verifying key imports..."

VERIFY_SCRIPT='
import sys
errors = []
packages = [
    ("tensorflow",  "TensorFlow"),
    ("numpy",       "NumPy"),
    ("pandas",      "Pandas"),
    ("sklearn",     "scikit-learn"),
    ("networkx",    "NetworkX"),
    ("fastapi",     "FastAPI"),
    ("celery",      "Celery"),
    ("streamlit",   "Streamlit"),
    ("sqlalchemy",  "SQLAlchemy"),
    ("plotly",      "Plotly"),
    ("jinja2",      "Jinja2"),
    ("PIL",         "Pillow"),
    ("yaml",        "PyYAML"),
    ("requests",    "Requests"),
    ("pyarrow",     "PyArrow"),
]
for mod, name in packages:
    try:
        __import__(mod)
        print(f"    ✓ {name}")
    except ImportError as e:
        errors.append(name)
        print(f"    ✗ {name} — {e}")
if errors:
    print(f"\n  WARN: {len(errors)} package(s) failed to import: {', '.join(errors)}")
    sys.exit(1)
'

python -c "$VERIFY_SCRIPT" && ok "All key packages verified" || warn "Some packages could not be imported (see above)"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║   Setup complete!                                    ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo "    1. Activate the environment:"
echo "         conda activate ${ENV_NAME}"
echo ""
echo "    2. Start all services:"
echo "         make run"
echo ""
echo "    3. Open the UI:"
echo "         http://localhost:8501"
echo ""
echo "    4. API docs:"
echo "         http://localhost:8000/docs"
echo ""
