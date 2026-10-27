# Cluster Guide — Banking TASCI (Phase 3A)

This guide covers transferring the project to the compute cluster, setting up an
**offline** environment, transferring a **local** BERT model, detecting the
scheduler, submitting CPU/GPU jobs, resuming from checkpoints, and retrieving
results.

> **Credentials are never stored in this repository.** The login node is
> reached interactively with:
>
> ```bash
> ssh rmavhengani@146.141.21.100
> ```
>
> Use your own SSH key / password interactively. Do **not** commit passwords,
> private keys, or tokens. The reproducibility writer
> (`training/reproducibility.py`) records only benign version/metadata strings.

> **Placeholders.** This guide does **not** assume a scheduler, partition,
> queue, GPU type, module name, or shared filesystem path. Replace every
> `<PLACEHOLDER>` with the values your cluster documentation specifies.

Common placeholders:

| Placeholder | Meaning |
| --- | --- |
| `<REMOTE_USER>` | your cluster username (e.g. `rmavhengani`) |
| `<LOGIN_HOST>` | login node host (e.g. `146.141.21.100`) |
| `<REMOTE_PROJECT_DIR>` | project path on the cluster (e.g. `$HOME/banking-tasci`) |
| `<SCHEDULER>` | `slurm` or `pbs` (detect it — see below) |
| `<PARTITION_OR_QUEUE>` | Slurm partition / PBS queue name |
| `<GPU_RESOURCE>` | GPU request string (e.g. `gpu:1` / `ngpus=1`) |
| `<MODULE_NAME>` | environment module (e.g. a Python/CUDA module) |
| `<SCRATCH_DIR>` | scratch/shared filesystem path |
| `<WHEELHOUSE_DIR>` | directory of pre-downloaded wheels |
| `<LOCAL_BERT_DIR>` | local BERT model directory |

---

## 1. Transfer the project (scp)

From your **local** machine, from the repository root:

```bash
# Exclude large/regenerable artifacts; transfer source, configs, scripts, tests.
scp -r \
  Makefile pyproject.toml requirements.txt \
  configs scripts src tests docs \
  <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/
```

Or, with rsync (preferred — resumable, respects excludes):

```bash
rsync -avz --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'outputs/runs' --exclude '.git' \
  ./ <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/
```

Also transfer the **raw data** and (later) the **adjudicated gold + manifests**
when they exist:

```bash
scp -r data/raw <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/data/
# When gold data exists:
scp data/annotations/pilot_adjudicated.jsonl \
  <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/data/annotations/
scp data/processed/*_manifest.csv \
  <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/data/processed/
```

---

## 2. Environment setup (login node)

```bash
ssh <REMOTE_USER>@<LOGIN_HOST>
cd <REMOTE_PROJECT_DIR>

# Load whatever Python/CUDA the cluster provides (name is cluster-specific).
module load <MODULE_NAME>        # e.g. a Python 3.10+ module

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
```

---

## 3. Offline wheelhouse installation

Compute nodes usually have **no internet**. Pre-download wheels on a machine
with connectivity, transfer them, then install offline.

