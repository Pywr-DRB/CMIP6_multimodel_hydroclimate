"""Phase 4: parallel aggregation across all (sim, var, year) tasks.

Uses multiprocessing.Pool on a single SLURM node — N workers, each runs
fetch->open->clip->matmul->parquet for one task. Tasks are independent.

(We tried mpi4py.futures.MPIPoolExecutor first but mpi4py 4.x against
OpenMPI 4.0.5 raises MPI_ERR_INTERN in Comm.Create on this cluster.
Single-node multiprocessing avoids that and gives the same throughput
since the workload is network-bound, not compute-bound.)

After all workers finish, a serial reduce concatenates per-year
intermediate parquets into the final per-(sim, var) parquet and deletes
the intermediates.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import config as cfg_mod, io as drb_io, manifest, mpi_runner  # noqa: E402
from cmip6_drb.state import StateLog  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("agg_mpi")


def _build_tasks(cfg, sims: list[str] | None, vars_: list[str] | None) -> list[manifest.Task]:
    sims = sims if sims is not None else manifest.all_simulations(cfg)
    vars_ = vars_ if vars_ is not None else manifest.variables(cfg)
    return list(manifest.iter_tasks(cfg, simulations=sims, variables_filter=vars_))


def _reduce(cfg) -> None:
    """Concatenate per-year parquets into final per-(sim, var) outputs."""
    inter_dir = cfg.paths.staging_intermediate
    parts_by_pair: dict[tuple[str, str], list[Path]] = {}
    for p in sorted(inter_dir.glob("*.parquet")):
        try:
            sim, var, _ = p.stem.split("__")
        except ValueError:
            continue
        parts_by_pair.setdefault((sim, var), []).append(p)

    for (sim, var), parts in parts_by_pair.items():
        out = cfg.paths.final(sim, var)
        frames = [drb_io.read_parquet(p) for p in sorted(parts)]
        if out.exists():
            frames.insert(0, drb_io.read_parquet(out))
        df = pd.concat(frames, axis=0)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        drb_io.write_parquet_atomic(df, out)
        log.info("Reduced %d parts -> %s (%d rows × %d cols, %.1f KB)",
                 len(parts), out, *df.shape, out.stat().st_size / 1024)
        for p in parts:
            try:
                p.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--simulations", nargs="*")
    ap.add_argument("--variables", nargs="*")
    ap.add_argument("--reduce-only", action="store_true",
                    help="Skip worker dispatch; only run the per-(sim,var) reduce step.")
    ap.add_argument("--no-reduce", action="store_true",
                    help="Skip the reduce step; only run worker dispatch.")
    ap.add_argument("--max-tasks", type=int, default=None, help="Cap tasks for testing")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    cfg.paths.ensure()
    weights_dir = cfg.paths.final_weights
    if not (weights_dir / "drb_node_weights.npz").exists():
        log.error("Weights not found at %s. Run scripts/01_compute_weights.py first.", weights_dir)
        return 1

    if args.reduce_only:
        _reduce(cfg)
        return 0

    tasks = _build_tasks(cfg, args.simulations, args.variables)
    if args.max_tasks is not None:
        tasks = tasks[: args.max_tasks]

    state = StateLog(cfg.paths.state_file)
    done = state.completed("aggregated")
    missing = state.completed("missing")  # 404'd previously; don't re-attempt
    skipset = done | missing
    pending = [t for t in tasks if (t.simulation, t.variable, t.year) not in skipset]
    log.info("Tasks: total=%d, already done=%d, known-missing=%d, pending=%d",
             len(tasks), len(done), len(missing), len(pending))

    payloads = [mpi_runner.build_worker_args(cfg, t, weights_dir) for t in pending]

    import multiprocessing as mp
    import os
    n_workers = int(os.environ.get("CMIP6_DRB_WORKERS",
                                    cfg.get("mp", {}).get("workers", 16)))
    log.info("Using multiprocessing.Pool with %d workers", n_workers)

    chunk = int(cfg["mpi"]["task_chunk_size"])
    log_every = int(cfg["mpi"]["log_every"])
    reduce_every = int(cfg.get("mp", {}).get("reduce_every", 500))
    failures = 0
    since_reduce = 0
    # 'spawn' avoids fork+fork issues with file descriptors held by xarray/h5netcdf.
    ctx = mp.get_context("spawn")
    with ctx.Pool(n_workers) as pool:
        for start in range(0, len(payloads), chunk):
            batch = payloads[start: start + chunk]
            log.info("Dispatching batch %d-%d / %d", start, start + len(batch), len(payloads))
            for i, result in enumerate(pool.imap_unordered(mpi_runner.process_task, batch, chunksize=1), 1):
                stage = {
                    "ok": "aggregated",
                    "skipped_existing": "aggregated",
                    "missing_in_source": "missing",
                }.get(result["status"], "failed")
                state.record(sim=result["sim"], var=result["var"], year=result["year"],
                             stage=stage,
                             info=f"{result['status']}: {result['info']}")
                if stage == "failed":
                    failures += 1
                since_reduce += 1
                if i % log_every == 0:
                    log.info("  progress: %d/%d in batch (%d failures so far)",
                             i, len(batch), failures)
                # Periodic reduce so partial progress shows up in final/parquet/
                # without waiting for the entire job to finish.
                if since_reduce >= reduce_every and not args.no_reduce:
                    log.info("  triggering periodic reduce (%d new results since last)", since_reduce)
                    _reduce(cfg)
                    since_reduce = 0

    if not args.no_reduce:
        log.info("Worker phase done; running final reduce step...")
        _reduce(cfg)

    log.info("Aggregation finished: %d total failures.", failures)
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
