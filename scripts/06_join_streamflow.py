"""Augment per-node forcing CSVs with routed streamflow (and local runoff) columns.

For each ``{node}__{sim}.csv`` written by scripts/05_export_node_csv.py, this:

  1. Adds local VIC/PRMS runoff (mm/day) columns where the parquet exists
     (`data/final/parquet/{sim}__runoff.parquet`, `__PRMS_runoff.parquet`).
  2. Adds RAPID-routed streamflow (mgd) columns pulled from the sibling
     streamflow repo, one per configured LSM, resolved by name (see
     `src/cmip6_drb/streamflow.py`).

Streamflow and forcing have different date coverage (e.g. projections start 2020
in the streamflow repo vs 2015 here), so the join is an outer join on date and
out-of-coverage cells are left as NaN — no data is invented.

The set of routed LSM variants (VIC5, PRMS) lives in config.yaml
(`streamflow.lsms`) — the single source of truth — not behind a CLI flag, so a
given config always produces the same output.

    python scripts/06_join_streamflow.py [--config config.yaml]
                                         [--node cannonsville]
                                         [--csv-dir data/final/csv]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import config as cfg_mod, io as drb_io, streamflow as sf_mod  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("join_streamflow")


def discover_sims(csv_dir: Path, node: str) -> dict[str, Path]:
    """Map sim name -> csv path for files matching `{node}__{sim}.csv`."""
    out: dict[str, Path] = {}
    for p in sorted(csv_dir.glob(f"{node}__*.csv")):
        sim = p.name[len(node) + 2 : -len(".csv")]  # strip "{node}__" and ".csv"
        out[sim] = p
    return out


def runoff_columns(sim: str, node: str, parquet_dir: Path) -> dict[str, pd.Series]:
    """Local VIC/PRMS runoff series (mm/day) for a node, where parquet exists."""
    cols: dict[str, pd.Series] = {}
    for var, colname in sf_mod.RUNOFF_UNIT_NAMES.items():
        p = parquet_dir / f"{sim}__{var}.parquet"
        if not p.exists():
            continue
        try:
            df = drb_io.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("%s: skip %s: %s", sim, p.name, e)
            continue
        if node not in df.columns:
            log.warning("%s: node %r absent in %s; skipping", sim, node, p.name)
            continue
        s = df[node].copy()
        s.index = pd.DatetimeIndex(s.index).normalize()  # daily date key for alignment
        s.name = colname
        cols[colname] = s
    return cols


def join_one(sim: str, csv_path: Path, node: str, lsms: list[str],
             parquet_dir: Path, cfg: cfg_mod.Config) -> tuple[int, list[str]]:
    """Join runoff + streamflow columns onto one CSV in place. Returns (#added, names)."""
    base = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    base.index = pd.DatetimeIndex(base.index).normalize()  # daily date key for alignment
    base.index.name = "date"
    # Make idempotent + self-sufficient: ensure forcing names are unit-suffixed.
    base = base.rename(columns=sf_mod.FORCING_UNIT_NAMES)

    new: dict[str, pd.Series] = {}
    new.update(runoff_columns(sim, node, parquet_dir))
    for lsm in lsms:
        s = sf_mod.load_node_streamflow(sim, node, lsm, cfg)
        if s is None:
            log.info("%s [%s]: no matching streamflow dataset; skipping", sim, lsm)
            continue
        new[s.name] = s

    if not new:
        log.warning("%s: nothing to add (no runoff parquet, no streamflow match)", sim)
        return 0, []

    # Drop any prior versions of these columns so re-runs don't duplicate.
    base = base.drop(columns=[c for c in new if c in base.columns])
    added = pd.DataFrame(new)
    result = base.join(added, how="outer").sort_index()
    result.index.name = "date"
    result.to_csv(csv_path, index=True)
    return len(new), list(new)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--node", default="cannonsville", help="node column to join")
    ap.add_argument("--csv-dir", default=None, help="dir of {node}__{sim}.csv (default: <final_parquet>/../csv)")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    parquet_dir = cfg.paths.final_parquet
    csv_dir = Path(args.csv_dir).resolve() if args.csv_dir else (parquet_dir.parent / "csv")
    lsms = cfg.get("streamflow", {}).get("lsms", ["VIC5", "PRMS"])

    sims = discover_sims(csv_dir, args.node)
    if not sims:
        log.warning("no %s__*.csv files found in %s", args.node, csv_dir)
        return 0

    log.info("joining streamflow onto %d CSVs in %s (node=%r, lsms=%s)",
             len(sims), csv_dir, args.node, ",".join(lsms))
    total = 0
    for sim, path in sims.items():
        n, names = join_one(sim, path, args.node, lsms, parquet_dir, cfg)
        if n:
            log.info("%s: +%d cols (%s)", sim, n, ",".join(names))
            total += 1
    log.info("done: updated %d / %d CSVs", total, len(sims))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
