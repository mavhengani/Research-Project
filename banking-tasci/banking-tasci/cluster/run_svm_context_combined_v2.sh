#!/usr/bin/env bash
# Phase 3B context-aware SVM intent baseline on combined Gold Version 2.
set -euo pipefail
#SBATCH --job-name=tasci_svm_context_v2
#SBATCH --partition=stampede
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=outputs/logs/slurm_svm_context_%j.out
#SBATCH --error=outputs/logs/slurm_svm_context_%j.err

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/banking-tasci}"
ANNOTATIONS="data/annotations/combined_adjudicated_v2.jsonl"
SPLIT_DIR="data/processed/combined_v2"

mkdir -p "${PROJECT_ROOT}/outputs/logs"
cd "${PROJECT_ROOT}"

# Batch shells need the system profile before Lmod's module function exists.
set +u
source /etc/profile
set -u
module load anaconda/anaconda-2025-12-2

echo "slurm_job_id=${SLURM_JOB_ID:-not_under_slurm}"
echo "hostname=$(hostname)"
python3 --version

python3 scripts/check_training_readiness.py \
  --annotations "${ANNOTATIONS}" \
  --split-dir "${SPLIT_DIR}"

python3 scripts/train_baselines.py \
  --model svm --task intent \
  --config configs/baselines/svm_intent_context_combined_v2.yaml \
  --annotations "${ANNOTATIONS}" \
  --split-dir "${SPLIT_DIR}"