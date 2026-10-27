#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

mkdir -p data/annotations outputs/logs

if ! command -v streamlit >/dev/null 2>&1; then
  echo "streamlit is not installed. Install it first:"
  echo "  python -m pip install streamlit"
  exit 1
fi

UNANNOTATED="data/annotations/pilot_unannotated.jsonl"
if [ ! -f "${UNANNOTATED}" ]; then
  echo "Pilot annotations file not found: ${UNANNOTATED}"
  echo "Generate it first with:"
  echo "  python scripts/create_annotation_sample.py --input data/interim/prepared.csv --output ${UNANNOTATED} --size 600 --seed 42"
  exit 1
fi

LOG_DIR="outputs/logs/annotation"
mkdir -p "${LOG_DIR}"

PORT_A=8501
PORT_B=8502

# Streamlit's one-time onboarding prompt reads stdin for an email address;
# feed it a blank line so a backgrounded/non-interactive launch never blocks.
if lsof -iTCP:${PORT_A} -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT_A} is already in use; skipping annotator A startup."
else
  nohup bash -c 'echo | streamlit run scripts/annotation_app.py -- \
    --input "'"${UNANNOTATED}"'" \
    --output "data/annotations/pilot_annotator_a.jsonl" \
    --annotator-id annotator_a \
    --server.port "'"${PORT_A}"'" \
    --server.headless true' > "${LOG_DIR}/annotator_a.log" 2>&1 &
  echo "Started annotator A at http://localhost:${PORT_A}"
fi

if lsof -iTCP:${PORT_B} -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT_B} is already in use; skipping annotator B startup."
else
  nohup bash -c 'echo | streamlit run scripts/annotation_app.py -- \
    --input "'"${UNANNOTATED}"'" \
    --output "data/annotations/pilot_annotator_b.jsonl" \
    --annotator-id annotator_b \
    --server.port "'"${PORT_B}"'" \
    --server.headless true' > "${LOG_DIR}/annotator_b.log" 2>&1 &
  echo "Started annotator B at http://localhost:${PORT_B}"
fi

echo ""
echo "Session logs:"
echo "  ${LOG_DIR}/annotator_a.log"
echo "  ${LOG_DIR}/annotator_b.log"
echo ""
echo "To stop the sessions later:"
echo "  pkill -f 'streamlit run scripts/annotation_app.py'"
