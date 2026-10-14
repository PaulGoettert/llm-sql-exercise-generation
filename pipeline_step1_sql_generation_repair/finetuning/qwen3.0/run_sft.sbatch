#!/bin/bash
#SBATCH --job-name=axolotl-sft
#SBATCH --partition=debug
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-gpu=16
#SBATCH --mem-per-cpu=4G
#SBATCH --time=24:00:00
#SBATCH --output=%x-%j.out

#SBATCH --container-image=/path/to/axolotl_fa2.sqsh
#SBATCH --container-mounts=/path/to/project:/project
#SBATCH --container-remap-root

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/project}"
AXOLOTL_DIR="${AXOLOTL_DIR:-$PROJECT_ROOT/pipeline_step1_sql_generation_repair}"
CONFIG_PATH="${CONFIG_PATH:-$AXOLOTL_DIR/finetuning/qwen3.0/config_sft_qwen2.5.yaml}"

nvidia-smi
python -c "from axolotl.cli.main import main; print('axolotl import OK')"

export HOME="${HOME:-/project}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export HF_DATASETS_CACHE="$HF_HOME/datasets"
export TRANSFORMERS_CACHE="$HF_HOME/hub"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
mkdir -p "$HF_DATASETS_CACHE" "$TRANSFORMERS_CACHE" "$TORCH_HOME"

TORCH_LIB=$(python - <<'PY'
import torch, os
print(os.path.join(os.path.dirname(torch.__file__), "lib"))
PY
)
export LD_LIBRARY_PATH="$TORCH_LIB:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"

python -c "import flash_attn_2_cuda; print('flash_attn OK')"

cd "$AXOLOTL_DIR"
export AXOLOTL_DO_NOT_TRACK=1
export MASTER_ADDR="$(hostname -f 2>/dev/null || hostname)"
export MASTER_PORT=$((29500 + SLURM_JOB_ID % 1000))
export TOKENIZERS_PARALLELISM=false

axolotl train "$CONFIG_PATH" \
  --launcher torchrun -- \
  --nnodes=1 \
  --node_rank=0 \
  --nproc_per_node=${SLURM_GPUS_ON_NODE:-2} \
  --master_addr="${MASTER_ADDR}" \
  --master_port="${MASTER_PORT}"