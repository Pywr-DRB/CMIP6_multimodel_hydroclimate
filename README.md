# CMIP6_multimodel_hydroclimate

Download and post-process the **Kao et al. 2024 CMIP6-based Multi-Model
Hydroclimate Projection over the CONUS, v1.1** (HydroSource SWA9505V3,
DOI [10.13139/OLCF/2311812](https://doi.org/10.13139/OLCF/2311812)) into
per-catchment daily time series for the **33 Pywr-DRB node basins**.

End uses:

1. Forcing for water-temperature simulation in the upper DRB / NYC reservoirs
   (`cannonsville`, `pepacton`, `neversink`).
2. Forcing grids for a collaborator's hydrologic model (`prcp`, `tmax`,
   `tmin`, `wind` retained as raw NetCDF).

Reference dataset: Kao, S.-C., Ashfaq, M., Rastogi, D., & Gangrade, S. (2024).
*CMIP6-based multi-model hydroclimate projection over the conterminous US,
Version 1.1.* HydroSource. Oak Ridge National Laboratory.

---

## Dataset coverage

| Component | Values | Count |
|---|---|---|
| GCMs | ACCESS-CM2, BCC-CSM2-MR, CNRM-ESM2-1, EC-Earth3, MPI-ESM1-2-HR, MRI-ESM2-0, NorESM2-MM | 7 |
| SSP scenarios | ssp126, ssp245, ssp370, ssp585 | 4 |
| Downscaling × reference observations | DBCCA-Daymet, DBCCA-Livneh, RegCM-Daymet, RegCM-Livneh | 4 |
| Historical reference runs | DaymetV4 (1980–2022), Livneh (1950–2018) | 2 |
| Variables per run | `prcp`, `tmax`, `tmin`, `wind`, plus 21 derived (VIC + VIC-MetClim + PRMS) | 25 |
| Future period | 2015–2099 | 85 yrs |

The full Cartesian (7 × 4 × 4 = 112) is **not** populated. Each GCM ships
DBCCA-Daymet for all 4 SSPs, and DBCCA-Livneh / RegCM-Daymet / RegCM-Livneh
for ssp585 only — **7 future runs per GCM × 7 GCMs = 49 future + 2 historical
≈ 51 simulation runs**, ~110,000 (sim × variable × year) NetCDF files total.
CNRM-ESM2-1 uses ensemble `r1i1p1f2`; others use `r1i1p1f1`. See
[Kao et al. 2022](https://doi.org/10.2172/1887712) for methodology and
provenance.

---

## Quickstart

The pipeline runs in five phases. The first three are tested and work; phases
3–4 are wired but designed to run inside SLURM at scale.

### 0. One-time setup (login node)

```bash
module load python/3.11.5
python -m venv venv  # if not already present
source venv/bin/activate
pip install -r requirements.txt
```

The repo's `venv/` is Python 3.11.5. The aggregator uses
`multiprocessing.Pool` (single-node, N workers); no MPI runtime needed.

> *Note:* an earlier prototype tried `mpi4py.futures.MPIPoolExecutor`, but
> mpi4py 4.x against this cluster's OpenMPI 4.0.5 raises
> `MPI_ERR_INTERN` in `Comm.Create`. Multiprocessing is what works here.

Edit [config.yaml](config.yaml) if you want to scope to a subset of GCMs / SSPs
/ variables. By default everything is enumerated.

### 1. Smoke test (one file end-to-end, ~30 s)

```bash
source /etc/profile.d/lmod.sh && module load python/3.11.5
source venv/bin/activate
python scripts/02_smoke_test.py --config config.yaml
# Or: sbatch slurm/smoke.sbatch
```

Downloads `DaymetV4_VIC4_prcp_1980.nc` (~148 MB) via HTTPS, clips to the DRB
bbox, computes weights against `node_basin_geometries.shp` in-memory, and
produces `data/final/parquet/DaymetV4__prcp.parquet` (366 rows × 33 cols).
Prints the 1980 mean prcp at `cannonsville` for sanity.

### 2. Persist weights (~1 s)

```bash
python scripts/01_compute_weights.py --config config.yaml
```

Writes `data/final/weights/drb_node_weights.{npz,parquet}` (~16 KB total). The
MPI aggregator memory-maps these on every rank.

### 3. Bulk-download keep-raw variables

`prcp`, `tmax`, `tmin`, `wind` are retained as raw NetCDF for the
collaborator's hydrologic model. Everything else is stream-and-discard inside
Phase 4.

```bash
sbatch slurm/download.sbatch                              # all keep_raw vars, all sims
sbatch slurm/download.sbatch --simulations DaymetV4 --max-files 5    # smaller test
```

Threaded HTTPS against `hydrosource2.ornl.gov` (the public mirror of the OLCF
DOI archive) — concurrency capped by `https.concurrency` in
[config.yaml](config.yaml). Proven at ~30 MB/s in the smoke test; the full
~7.5 TB `keep_raw` budget completes in roughly 70 hours of unattended SLURM
wall time.

### 4. Parallel aggregation (one node, 8 workers)

```bash
sbatch slurm/aggregate.sbatch
# Or scope: sbatch slurm/aggregate.sbatch --simulations DaymetV4 Livneh
```

Loads `python/3.11.5`, dispatches every `(simulation, variable, year)` task
via `multiprocessing.Pool` (8 workers, polite concurrency for ORNL HTTPS),
streams raw NetCDF when needed, and writes per-year intermediates which are
concatenated into final parquets:

```
data/final/parquet/{simulation}__{variable}.parquet
```

Each ≈7 MB, float32, daily DatetimeIndex × 33 node-name columns.

### 5. Reduce only (after a partial run)

```bash
python scripts/04_aggregate_mpi.py --reduce-only
```

---

## Output schema

| File | Index | Columns | Units |
|---|---|---|---|
| `data/final/parquet/{sim}__{var}.parquet` | `date` (DatetimeIndex, daily) | 33 Pywr-DRB node names | per-variable, see below |

Variables and units (from the source dataset README):

| Variable | Units | Source |
|---|---|---|
| `prcp` | mm/day | Daymet/Livneh, then GCM-downscaled |
| `tmax`, `tmin` | °C | Daymet/Livneh, then GCM-downscaled |
| `wind` | m/s | Daymet/Livneh, then GCM-downscaled |
| `srad`, `lrad` | W/m² | VIC-MetClim |
| `qair` | kg/kg | VIC-MetClim |
| `rhum` | % | VIC-MetClim |
| `vp`, `vpd`, `pres` | Pa | VIC-MetClim |
| `runoff`, `runoffs`, `runoffb` | mm/day | VIC |
| `swe`, `soilm` | mm | VIC |
| `evap`, `pet` | mm/day | VIC |
| `PRMS_*` | as above | PRMS |

Float32 throughout, zstd-compressed parquet.

Node names cover the 33 Pywr-DRB inflow points; upper-DRB / NYC reservoirs
are `cannonsville`, `pepacton`, `neversink` (plus the `link_*` reaches that
appear immediately downstream of each).

## Notes on data layout discovered during build

- File pattern (verified): `{simulation}/{variable}/{simulation}_VIC4_{variable}_{year}.nc`
  for the climate + VIC-derived variables, and
  `{simulation}/{variable}/{simulation}_{variable}_{year}.nc` for `PRMS_*`.
- DaymetV4 covers 1980–2022; Livneh covers 1950–2018; future scenarios cover 2015–2099.
- CNRM-ESM2-1 uses ensemble `r1i1p1f2` (all other GCMs use `r1i1p1f1`).
- The `node_basin_geometries.shp` `.prj` is incorrectly stamped as
  `GCS_ISN93_3D`; coordinates are actually WGS84 / EPSG:4326. The pipeline
  overrides this at load time.

## Layout

```
src/cmip6_drb/        # importable Python package
  paths.py            # resolve staging/intermediate/final dirs
  config.py           # YAML loader
  manifest.py         # enumerate (sim, var, year) tasks + URLs
  http_client.py      # resumable HTTPS download with retries
  weights.py          # exactextract polygon-grid weights
  aggregate.py        # clip-to-bbox + sparse matmul
  io.py               # atomic parquet writer with float32 enforcement
  mpi_runner.py       # per-task worker function
  state.py            # JSONL idempotent task tracker
scripts/
  01_compute_weights.py     # persist polygon-grid weights
  02_smoke_test.py          # Phase 1 end-to-end test
  03_download_bulk.py       # Phase 3 batched fetch (keep_raw vars)
  04_aggregate_mpi.py       # Phase 4 parallel driver + reduce
  05_make_figures.py        # reproducible figures from final/parquet
slurm/
  smoke.sbatch
  download.sbatch
  aggregate.sbatch
tests/                # pytest suite (synthetic correctness)
config.yaml           # single source of truth
```

## Reference

Kao, S.-C., M. Ashfaq, D. Rastogi, S. Gangrade, R. Uría Martínez, A. Fernandez,
G. Konapala, N. Voisin, T. Zhou, W. Xu, H. Gao, B. Zhao, and G. Zhao (2022),
*The Third Assessment of the Effects of Climate Change on Federal Hydropower*,
ORNL/TM-2021/2278, Oak Ridge National Laboratory, Oak Ridge, TN.
[https://doi.org/10.2172/1887712](https://doi.org/10.2172/1887712)
