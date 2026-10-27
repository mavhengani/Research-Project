#!/usr/bin/env bash
# Slurm submission script: Phase 3B SVM baselines (intent + sentiment) on the
# combined Gold Version 2 dataset (pilot_adjudicated.jsonl +
# south_african_adjudicated_v2.jsonl, genuinely independent SA annotation).
#
# Usage:
#   sbatch cluster/run_svm_combined_v2.sh
#
# CPU-only job: SVM baselines use scikit-learn, no GPU required.
# Uses the cluster's module-provided Anaconda environment (scikit-learn
# 1.7.2, numpy 2.3.5 confirmed present) — no local .venv needed.

set -euo pipefail

#SBATCH --job-name=tasci_svm_combined_v2
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=outputs/logs/slurm_svm_%j.out
#SBATCH --error=outputs/logs/slurm_svm_%j.err

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/banking-tasci}"
ANNOTATIONS="data/annotations/combined_adjudicated_v2.jsonl"
SPLIT_DIR="data/processed/combined_v2"

mkdir -p "${PROJECT_ROOT}/outputs/logs"
cd "${PROJECT_ROOT}"

# Batch shells need the system profile before Lmod's `module` function exists.
set +u
source /etc/profile
set -u
module load anaconda/anaconda-2025-12-2

python3 --version

python3 scripts/check_training_readiness.py \
    --annotations "${ANNOTATIONS}" \
    --split-dir "${SPLIT_DIR}"

python3 scripts/train_baselines.py \
    --model svm --task intent \
    --config configs/baselines/svm_intent_combined_v2.yaml \
    --annotations "${ANNOTATIONS}" \
    --split-dir "${SPLIT_DIR}"

python3 scripts/train_baselines.py \
    --model svm --task sentiment \
    --config configs/baselines/svm_sentiment_combined_v2.yaml \
    --annotations "${ANNOTATIONS}" \
    --split-dir "${SPLIT_DIR}"
