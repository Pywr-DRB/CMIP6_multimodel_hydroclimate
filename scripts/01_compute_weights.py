"""Phase 2: compute polygon-grid weights ONCE and persist them.

Given any source NetCDF (default: the smoke-test file produced by Phase 1),
this script:
  1. Opens it, clips to the DRB bbox (matches what aggregate.open_clipped does),
  2. Builds a GridSpec from the clipped lat/lon coords,
  3. Reprojects node_basin_geometries.shp to EPSG:4326 (its .prj is incorrectly
     stamped as ISN93; coords are actually WGS84),
  4. Computes fractional-area weights via exactextract,
  5. Verifies row-sums and saves to data/final/weights/.

The resulting weights file is reused by the MPI aggregator for every (sim, var, year)
task — every Kao et al. NetCDF shares the same lat/lon coordinates after bbox clip,
so one weights file works for everything.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import aggregate, config as cfg_mod, manifest, weights as weights_mod  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("compute_weights")


def _reproject_shapefile(src_path: str, target_crs: str, out_path: Path) -> Path:
    import geopandas as gpd

    gdf = gpd.read_file(src_path)
    if gdf.crs is None or "ISN" in str(gdf.crs):
        log.warning("Overriding shapefile CRS from %s to %s (the .prj is bogus).", gdf.crs, target_crs)
        gdf = gdf.set_crs(target_crs, allow_override=True)
    else:
        gdf = gdf.to_crs(target_crs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GPKG")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--sample-nc", help="Path to any source NetCDF; defaults to the Phase 1 smoke file.")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    cfg.paths.ensure()

    if args.sample_nc:
        sample = Path(args.sample_nc)
    else:
        s = cfg["smoke_test"]
        task = manifest.Task(simulation=s["simulation"], variable=s["variable"], year=int(s["year"]))
        sample = cfg.paths.raw_dest(task.simulation, task.variable, task.filename(), permanent=False)

    if not sample.exists():
        log.error("Sample NetCDF not found at %s. Run scripts/02_smoke_test.py first.", sample)
        return 1

    bbox = aggregate.Bbox.from_config(cfg)
    da = aggregate.open_clipped(sample, cfg["smoke_test"]["variable"], bbox)
    grid = weights_mod.GridSpec.from_dataarray(da, crs=cfg["target_crs"])
    log.info("Grid: lat=%s lon=%s", grid.shape, da.dims)

    forced = cfg.paths.final_weights / "node_basin_geometries_wgs84.gpkg"
    _reproject_shapefile(cfg["paths"]["shapefile"], cfg["target_crs"], forced)

    w = weights_mod.compute_weights(forced, grid)
    stats = weights_mod.verify_weights(w)
    log.info("Verified weights: %s", stats)

    out = weights_mod.save_weights(w, cfg.paths.final_weights)
    for k, v in out.items():
        log.info("  %s: %s (%.1f KB)", k, v, v.stat().st_size / 1024)

    # Round-trip sanity.
    w2 = weights_mod.load_weights(cfg.paths.final_weights)
    assert w2.matrix.nnz == w.matrix.nnz, "Round-trip nnz mismatch"
    assert w2.node_ids[0] == w.node_ids[0], "Round-trip node order mismatch"
    log.info("Round-trip OK.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
