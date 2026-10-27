#!/usr/bin/env bash
# =============================================================================
# Interactive cluster setup script for banking-tasci.
#
# Run this ONCE on the cluster after transferring the repository.
# It creates a virtual environment and installs all dependencies.
#
# If the cluster blocks internet access, build a wheelhouse on another
# Linux machine first (see the "Offline install" section below).
#
# CLUSTER LOGIN (for reference; do not store passwords here)
#   ssh rmavhengani@146.141.21.100
#
# USAGE
#   chmod +x cluster/interactive_setup.sh
#   ./cluster/interactive_setup.sh
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration — fill in before running
# =============================================================================

PROJECT_ROOT=<PLACEHOLDER_PROJECT_ROOT>        # e.g. ~/banking-tasci
PYTHON_BIN=<PLACEHOLDER_PYTHON_BIN>            # e.g. python3 or python3.10
VENV_DIR="${PROJECT_ROOT}/.venv"

# Path to a pre-built wheelhouse directory (leave empty for online install).
WHEELHOUSE=<PLACEHOLDER_WHEELHOUSE_PATH_OR_EMPTY>  # e.g. ~/wheelhouse or ""

# =============================================================================
# Load cluster modules (if required)
# =============================================================================
# Uncomment and replace with actual module names if your cluster uses
# Environment Modules.
# module load <PLACEHOLDER_PYTHON_MODULE>       # e.g. python/3.10

# =============================================================================
# Create virtual environment
# =============================================================================

cd "${PROJECT_ROOT}"
echo "[setup] Creating virtual environment at ${VENV_DIR} ..."
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

echo "[setup] Python: $(python --version)"
python -m pip install --upgrade pip --quiet

# =============================================================================
# Install dependencies
# =============================================================================

if [ -n "${WHEELHOUSE}" ] && [ -d "${WHEELHOUSE}" ]; then
    # --- Offline install from a pre-built wheelhouse --------------------------
    echo "[setup] Installing from wheelhouse: ${WHEELHOUSE}"
    pip install \
        --no-index \
        --find-links="${WHEELHOUSE}" \
        -r requirements.txt
else
    # --- Online install -------------------------------------------------------
    echo "[setup] Installing from PyPI (internet required) ..."
    pip install -r requirements.txt
fi

# =============================================================================
# Verify installation
# =============================================================================

echo "[setup] Verifying core imports ..."
python -c "import torch; print('torch:', torch.__version__)"
python -c "import pandas; print('pandas:', pandas.__version__)"
python -c "import sklearn; print('sklearn:', sklearn.__version__)"
python -c "import banking_tasci; print('banking_tasci: OK')"

echo ""
echo "[setup] Environment ready."
echo "[setup] Activate with:  source ${VENV_DIR}/bin/activate"
echo ""

# =============================================================================
# Data transfer reminder (run from LOCAL machine, not cluster)
# =============================================================================
# From your local machine:
#   scp -r banking-tasci rmavhengani@146.141.21.100:~/
#
# Transfer pretrained BERT model (if using BERT baseline):
#   scp -r /path/to/local/bert-model rmavhengani@146.141.21.100:~/bert_model/
# Then set configs/baselines/bert_*.yaml pretrained_path to ~/bert_model/

# =============================================================================
# Offline wheelhouse build (run on an internet-connected Linux machine)
# =============================================================================
# python3 -m pip download -r requirements.txt --dest ~/wheelhouse/
# scp -r ~/wheelhouse/ rmavhengani@146.141.21.100:~/wheelhouse/

# =============================================================================
# Readiness check (run after data and annotations are in place)
# =============================================================================
# python scripts/check_training_readiness.py \
#     --annotations data/annotations/pilot_adjudicated.jsonl \
#     --split-dir data/processed
