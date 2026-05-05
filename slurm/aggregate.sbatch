#!/bin/bash
#SBATCH --job-name=cmip6_drb_agg
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --time=24:00:00
#SBATCH --output=logs/aggregate_%j.out
#SBATCH --error=logs/aggregate_%j.err
# Single Python process, 16 multiprocessing workers (set in config.yaml).
# 16 concurrent HTTPS streams to ORNL hydrosource2 is polite; 24 cores
# reserved leaves headroom for I/O kernel work. Well under 5-node budget.

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-/home/fs02/pmr82_0001/tja73/Research/DRB/Pywr-DRB/CMIP6_multimodel_hydroclimate}"

source /etc/profile.d/lmod.sh
module load python/3.11.5

source venv/bin/activate

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

export CMIP6_DRB_WORKERS=8

python scripts/04_aggregate_mpi.py --config config.yaml "$@"
