#!/bin/bash
set -euo pipefail

MODEL_NAME="${1:-qwen3_0}"
LIMIT="${2:-}"

PROJECT_ROOT="${PROJECT_ROOT:-/public}"
CODE_DIR="${PROJECT_ROOT}/code"
INPUT_JSON="${INPUT_JSON:-${CODE_DIR}/omnisql_step3_qwen_2_5_sft.json}"
OUTPUT_JSON="${OUTPUT_JSON:-${CODE_DIR}/omnisql_step4_qwen3_0.json}"
SCRIPT_PATH="${SCRIPT_PATH:-${CODE_DIR}/omnisql_step4_generate_question_candidates.py}"
MODELFILE_PATH="${MODELFILE_PATH:-${PROJECT_ROOT}/ollama/Modelfile_Qwen3_0}"

export PATH="${PROJECT_ROOT}/ollama/ollama-local/bin:${PATH}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-${PROJECT_ROOT}/ollama/models}"
export HOME="${HOME:-${PROJECT_ROOT}/home}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${PROJECT_ROOT}/.cache}"
mkdir -p "${HOME}" "${XDG_CACHE_HOME}" "${OLLAMA_MODELS}"

if [[ -n "${LIMIT}" ]]; then
  OUTPUT_JSON="${OUTPUT_JSON%.json}_test${LIMIT}.json"
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama not found in PATH"
  exit 1
fi

ollama serve >/tmp/ollama-step4.log 2>&1 &
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
  --temperature 0.3
  --top-p 0.9
  --num-predict 700
  --num-candidates 5
  --min-candidates 3
  --max-retries 3
  --timeout 300
  --resume
)

if [[ -n "${LIMIT}" ]]; then
  ARGS+=(--limit "${LIMIT}")
fi

"${ARGS[@]}"