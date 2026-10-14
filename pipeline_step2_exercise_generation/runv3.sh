#!/bin/bash
#SBATCH --job-name=omnisql-step4-qgen
#SBATCH --container-image=/path/to/master.sqsh  # adjust for your Slurm environment
#SBATCH --container-name=omnisql-step4-qgen
#SBATCH --container-mounts=/path/to/project:/public  # adjust for your Slurm environment
#SBATCH --container-remap-root
#SBATCH --container-writable
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --output=omnisql-step4-qgen-%j.out

set -euo pipefail

echo "Start runv3.sh"
echo "Host working directory:"
pwd

cd "${PROJECT_ROOT:-/public}"
chmod +x run-in-dockerv3.sh
./run-in-dockerv3.sh "$@"