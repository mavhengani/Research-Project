#!/usr/bin/env bash
# Prepared Slurm wrapper. Execution remains gated by explicit authorisation.
set -euo pipefail
#SBATCH --job-name=banking_ssl_pilot
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --time=08:00:00
#SBATCH --output=outputs/logs/ssl_pilot_%j.out
#SBATCH --error=outputs/logs/ssl_pilot_%j.err
PROJECT_ROOT="${PROJECT_ROOT:-$HOME/banking-tasci}"
REPRESENTATION="${REPRESENTATION:?Set REPRESENTATION to U1 or U2}"
case "$REPRESENTATION" in
  U1) CONFIG=configs/self_supervised/u1_banking_mlm_bert.yaml ;;
  U2) CONFIG=configs/self_supervised/u2_banking_span_bert.yaml ;;
  *) echo "REPRESENTATION must be U1 or U2" >&2; exit 2 ;;
esac
cd "$PROJECT_ROOT"
source .venv-mlm/bin/activate
python scripts/train_self_supervised.py --config "$CONFIG" --mode validate-only
if [ "${EXECUTE_AUTHORIZED:-0}" != "1" ]; then
    echo "PILOT_NOT_EXECUTED: set EXECUTE_AUTHORIZED=1 only after separate approval"
    exit 3
fi
python scripts/train_self_supervised.py --config "$CONFIG" --mode pilot --execute-authorized
