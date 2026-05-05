"""Per-task worker for parallel aggregation.

`process_task(task_dict)` takes a serializable dict (no live config, no live
xarray Dataset) and runs:
    fetch raw -> open + clip -> sparse matmul -> atomic parquet write
    -> optionally delete raw (stream-and-discard for non-keep_raw vars).

Used by `scripts/04_aggregate_mpi.py` via `multiprocessing.Pool`. Tasks are
independent — no inter-process communication beyond the pool's task/result
channels. The driver holds the task queue + state log; workers return small
status dicts.

(Module name is a holdover from an mpi4py prototype; we use multiprocessing
on this cluster because mpi4py 4.x + OpenMPI 4.0.5 hits MPI_ERR_INTERN in
MPIPoolExecutor.Comm.Create.)
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkerArgs:
    """All inputs a worker needs to do one (sim, var, year) task without re-reading config."""
    sim: str
    var: str
    year: int
    raw_dest_str: str            # absolute path to expected raw NetCDF location
    keep_raw: bool               # if False, delete raw after aggregation succeeds
    intermediate_str: str        # absolute path to per-year parquet output
    weights_dir_str: str         # directory holding drb_node_weights.npz + grid
    bbox: dict                   # {"lon_min": ..., "lon_max": ..., "lat_min": ..., "lat_max": ...}
    https_url: str               # source URL for on-demand HTTPS fetch
    https_retries: int
    https_backoff: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def process_task(args_dict: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point — invoked by multiprocessing.Pool on each child.

    Returns a small status dict for the driver to log.
    """
    import os

    args = WorkerArgs(**args_dict)
    raw = Path(args.raw_dest_str)
    inter = Path(args.intermediate_str)
    if inter.exists():
        return {"sim": args.sim, "var": args.var, "year": args.year, "status": "skipped_existing", "info": str(inter)}

    # Fetch raw if needed.
    if not raw.exists():
        from cmip6_drb import http_client
        raw.parent.mkdir(parents=True, exist_ok=True)
        try:
            http_client.download(args.https_url, raw, retries=args.https_retries, backoff=args.https_backoff)
        except http_client.PermanentHttpError as e:
            # 404 etc. -- file isn't published. Skip without polluting failure metrics.
            return {"sim": args.sim, "var": args.var, "year": args.year, "status": "missing_in_source", "info": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"sim": args.sim, "var": args.var, "year": args.year, "status": "fetch_failed", "info": str(e)}

    # Aggregate.
    from cmip6_drb import aggregate, io as drb_io, weights as weights_mod
    bbox = aggregate.Bbox(**args.bbox)
    try:
        w = weights_mod.load_weights(args.weights_dir_str)
        df = aggregate.aggregate_file(raw, args.var, bbox, w)
        drb_io.write_parquet_atomic(df, inter)
    except Exception as e:  # noqa: BLE001
        return {"sim": args.sim, "var": args.var, "year": args.year, "status": "aggregate_failed", "info": str(e)}

    # Stream-and-discard policy.
    if not args.keep_raw:
        try:
            os.remove(raw)
        except FileNotFoundError:
            pass

    return {"sim": args.sim, "var": args.var, "year": args.year, "status": "ok", "info": str(inter)}


def build_worker_args(cfg, task, weights_dir: Path) -> dict[str, Any]:
    from .manifest import http_url

    keep_raw = task.variable in set(cfg["retention"]["keep_raw"])
    raw_dest = cfg.paths.raw_dest(task.simulation, task.variable, task.filename(), permanent=keep_raw)
    inter = cfg.paths.intermediate(task.simulation, task.variable, task.year)
    return WorkerArgs(
        sim=task.simulation,
        var=task.variable,
        year=int(task.year),
        raw_dest_str=str(raw_dest),
        keep_raw=keep_raw,
        intermediate_str=str(inter),
        weights_dir_str=str(weights_dir),
        bbox={
            "lon_min": cfg["drb_bbox"]["lon_min"],
            "lon_max": cfg["drb_bbox"]["lon_max"],
            "lat_min": cfg["drb_bbox"]["lat_min"],
            "lat_max": cfg["drb_bbox"]["lat_max"],
        },
        https_url=http_url(cfg, task),
        https_retries=int(cfg["https"]["retries"]),
        https_backoff=float(cfg["https"]["backoff_seconds"]),
    ).to_dict()
