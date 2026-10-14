#!/bin/bash

echo "Start run-in-dockerv2.sh"
echo "Working directory:"
pwd
echo "Contents:"
ls

echo "Add local Ollama to PATH"
PROJECT_ROOT="${PROJECT_ROOT:-/public}"
export PATH="${PROJECT_ROOT}/ollama/ollama-local/bin:$PATH"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
export OLLAMA_SCHED_SPREAD="${OLLAMA_SCHED_SPREAD:-true}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"

echo "Runtime GPU config:"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}"
echo "OLLAMA_SCHED_SPREAD=${OLLAMA_SCHED_SPREAD}"
echo "OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
echo "OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"

echo "Ollama binary:"
which ollama || echo "ollama not in PATH"

echo "Ollama version:"
ollama --version

echo "Start Ollama server"
ollama serve &

echo "Wait for Ollama"
sleep 20

MODEL_NAME="Qwen2.5-Text2SQL-R1"
MODELFILE_PATH="${MODELFILE_PATH:-${PROJECT_ROOT}/ollama/Modelfile_Qwen2_5}"
if [ ! -f "$MODELFILE_PATH" ]; then
  MODELFILE_PATH="${PROJECT_ROOT}/code/Modelfile_Qwen2_5"
fi
if [ ! -f "$MODELFILE_PATH" ]; then
  MODELFILE_PATH="./Modelfile_Qwen2_5"
fi

echo "Create model ${MODEL_NAME} from ${MODELFILE_PATH}"
ollama create "${MODEL_NAME}" -f "${MODELFILE_PATH}"

echo "Available models:"
ollama list

echo "Install sqlglot"
pip install -q sqlglot

SCRIPT_PATH="code/model2.py"
if [ ! -f "$SCRIPT_PATH" ]; then
  SCRIPT_PATH="./model2.py"
fi

MAX_ROWS="${1:-${MAX_ROWS:-}}"
if [ -n "$MAX_ROWS" ]; then
  echo "Run ${SCRIPT_PATH} in test mode with --max-rows ${MAX_ROWS}"
  python3 "$SCRIPT_PATH" --max-rows "$MAX_ROWS"
else
  echo "Run ${SCRIPT_PATH} once for the full dataset"
  python3 "$SCRIPT_PATH"
fi
