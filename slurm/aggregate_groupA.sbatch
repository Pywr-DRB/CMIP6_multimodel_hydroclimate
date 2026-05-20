#!/bin/bash
#SBATCH --job-name=cmip6_drb_aggA
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --time=06:00:00
#SBATCH --output=logs/aggregate_groupA_%j.out
#SBATCH --error=logs/aggregate_groupA_%j.err
# Group A: aggregate keep_raw vars (prcp/tmax/tmin/wind) for the 5 GCMs whose
# ssp245/ssp370 parquet outputs are missing. Raw NCs already staged in
# data/staging/raw_nc/permanent/ — no HTTPS calls happen here, so this is
# CPU-bound and should finish in ~2-3 h.

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-/home/fs02/pmr82_0001/tja73/Research/DRB/Pywr-DRB/CMIP6_multimodel_hydroclimate}"

source /etc/profile.d/lmod.sh
module load python/3.11.5
source venv/bin/activate

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

# No network contention this run — bump workers up from the 8 used during the
# ORNL-throttled aggregate_229370 run.
export CMIP6_DRB_WORKERS=16

python scripts/04_aggregate_mpi.py --config config.yaml \
  --simulations \
    CNRM-ESM2-1_ssp245_r1i1p1f2_DBCCA_Daymet \
    CNRM-ESM2-1_ssp370_r1i1p1f2_DBCCA_Daymet \
    EC-Earth3_ssp245_r1i1p1f1_DBCCA_Daymet \
    EC-Earth3_ssp370_r1i1p1f1_DBCCA_Daymet \
    MPI-ESM1-2-HR_ssp245_r1i1p1f1_DBCCA_Daymet \
    MPI-ESM1-2-HR_ssp370_r1i1p1f1_DBCCA_Daymet \
    MRI-ESM2-0_ssp245_r1i1p1f1_DBCCA_Daymet \
    MRI-ESM2-0_ssp370_r1i1p1f1_DBCCA_Daymet \
    NorESM2-MM_ssp245_r1i1p1f1_DBCCA_Daymet \
    NorESM2-MM_ssp370_r1i1p1f1_DBCCA_Daymet \
  --variables prcp tmax tmin wind \
  "$@"
