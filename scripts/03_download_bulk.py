"""Phase 3: bulk-download raw NetCDF for variables in retention.keep_raw.

This script focuses on raw retention for the collaborator's hydrologic model:
prcp, tmax, tmin, wind. Other variables are NOT pre-staged — the MPI aggregator
fetches them on demand inside each worker task.

Behavior:
  - Submits transfers via Globus if globus.enable=true AND auth is configured.
  - Otherwise falls back to threaded HTTPS GET (concurrency-capped).
  - Idempotent: skips files that already exist on disk; resumes via .part files
    and the JSONL state log.
  - Aborts if staging exceeds retention.staging_raw_cap_gb (a safety net for
    misconfigured runs against /home).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import config as cfg_mod, http_client, manifest  # noqa: E402
from cmip6_drb.state import StateLog  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("bulk_download")


def _dir_size_gb(path: Path) -> float:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total / (1024 ** 3)


def _https_one(cfg, task: manifest.Task, dest: Path) -> tuple[manifest.Task, bool, str]:
    url = manifest.http_url(cfg, task)
    try:
        http_client.download(
            url,
            dest,
            retries=int(cfg["https"]["retries"]),
            backoff=float(cfg["https"]["backoff_seconds"]),
        )
        return task, True, ""
    except Exception as e:  # noqa: BLE001
        return task, False, str(e)


def _build_task_list(cfg, simulations: list[str] | None, variables: list[str] | None) -> list[manifest.Task]:
    sims = simulations if simulations is not None else manifest.all_simulations(cfg)
    vars_ = variables if variables is not None else list(cfg["retention"]["keep_raw"])
    tasks = list(manifest.iter_tasks(cfg, simulations=sims, variables_filter=vars_))
    return tasks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--simulations", nargs="*", help="Subset of simulation names")
    ap.add_argument("--variables", nargs="*", help="Subset of variable names (default: retention.keep_raw)")
    ap.add_argument("--max-files", type=int, default=None, help="Cap total files for testing")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    cfg.paths.ensure()

    tasks = _build_task_list(cfg, args.simulations, args.variables)
    if args.max_files is not None:
        tasks = tasks[: args.max_files]

    state = StateLog(cfg.paths.state_file)
    done = state.completed("downloaded")

    work: list[tuple[manifest.Task, Path]] = []
    for t in tasks:
        if (t.simulation, t.variable, t.year) in done:
            continue
        dest = cfg.paths.raw_dest(t.simulation, t.variable, t.filename(), permanent=True)
        if dest.exists():
            state.record(sim=t.simulation, var=t.variable, year=t.year, stage="downloaded", info="preexisting")
            continue
        work.append((t, dest))

    log.info("Total tasks: %d, already done: %d, to fetch: %d", len(tasks), len(done), len(work))
    if args.dry_run:
        for t, d in work[:10]:
            log.info("DRY-RUN: %s -> %s", manifest.http_url(cfg, t), d)
        return 0

    if cfg["globus"].get("enable"):
        log.warning("Globus path not yet wired in bulk driver; using HTTPS. Confirm UUIDs and re-enable later.")

    cap_gb = float(cfg["retention"]["staging_raw_cap_gb"])
    permanent_root = cfg.paths.staging_raw / "permanent"

    concurrency = int(cfg["https"]["concurrency"])
    completed = 0
    failed: list[tuple[manifest.Task, str]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_https_one, cfg, t, d): (t, d) for t, d in work}
        for fut in as_completed(futures):
            task, ok, err = fut.result()
            t, d = futures[fut]
            if ok:
                state.record(sim=task.simulation, var=task.variable, year=task.year, stage="downloaded", info=str(d))
                completed += 1
            else:
                state.record(sim=task.simulation, var=task.variable, year=task.year, stage="failed", info=err)
                failed.append((task, err))
            if completed and completed % 25 == 0:
                used = _dir_size_gb(permanent_root)
                log.info("Progress: %d/%d done, staging %.1f GB", completed, len(work), used)
                if used > cap_gb:
                    log.error("Staging exceeded cap %.1f GB > %.1f GB; aborting.", used, cap_gb)
                    return 2

    log.info("Bulk download finished: %d ok, %d failed.", completed, len(failed))
    for t, e in failed[:20]:
        log.error("  FAILED %s: %s", t, e)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
