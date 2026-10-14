#!/bin/bash
#SBATCH --job-name=omnisql-step6-arctic
#SBATCH --container-image=/path/to/master.sqsh  # adjust for your Slurm environment
#SBATCH --container-name=omnisql-step6-arctic
#SBATCH --container-mounts=/path/to/project:/public  # adjust for your Slurm environment
#SBATCH --container-remap-root
#SBATCH --container-writable
#SBATCH --nodelist=workg01
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --output=omnisql-step6-arctic-%j.out

set -euo pipefail

echo "Start runv4.sh"
echo "Host working directory:"
pwd

cd "${PROJECT_ROOT:-/public}"
chmod +x run-in-dockerv4.sh
./run-in-dockerv4.sh "$@"

