#!/usr/bin/env bash
# Slurm submission script for the Banking TASCI CUDA training workflow.
#
# Usage examples:
#   sbatch cluster/run_banking_tasci_cuda.sh
#   MODEL=bilstm TASK=intent CONFIG=configs/baselines/bilstm_intent.yaml \
#       sbatch cluster/run_banking_tasci_cuda.sh
#   MODEL=bert TASK=aspect CONFIG=configs/baselines/bert_aspect.yaml \
#       sbatch cluster/run_banking_tasci_cuda.sh
#
# Notes:
# - This script expects the repo to live at $HOME/banking-tasci on the cluster.
# - The cluster provides CUDA under /usr/local/cuda-12.9 and /usr/local/cuda-13.3.
# - The project readiness gate is enforced before training starts.

set -euo pipefail

#SBATCH --job-name=banking_tasci_cuda
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
#SBATCH --output=outputs/logs/slurm_%j.out
#SBATCH --error=outputs/logs/slurm_%j.err

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/banking-tasci}"
MODEL="${MODEL:-svm}"
TASK="${TASK:-intent}"
CONFIG="${CONFIG:-configs/baselines/svm_intent.yaml}"
CUDA_VERSION="${CUDA_VERSION:-12.9}"

if [ -d "/usr/local/cuda-${CUDA_VERSION}" ]; then
    export CUDA_HOME="/usr/local/cuda-${CUDA_VERSION}"
    export PATH="${CUDA_HOME}/bin:${PATH}"
    export LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"
fi

mkdir -p "${PROJECT_ROOT}/outputs/logs"
cd "${PROJECT_ROOT}"

if [ ! -d .venv ]; then
    echo "error: expected virtual environment at ${PROJECT_ROOT}/.venv" >&2
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python --version
nvidia-smi || true

python scripts/check_training_readiness.py \
    --annotations data/annotations/pilot_adjudicated.jsonl \
    --split-dir data/processed

python scripts/train_baselines.py \
    --model "${MODEL}" \
    --task "${TASK}" \
    --config "${CONFIG}"
