#!/bin/bash
#SBATCH --job-name=paul-v2
#SBATCH --container-image=/path/to/master.sqsh  # adjust for your Slurm environment
#SBATCH --container-name=seven-v2
#SBATCH --container-mounts=/path/to/project:/public  # adjust for your Slurm environment
#SBATCH --container-remap-root
#SBATCH --container-writable
#SBATCH --nodelist=workg02
#SBATCH --gres=gpu:2
#SBATCH --mem=256G

echo "hello from run_v2.sh"
ls
cd ..
ls
cd public
ls
chmod +x run-in-docker_v2.sh
./run-in-docker_v2.sh "$1"
