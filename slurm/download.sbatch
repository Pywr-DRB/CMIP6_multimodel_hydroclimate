#!/bin/bash
#SBATCH --job-name=cmip6_drb_dl
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=48:00:00
#SBATCH --output=logs/download_%j.out
#SBATCH --error=logs/download_%j.err

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-/home/fs02/pmr82_0001/tja73/Research/DRB/Pywr-DRB/CMIP6_multimodel_hydroclimate}"

source /etc/profile.d/lmod.sh
module load python/3.11.5
source venv/bin/activate

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

# Optional CLI overrides via SBATCH_EXPORT, e.g. --simulations DaymetV4 --variables prcp tmax
python scripts/03_download_bulk.py --config config.yaml "$@"
