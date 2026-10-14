#!/bin/bash
#SBATCH --job-name=axolotl-dpo
#SBATCH --partition=debug
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-gpu=16
#SBATCH --mem-per-cpu=4G
#SBATCH --time=24:00:00
#SBATCH --output=%x-%j.out

#SBATCH --container-image=/path/to/axolotl.sqsh
#SBATCH --container-name=axolotl_train
#SBATCH --container-mounts=/path/to/project:/project
#SBATCH --container-remap-root
#SBATCH --container-writable

set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/project}"
AXOLOTL_DIR="${AXOLOTL_DIR:-$PROJECT_ROOT/pipeline_step1_sql_generation_repair}"
CONFIG_PATH="${CONFIG_PATH:-$AXOLOTL_DIR/config_dpo.yaml}"

cd "$AXOLOTL_DIR"
nvidia-smi
python -c "from axolotl.cli.main import main; print('axolotl import OK')"

axolotl train "$CONFIG_PATH"