On a connected machine (matching the cluster's Python/platform where possible):

```bash
mkdir wheelhouse
python3 -m pip download -r requirements.txt -d wheelhouse
# For the BERT baseline, also download transformers (+ its deps):
python3 -m pip download transformers -d wheelhouse
```

Transfer and install on the cluster:

```bash
scp -r wheelhouse <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/
# On the cluster, inside the venv:
python3 -m pip install --no-index --find-links=<WHEELHOUSE_DIR> -r requirements.txt
python3 -m pip install --no-index --find-links=<WHEELHOUSE_DIR> transformers  # optional
```

Sanity check:

```bash
python3 -m pytest -q
```

---

## 4. Local BERT asset transfer (offline models)

The BERT baseline loads from a **local directory** with
`local_files_only=True` — it never downloads. On a connected machine:

```bash
python3 - <<'PY'
from transformers import AutoModel, AutoTokenizer
name = "bert-base-uncased"   # or your chosen checkpoint
AutoTokenizer.from_pretrained(name).save_pretrained("bert-base-uncased")
AutoModel.from_pretrained(name).save_pretrained("bert-base-uncased")
PY
```

Transfer the directory and point the config at it:

```bash
scp -r bert-base-uncased \
  <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/models/pretrained/
```

Set `bert.pretrained_path` in `configs/baselines/bert_*.yaml` to
`<LOCAL_BERT_DIR>` (e.g. `models/pretrained/bert-base-uncased`).

---

## 5. Scheduler detection

Detect which scheduler is available before writing a job script:

```bash
if command -v sbatch >/dev/null 2>&1; then
  echo "scheduler: slurm"
elif command -v qsub >/dev/null 2>&1; then
  echo "scheduler: pbs"
else
  echo "scheduler: none found — ask your cluster admin"
fi
```

List partitions/queues (names are cluster-specific):

```bash
sinfo            # Slurm partitions
qstat -Q         # PBS queues
```

---

## 6. Slurm job template

Save as `scripts/cluster/train.slurm` and edit the placeholders:

```bash
#!/bin/bash
#SBATCH --job-name=tasci-baseline
#SBATCH --partition=<PARTITION_OR_QUEUE>
#SBATCH --gres=<GPU_RESOURCE>          # e.g. gpu:1 ; omit for CPU-only
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=%x-%j.out

set -euo pipefail
module load <MODULE_NAME>
cd <REMOTE_PROJECT_DIR>
source .venv/bin/activate

python3 scripts/check_training_readiness.py \
  --annotations data/annotations/pilot_adjudicated.jsonl \
  --split-dir data/processed

python3 scripts/train_baselines.py \
  --model "${MODEL:-svm}" --task "${TASK:-intent}" \
  --config "configs/baselines/${MODEL:-svm}_${TASK:-intent}.yaml"
```

Submit:

```bash
MODEL=bilstm TASK=intent sbatch scripts/cluster/train.slurm
```

---

## 7. PBS job template

Save as `scripts/cluster/train.pbs` and edit the placeholders:

```bash
#!/bin/bash
#PBS -N tasci-baseline
#PBS -q <PARTITION_OR_QUEUE>
#PBS -l select=1:ncpus=4:mem=16gb:<GPU_RESOURCE>   # e.g. ngpus=1 ; omit for CPU
#PBS -l walltime=04:00:00
#PBS -o tasci-baseline.out
#PBS -j oe

set -euo pipefail
module load <MODULE_NAME>
cd <REMOTE_PROJECT_DIR>
source .venv/bin/activate

python3 scripts/check_training_readiness.py \
  --annotations data/annotations/pilot_adjudicated.jsonl \
  --split-dir data/processed

python3 scripts/train_baselines.py \
  --model "${MODEL:-svm}" --task "${TASK:-intent}" \
  --config "configs/baselines/${MODEL:-svm}_${TASK:-intent}.yaml"
```

Submit:

```bash
qsub -v MODEL=bert,TASK=aspect scripts/cluster/train.pbs
```

---

## 8. CPU smoke test

Before requesting a GPU, confirm the pipeline runs on CPU (interactively or in a
short CPU job). At the current stage this **correctly stops** at the readiness
gate because the pilot is unannotated:

```bash
cd <REMOTE_PROJECT_DIR>
source .venv/bin/activate

# Fast, dependency-light checks:
python3 -m pytest -q

# Readiness gate (expected to BLOCK until gold + manifests exist):
python3 scripts/check_training_readiness.py \
  --annotations data/annotations/pilot_adjudicated.jsonl \
  --split-dir data/processed

# A baseline command also stops with the blocked message until gold exists:
python3 scripts/train_baselines.py --model svm --task intent \
  --config configs/baselines/svm_intent.yaml
```

Force CPU for neural configs by setting `train.device: cpu` (the default in the
provided baseline configs).

---

## 9. GPU job submission

Once gold data and manifests exist, request a GPU and set the device. For a
Slurm example:

```bash
# In configs/baselines/bilstm_intent.yaml (or via a copy), set:
#   train:
#     device: cuda
MODEL=bilstm TASK=intent sbatch scripts/cluster/train.slurm
```

Monitor:

```bash
squeue -u <REMOTE_USER>     # Slurm
qstat -u <REMOTE_USER>      # PBS
tail -f tasci-baseline-*.out
```

---

## 10. Checkpoint resume

The shared training loop writes structured checkpoints and supports two modes
(see `docs/` and `training/loop.py`):

- **warm_start** — restore model weights only; fresh optimiser/epoch/best.
- **full_resume** — restore weights + optimiser + epoch + best score +
  early-stopping counter + RNG, continuing from `epoch + 1`.

The best checkpoint for a run is written to
`outputs/runs/<run-id>/best_checkpoint.pt`. To continue an interrupted neural
run, load that checkpoint with `resume_mode="full_resume"` (old weight-only
checkpoints load as `warm_start`; a `full_resume` from one raises a clear
compatibility error). Wire the resume path through your job script by pointing
the trainer at the prior run's checkpoint (see `training/loop.load_checkpoint`).

---

## 11. Result retrieval

Each run writes a self-contained directory under `outputs/runs/<run-id>/`
(config, environment, git commit, label maps, the three manifests, metrics,
best checkpoint, training log, predictions). Copy results back locally:

```bash
# From your local machine:
rsync -avz \
  <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/outputs/runs/ \
  ./outputs/runs/
```

Or a single run:

```bash
scp -r <REMOTE_USER>@<LOGIN_HOST>:<REMOTE_PROJECT_DIR>/outputs/runs/<RUN_ID> \
  ./outputs/runs/
```

---

## 12. Safety notes

- No credentials are stored here; authenticate interactively.
- The readiness gate blocks all supervised training until adjudicated gold and
  leakage-safe manifests exist — no baseline is trained on the unannotated pilot.
- Compute nodes run **offline**: install from the wheelhouse and load BERT from
  a **local** directory (`local_files_only=True`).

