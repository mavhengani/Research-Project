#!/usr/bin/env bash
# Phase 3B BiLSTM intent baseline on combined Gold Version 2.
set -euo pipefail
#SBATCH --job-name=tasci_bilstm_intent_v2
#SBATCH --partition=biggpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=outputs/logs/slurm_bilstm_intent_%j.out
#SBATCH --error=outputs/logs/slurm_bilstm_intent_%j.err

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/banking-tasci}"
ANNOTATIONS="data/annotations/combined_adjudicated_v2.jsonl"
SPLIT_DIR="data/processed/combined_v2"

mkdir -p "${PROJECT_ROOT}/outputs/logs"
cd "${PROJECT_ROOT}"
source .venv/bin/activate

echo "slurm_job_id=${SLURM_JOB_ID:-not_under_slurm}"
echo "hostname=$(hostname)"
python --version
python -c "import torch; print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available())"

python scripts/check_training_readiness.py \
  --annotations "${ANNOTATIONS}" \
  --split-dir "${SPLIT_DIR}"

python scripts/train_baselines.py \
  --model bilstm --task intent \
  --config configs/baselines/bilstm_intent_combined_v2.yaml \
  --annotations "${ANNOTATIONS}" \
  --split-dir "${SPLIT_DIR}"