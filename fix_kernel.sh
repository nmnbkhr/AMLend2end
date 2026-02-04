#!/bin/bash
# Fix Jupyter Kernel Connection Issues
# Run this script when kernel keeps "connecting" or "restarting"
# Usage: ./fix_kernel.sh

echo "========================================"
echo "  Jupyter Kernel Fix Script"
echo "========================================"

# 1. Kill all Jupyter kernel processes
echo ""
echo "[1/4] Killing Jupyter kernels..."
pkill -9 -f ipykernel_launcher 2>/dev/null
pkill -9 -f jupyter 2>/dev/null
sleep 1

# 2. Kill Spark/Java processes (from PySpark notebooks)
echo "[2/4] Killing Spark/Java processes..."
pkill -9 -f "spark" 2>/dev/null
pkill -9 -f "java.*spark" 2>/dev/null
pkill -9 -f "pyspark" 2>/dev/null
sleep 1

# 3. Clear Jupyter runtime files
echo "[3/4] Clearing Jupyter runtime files..."
rm -rf /run/user/$(id -u)/jupyter/runtime/* 2>/dev/null
rm -rf ~/.local/share/jupyter/runtime/* 2>/dev/null
rm -rf /tmp/jupyter-* 2>/dev/null
rm -rf /tmp/spark-* 2>/dev/null

# 4. Reinstall kernel (optional but helps)
echo "[4/4] Reinstalling amlgan kernel..."
source /opt/miniconda/bin/activate amlgan 2>/dev/null && \
python -m ipykernel install --user --name amlgan --display-name "amlgan" 2>/dev/null

echo ""
echo "========================================"
echo "  Done! Now in VS Code:"
echo "  1. Press Ctrl+Shift+P"
echo "  2. Type: Developer: Reload Window"
echo "  3. Press Enter"
echo "  4. Open your notebook and select kernel"
echo "========================================"
