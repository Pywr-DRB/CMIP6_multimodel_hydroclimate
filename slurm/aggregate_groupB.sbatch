#!/bin/bash
#SBATCH --job-name=cmip6_drb_aggB
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --time=12:00:00
#SBATCH --output=logs/aggregate_groupB_%x_%j.out
#SBATCH --error=logs/aggregate_groupB_%x_%j.err
# Group B: aggregate srad/lrad/qair/rhum for one GCM (both ssp245 and ssp370).
# These vars are NOT pre-staged — each worker does an HTTPS fetch from ORNL
# hydrosource2 inside process_task(). Run one GCM per job so an ORNL hiccup
# only loses 680 tasks instead of all 4080.
#
# Usage:
#   sbatch -J cmip6B_<GCM> slurm/aggregate_groupB.sbatch <GCM>
# Examples:
#   sbatch -J cmip6B_BCC      slurm/aggregate_groupB.sbatch BCC-CSM2-MR
#   sbatch -J cmip6B_CNRM     slurm/aggregate_groupB.sbatch CNRM-ESM2-1
#   sbatch -J cmip6B_ECEarth  slurm/aggregate_groupB.sbatch EC-Earth3
#   sbatch -J cmip6B_MPI      slurm/aggregate_groupB.sbatch MPI-ESM1-2-HR
#   sbatch -J cmip6B_MRI      slurm/aggregate_groupB.sbatch MRI-ESM2-0
#   sbatch -J cmip6B_NorESM   slurm/aggregate_groupB.sbatch NorESM2-MM

set -euo pipefail

GCM="${1:-}"
if [[ -z "$GCM" ]]; then
  echo "ERROR: GCM name is required as first positional arg." >&2
  exit 2
fi
shift  # drop GCM from "$@" before forwarding the rest to python

# Per-GCM ensemble ID — must match config.yaml dataset.ensembles.
case "$GCM" in
  CNRM-ESM2-1) ENS=r1i1p1f2 ;;
  ACCESS-CM2|BCC-CSM2-MR|EC-Earth3|MPI-ESM1-2-HR|MRI-ESM2-0|NorESM2-MM) ENS=r1i1p1f1 ;;
  *) echo "ERROR: unknown GCM '$GCM'" >&2; exit 2 ;;
esac

cd "${SLURM_SUBMIT_DIR:-/home/fs02/pmr82_0001/tja73/Research/DRB/Pywr-DRB/CMIP6_multimodel_hydroclimate}"

source /etc/profile.d/lmod.sh
module load python/3.11.5
source venv/bin/activate

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

# Stay at 8 workers — ORNL hydrosource2 cuts mid-transfer under heavier load
# (see config.yaml mp.workers note). Polite concurrency wins here.
export CMIP6_DRB_WORKERS=8

python scripts/04_aggregate_mpi.py --config config.yaml \
  --simulations \
    "${GCM}_ssp245_${ENS}_DBCCA_Daymet" \
    "${GCM}_ssp370_${ENS}_DBCCA_Daymet" \
  --variables srad lrad qair rhum \
  "$@"
