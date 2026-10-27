#!/usr/bin/env bash
# =============================================================================
# PBS/Torque job template for banking-tasci baseline and proposed-model training.
#
# USAGE
#   Copy this file, fill in every <PLACEHOLDER>, then submit:
#       qsub cluster/pbs_train.sh
#
# All lines marked PLACEHOLDER must be changed before submission.
# Do not submit this file unmodified.
#
# CLUSTER LOGIN (for reference; do not store passwords here)
#   ssh rmavhengani@146.141.21.100
# =============================================================================

# ── Job metadata ─────────────────────────────────────────────────────────────
#PBS -N <PLACEHOLDER_JOB_NAME>                  # e.g. tasci_bilstm_intent
#PBS -o outputs/logs/pbs_${PBS_JOBID}.out
#PBS -e outputs/logs/pbs_${PBS_JOBID}.err
#PBS -j oe                                       # merge stdout and stderr

# ── Queue ────────────────────────────────────────────────────────────────────
# Ask your cluster administrator for the correct queue name.
#PBS -q <PLACEHOLDER_QUEUE>                      # e.g. gpu, batch, normal

# ── Resources ────────────────────────────────────────────────────────────────
# PBS resource syntax varies by site.  Replace the examples below.
#PBS -l nodes=1:ppn=<PLACEHOLDER_CPU_COUNT>      # e.g. nodes=1:ppn=4
#PBS -l mem=<PLACEHOLDER_MEMORY>                 # e.g. mem=16gb

# ── GPU (remove or set to 0 for CPU-only jobs) ───────────────────────────────
# Some PBS sites use a select statement with ngpus; adjust to your site.
# #PBS -l select=1:ncpus=<PLACEHOLDER_CPU_COUNT>:mem=<PLACEHOLDER_MEMORY>:ngpus=<PLACEHOLDER_GPU_COUNT>

# ── Wall time ────────────────────────────────────────────────────────────────
#PBS -l walltime=<PLACEHOLDER_WALL_TIME>         # e.g. 12:00:00

# ── Project account (if required by your site) ───────────────────────────────
# #PBS -A <PLACEHOLDER_PROJECT_ACCOUNT>

# ── Notification (optional) ──────────────────────────────────────────────────
# #PBS -m abe
# #PBS -M <PLACEHOLDER_EMAIL>

# =============================================================================
# Environment setup
# =============================================================================

# Load required modules if your cluster uses Environment Modules.
# Remove or replace with the actual module names.
# module load <PLACEHOLDER_PYTHON_MODULE>        # e.g. python/3.10
# module load <PLACEHOLDER_CUDA_MODULE>          # e.g. cuda/11.8  (GPU only)

# Activate the virtual environment.
VENV_PATH=<PLACEHOLDER_VENV_PATH>               # e.g. ~/banking-tasci/.venv
source "${VENV_PATH}/bin/activate"

# Move to the project root.
PROJECT_ROOT=<PLACEHOLDER_PROJECT_ROOT>         # e.g. ~/banking-tasci
cd "${PROJECT_ROOT}"

# =============================================================================
# Training command
# =============================================================================
# Replace --model, --task, and --config with the desired values.

MODEL=<PLACEHOLDER_MODEL>        # svm | bilstm | bert
TASK=<PLACEHOLDER_TASK>          # intent | sentiment | aspect
CONFIG=<PLACEHOLDER_CONFIG>      # e.g. configs/baselines/bilstm_intent.yaml

python scripts/train_baselines.py \
    --model "${MODEL}" \
    --task  "${TASK}"  \
    --config "${CONFIG}"

# =============================================================================
# Resume from checkpoint (optional — remove if not resuming)
# =============================================================================
# Add --resume and --resume-mode to the command above if resuming a run.
