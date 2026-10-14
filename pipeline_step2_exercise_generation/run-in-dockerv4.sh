#!/bin/bash
set -euo pipefail

MODEL_NAME="${1:-arcticsql}"
LIMIT="${2:-}"

PROJECT_ROOT="${PROJECT_ROOT:-/public}"
CODE_DIR="${PROJECT_ROOT}/code"
INPUT_JSON="${CODE_DIR}/omnisql_step5_qwen3_0_selected_questions.json"
OUTPUT_JSON="${CODE_DIR}/omnisql_step6_arcticsql_roundtrip_sql.json"
SCRIPT_PATH="${CODE_DIR}/omnisql_step6_generate_roundtrip_sql.py"
MODELFILE_PATH="${MODELFILE_PATH:-${PROJECT_ROOT}/ollama/Modelfile_ArcticSQL}"

export PATH="${PROJECT_ROOT}/ollama/ollama-local/bin:${PATH}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-${PROJECT_ROOT}/ollama/models}"

if [[ -n "${LIMIT}" ]]; then
  OUTPUT_JSON="${CODE_DIR}/omnisql_step6_arcticsql_test${LIMIT}.json"
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama not found in PATH"
  exit 1
fi

ollama serve >/tmp/ollama-step6.log 2>&1 &
OLLAMA_PID=$!
trap 'kill ${OLLAMA_PID} >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 60); do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! ollama list | awk '{print $1}' | grep -qx "${MODEL_NAME}"; then
  if [[ ! -f "${MODELFILE_PATH}" ]]; then
    echo "Model ${MODEL_NAME} not found and Modelfile missing: ${MODELFILE_PATH}"
    echo "Set MODELFILE_PATH=${PROJECT_ROOT}/ollama/<your_modelfile> or pass an existing Ollama model name."
    exit 1
  fi
  ollama create "${MODEL_NAME}" -f "${MODELFILE_PATH}"
fi

python -m pip install -q requests

ARGS=(
  python "${SCRIPT_PATH}"
  --input "${INPUT_JSON}"
  --output "${OUTPUT_JSON}"
  --model "${MODEL_NAME}"
  --temperature 0.0
  --num-predict 700
  --timeout 300
  --resume
)

if [[ -n "${LIMIT}" ]]; then
  ARGS+=(--limit "${LIMIT}")
fi

"${ARGS[@]}"
