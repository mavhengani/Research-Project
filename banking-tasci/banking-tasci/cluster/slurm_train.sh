#!/usr/bin/env bash
# =============================================================================
# Slurm job template for banking-tasci baseline and proposed-model training.
#
# USAGE
#   Copy this file, fill in every <PLACEHOLDER>, then submit:
#       sbatch cluster/slurm_train.sh
#
# All lines marked PLACEHOLDER must be changed before submission.
# Do not submit this file unmodified.
#
# CLUSTER LOGIN (for reference; do not store passwords here)
#   ssh rmavhengani@146.141.21.100
# =============================================================================

# ── Job metadata ─────────────────────────────────────────────────────────────
#SBATCH --job-name=<PLACEHOLDER_JOB_NAME>       # e.g. tasci_svm_intent
#SBATCH --output=outputs/logs/slurm_%j.out
#SBATCH --error=outputs/logs/slurm_%j.err

# ── Partition / queue ─────────────────────────────────────────────────────────
# Ask your cluster administrator for the correct partition name.
#SBATCH --partition=<PLACEHOLDER_PARTITION>     # e.g. gpu, batch, compute

# ── Resources ────────────────────────────────────────────────────────────────
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=<PLACEHOLDER_CPU_COUNT> # e.g. 4
#SBATCH --mem=<PLACEHOLDER_MEMORY>              # e.g. 16G

# ── GPU (remove or set to 0 for CPU-only jobs) ───────────────────────────────
#SBATCH --gres=gpu:<PLACEHOLDER_GPU_COUNT>      # e.g. gpu:1
# Uncomment and set GPU type if your cluster requires it:
# #SBATCH --constraint=<PLACEHOLDER_GPU_TYPE>  # e.g. v100, a100

# ── Wall time ────────────────────────────────────────────────────────────────
#SBATCH --time=<PLACEHOLDER_WALL_TIME>          # e.g. 12:00:00

# ── Notification (optional) ──────────────────────────────────────────────────
# #SBATCH --mail-type=END,FAIL
# #SBATCH --mail-user=<PLACEHOLDER_EMAIL>

# =============================================================================
# Environment setup
# =============================================================================

# Load required modules if your cluster uses Environment Modules.
# Remove or replace with the actual module names.
# module load <PLACEHOLDER_PYTHON_MODULE>       # e.g. python/3.10
# module load <PLACEHOLDER_CUDA_MODULE>         # e.g. cuda/11.8  (GPU only)

# Activate the virtual environment.
VENV_PATH=<PLACEHOLDER_VENV_PATH>              # e.g. ~/banking-tasci/.venv
source "${VENV_PATH}/bin/activate"

# Move to the project root.
PROJECT_ROOT=<PLACEHOLDER_PROJECT_ROOT>        # e.g. ~/banking-tasci
cd "${PROJECT_ROOT}"

# =============================================================================
# Training command
# =============================================================================
# Replace --model, --task, and --config with the desired values.
# The readiness gate runs automatically before any model is built.
# Training will abort with a clear message if gold annotations or split
# manifests are absent.

MODEL=<PLACEHOLDER_MODEL>       # svm | bilstm | bert
TASK=<PLACEHOLDER_TASK>         # intent | sentiment | aspect
CONFIG=<PLACEHOLDER_CONFIG>     # e.g. configs/baselines/svm_intent.yaml

python scripts/train_baselines.py \
    --model "${MODEL}" \
    --task  "${TASK}"  \
    --config "${CONFIG}"

# =============================================================================
# Resume from checkpoint (optional — remove if not resuming)
# =============================================================================
# To resume a full interrupted run, add:
#   --resume outputs/runs/<run-id>/best_checkpoint.pt
#   --resume-mode full_resume
#
# To warm-start weights only:
#   --resume outputs/runs/<run-id>/best_checkpoint.pt
#   --resume-mode warm_start
