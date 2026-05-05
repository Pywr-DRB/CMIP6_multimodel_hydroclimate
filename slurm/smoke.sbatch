#!/bin/bash
#SBATCH --job-name=cmip6_drb_smoke
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:30:00
#SBATCH --output=logs/smoke_%j.out
#SBATCH --error=logs/smoke_%j.err

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-/home/fs02/pmr82_0001/tja73/Research/DRB/Pywr-DRB/CMIP6_multimodel_hydroclimate}"

source /etc/profile.d/lmod.sh
module load python/3.11.5

source venv/bin/activate

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

python scripts/02_smoke_test.py --config config.yaml
