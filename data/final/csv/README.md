# Per-node daily forcing + streamflow CSVs

Daily time series for individual **Pywr-DRB node basins**. Each file combines
three things for one node and one simulation:

1. **Meteorological forcing** — basin-area-weighted averages from the Kao et al.
   (2024) *CMIP6-based Multi-Model Hydroclimate Projection over the CONUS, v1.1*
   (HydroSource **SWA9505V3**, DOI 10.13139/OLCF/2311812).
2. **Land-surface runoff** (where available) — VIC and PRMS runoff depth,
   basin-averaged, from the same SWA9505V3 dataset.
3. **Routed streamflow** (where available) — RAPID-routed daily flow at the node,
   from the sibling **SWA9505V3Flow** product (DOI 10.13139/OLCF/2318650), which
   routes the *same* VIC/PRMS runoff through the river network.

## File naming

```
{node}__{simulation}.csv
```

- **`node`** — Pywr-DRB node basin. Currently only `cannonsville`.
  (`eastbranch-below-pepacton` will be added once that node is defined.)
- **`simulation`** — a historical reference run (`DaymetV4`, `Livneh`) or a
  `{GCM}_{SSP}_{ensemble}_{downscaling}_{reference-obs}` projection
  (e.g. `ACCESS-CM2_ssp245_r1i1p1f1_DBCCA_Daymet`).

## Columns

Every column name carries its unit as a suffix. The `date` index is a calendar
day (`YYYY-MM-DD`).

| Column | Units | Source | Description |
|--------|-------|--------|-------------|
| `date` | — | — | Daily date (index) |
| `prcp_mm_day` | mm/day | SWA9505V3 | Precipitation |
| `tmax_degC` | °C | SWA9505V3 | Daily maximum temperature |
| `tmin_degC` | °C | SWA9505V3 | Daily minimum temperature |
| `wind_m_s` | m/s | SWA9505V3 | Wind speed (no direction in source) |
| `srad_W_m2` | W/m² | VIC-MetClim | Shortwave radiation |
| `lrad_W_m2` | W/m² | VIC-MetClim | Longwave radiation |
| `qair_kg_kg` | kg/kg | VIC-MetClim | Specific humidity |
| `rhum_pct` | % | VIC-MetClim | Relative humidity |
| `runoff_vic_mm_day` | mm/day | VIC | Basin runoff depth (VIC) |
| `runoff_prms_mm_day` | mm/day | PRMS | Basin runoff depth (PRMS) |
| `streamflow_vic_mgd` | mgd | VIC→RAPID | Routed streamflow at node (VIC runoff routed) |
| `streamflow_prms_mgd` | mgd | PRMS→RAPID | Routed streamflow at node (PRMS runoff routed) |

### ⚠️ Runoff (mm/day) vs streamflow (mgd) — different quantities
- **`runoff_*_mm_day`** is basin runoff *depth generated over the node's
  catchment* — local water production, not accounting for the river network.
- **`streamflow_*_mgd`** is volumetric flow *at the node*, after RAPID routes the
  runoff downstream (travel time, accumulation from upstream, confluence). For a
  reservoir node this is the **inflow**.
- They come from the same VIC/PRMS land-surface runoff but are not
  interconvertible without the routing model. `vic`/`prms` columns let you compare
  the two hydrologic models.

## Time coverage and gaps

| Run type | Forcing | Routed streamflow available |
|----------|---------|-----------------------------|
| `DaymetV4` | 1980–2022 | **1980–2019** (NaN 2020–2022) |
| `Livneh` | 1950–2018 | **1950–2013** (NaN 2014–2018) |
| Future projections | 2015–2099 | **2020–2099** (NaN 2015–2019) |

Streamflow (and the VIC-derived runoff/radiation/humidity columns) cover a
shorter span than the raw meteorology, so cells outside their coverage are left
**empty (NaN)** — no values are interpolated or invented. Columns that have no
matching source for a given simulation are omitted entirely.

## Model configurations

The full source dataset spans:

| Component | Values |
|-----------|--------|
| GCMs | ACCESS-CM2, BCC-CSM2-MR, CNRM-ESM2-1, EC-Earth3, MPI-ESM1-2-HR, MRI-ESM2-0, NorESM2-MM |
| SSP scenarios | ssp126, ssp245, ssp370, ssp585 |
| Downscaling × reference obs | DBCCA-Daymet, DBCCA-Livneh, RegCM-Daymet, RegCM-Livneh |
| Ensemble | `r1i1p1f1` (all GCMs except CNRM-ESM2-1, which uses `r1i1p1f2`) |

> **Note on streamflow overlap:** routed streamflow exists for **ssp126/245/370**
> (not ssp585), while this repository's forcing currently emphasizes ssp585 and
> the two historical runs. A streamflow column therefore appears only where both
> products cover the same scenario — at present: the two historical runs and the
> ACCESS-CM2 ssp245/ssp370 projections.

## ⚠️ Currently uploaded (subset)

| File | Forcing | Runoff | Routed streamflow |
|------|---------|--------|-------------------|
| `cannonsville__DaymetV4.csv` | ✅ | ✅ | ✅ (to 2019) |
| `cannonsville__Livneh.csv` | ✅ | ✅ | ✅ (to 2013) |
| `cannonsville__ACCESS-CM2_ssp245_..._DBCCA_Daymet.csv` | ✅ | — | ✅ (2020–2099) |
| `cannonsville__ACCESS-CM2_ssp370_..._DBCCA_Daymet.csv` | ✅ | — | ✅ (2020–2099) |

Additional GCM × scenario combinations will be added over time.

## How these files are produced (reproducible)

```bash
python scripts/05_export_node_csv.py     # forcing columns from data/final/parquet
python scripts/06_join_streamflow.py     # + runoff + routed streamflow columns
python scripts/diagnostics/03_validate_streamflow_join.py   # annual water-balance check
```

All behavior is driven by `config.yaml` (`streamflow:` block) — the single source
of truth — so re-running regenerates identical output.

## Source & citation

Kao, S.-C., M. Ashfaq, D. Rastogi, S. Gangrade, et al. (2022), *The Third
Assessment of the Effects of Climate Change on Federal Hydropower*,
ORNL/TM-2021/2278, Oak Ridge National Laboratory.
https://doi.org/10.2172/1887712

Routed streamflow: SWA9505V3Flow, https://doi.org/10.13139/OLCF/2318650
(prepared in the sibling `CMIP6_multimodel_streamflow` project).
