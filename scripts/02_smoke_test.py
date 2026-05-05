"""Phase 1 smoke test: download ONE file end-to-end and produce a parquet.

Default scope: DaymetV4 / prcp / 1980. Configurable via config.yaml.

Path priority:
  1. Globus, if `globus.enable: true` AND collection UUIDs are configured.
  2. HTTPS direct from hydrosource2.ornl.gov (fallback / current default).

After download, the script:
  - opens the NetCDF, clips to DRB bbox,
  - computes polygon-grid weights in-memory against the smoke shapefile,
  - applies them, writes final/parquet/{sim}__{var}.parquet,
  - prints summary stats (annual mean prcp at cannonsville).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

# Add src/ to sys.path so this script runs without `pip install -e .`.
THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import aggregate, config as cfg_mod, http_client, io as drb_io, manifest, weights as weights_mod  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("smoke")


def _fetch_via_globus(cfg, task: manifest.Task, dest: Path) -> bool:
    """Try Globus. Return True on success, False to indicate fallback should run."""
    g = cfg["globus"]
    if not g.get("enable"):
        log.info("Globus disabled in config; using HTTPS fallback.")
        return False
    if not g.get("destination_endpoint_uuid") or not g.get("client_id"):
        log.warning("Globus config incomplete (destination UUID / client ID missing); falling back to HTTPS.")
        return False
    try:
        from cmip6_drb.globus_client import GlobusConfig, GlobusTransferClient  # lazy import
    except Exception as e:  # noqa: BLE001
        log.warning("globus-sdk import failed (%s); falling back to HTTPS.", e)
        return False

    gc = GlobusConfig(
        client_id=g["client_id"],
        source_endpoint_uuid=g["source_endpoint_uuid"],
        destination_endpoint_uuid=g["destination_endpoint_uuid"],
        refresh_token_path=Path(g["refresh_token_path"]).expanduser(),
    )
    try:
        client = GlobusTransferClient(gc)
    except FileNotFoundError as e:
        log.warning("Globus refresh token not found (%s); falling back to HTTPS.", e)
        return False

    src = manifest.globus_source_path(cfg, task)
    dst = str(dest.resolve())
    label = f"smoke {task.simulation}/{task.variable}/{task.year}"
    log.info("Submitting Globus transfer: %s -> %s", src, dst)
    task_id = client.submit_batch([(src, dst)], label=label)
    log.info("Task submitted: %s; polling...", task_id)
    status = client.wait(task_id, poll_seconds=15.0, timeout_seconds=3600.0)
    log.info("Globus task finished: status=%s", status.get("status"))
    return status.get("status") == "SUCCEEDED"


def _fetch_via_https(cfg, task: manifest.Task, dest: Path) -> Path:
    url = manifest.http_url(cfg, task)
    return http_client.download(
        url,
        dest,
        retries=int(cfg["https"]["retries"]),
        backoff=float(cfg["https"]["backoff_seconds"]),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()), help="Path to config.yaml")
    ap.add_argument("--simulation", help="Override smoke_test.simulation")
    ap.add_argument("--variable", help="Override smoke_test.variable")
    ap.add_argument("--year", type=int, help="Override smoke_test.year")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    cfg.paths.ensure()

    s = cfg["smoke_test"]
    sim = args.simulation or s["simulation"]
    var = args.variable or s["variable"]
    yr = int(args.year or s["year"])
    task = manifest.Task(simulation=sim, variable=var, year=yr)
    log.info("Smoke task: %s", task)

    raw_dest = cfg.paths.raw_dest(sim, var, task.filename(), permanent=False)

    if not _fetch_via_globus(cfg, task, raw_dest):
        log.info("HTTPS fetch from %s", manifest.http_url(cfg, task))
        _fetch_via_https(cfg, task, raw_dest)

    if not raw_dest.exists():
        log.error("Raw file missing after fetch: %s", raw_dest)
        return 1

    bbox = aggregate.Bbox.from_config(cfg)
    log.info("Opening NetCDF: %s", raw_dest)
    da = aggregate.open_clipped(raw_dest, var, bbox)
    log.info("Clipped DataArray shape: %s; dims=%s", da.shape, da.dims)

    grid = weights_mod.GridSpec.from_dataarray(da, crs=cfg["target_crs"])

    # Force shapefile CRS to target CRS (its .prj is bogus -> claims ISN93 but coords are EPSG:4326).
    import geopandas as gpd
    gdf = gpd.read_file(cfg["paths"]["shapefile"])
    if gdf.crs is None or "ISN" in str(gdf.crs):
        log.warning("Overriding shapefile CRS from %s to %s (the .prj is bogus).", gdf.crs, cfg["target_crs"])
        gdf = gdf.set_crs(cfg["target_crs"], allow_override=True)
    forced_path = cfg.paths.final_weights / "node_basin_geometries_wgs84.gpkg"
    forced_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(forced_path, driver="GPKG")

    log.info("Computing weights against %d polygons × %s grid", len(gdf), grid.shape)
    w = weights_mod.compute_weights(forced_path, grid)
    stats = weights_mod.verify_weights(w)
    log.info("Weights OK: %s", stats)

    df = aggregate.aggregate_to_nodes(da, w)
    log.info("Aggregated DataFrame: %d rows × %d cols", *df.shape)

    out = cfg.paths.final(sim, var)
    drb_io.write_parquet_atomic(df, out)
    log.info("Wrote %s (%.1f KB)", out, out.stat().st_size / 1024)

    if "cannonsville" in df.columns:
        annual_mean = float(np.nanmean(df["cannonsville"].values))
        log.info("Annual mean prcp at cannonsville (%d, %s): %.3f mm/day", yr, sim, annual_mean)
    else:
        log.warning("'cannonsville' column missing; available: %s", list(df.columns)[:5])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
