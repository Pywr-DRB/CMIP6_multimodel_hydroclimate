"""Export a single node's forcing variables to one CSV per simulation.

Pulls the chosen node's column (default: cannonsville) out of each
`{sim}__{var}.parquet` in data/final/parquet/, joins the forcing variables
on the daily date index, and writes one wide CSV per simulation:

    data/final/csv/{node}__{sim}.csv

    columns: date, prcp, tmax, tmin, wind, srad, lrad, qair, rhum

Defensive, like scripts/diagnostics/01_make_figures.py: a simulation missing
some forcing variables still gets a CSV (those columns are written as empty/NaN
with a warning); a simulation missing the node column entirely is skipped.

    python scripts/05_export_node_csv.py [--config config.yaml]
                                         [--node cannonsville]
                                         [--out data/final/csv]
                                         [--variables prcp tmax tmin ...]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import config as cfg_mod, io as drb_io, streamflow as sf_mod  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("export_node_csv")

# The 8 water-temperature-model forcing variables, in a stable column order.
FORCING_VARS = ["prcp", "tmax", "tmin", "wind", "srad", "lrad", "qair", "rhum"]


def list_parquets(parquet_dir: Path) -> dict[tuple[str, str], Path]:
    """Map (simulation, variable) -> parquet path, parsing `{sim}__{var}.parquet`."""
    out: dict[tuple[str, str], Path] = {}
    for p in sorted(parquet_dir.glob("*.parquet")):
        m = re.match(r"^(.+)__([A-Za-z0-9_]+)\.parquet$", p.name)
        if not m:
            continue
        out[(m.group(1), m.group(2))] = p
    return out


def export_node(
    parquets: dict[tuple[str, str], Path],
    node: str,
    variables: list[str],
    out_dir: Path,
) -> int:
    sims = sorted({s for s, _ in parquets})
    if not sims:
        log.warning("no parquets found; nothing to export")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for sim in sims:
        series: dict[str, pd.Series] = {}
        missing_var: list[str] = []
        node_absent = False
        for var in variables:
            p = parquets.get((sim, var))
            if p is None:
                missing_var.append(var)
                continue
            try:
                df = drb_io.read_parquet(p)
            except Exception as e:  # noqa: BLE001
                log.warning("%s: skip %s: %s", sim, p.name, e)
                missing_var.append(var)
                continue
            if node not in df.columns:
                node_absent = True
                break
            series[var] = df[node]

        if node_absent:
            log.warning("%s: node %r not present in columns; skipping simulation", sim, node)
            continue
        if not series:
            log.warning("%s: none of the requested variables present; skipping", sim)
            continue

        # Join on the union of dates, keep requested column order.
        wide = pd.DataFrame({var: series[var] for var in variables if var in series})
        wide = wide.sort_index()
        wide.index.name = "date"

        if missing_var:
            log.warning("%s: missing variables (written as NaN): %s", sim, ",".join(missing_var))
            for var in missing_var:                # keep full column set + order
                wide[var] = pd.NA
        wide = wide[variables]
        # Emit unit-suffixed column names (e.g. prcp -> prcp_mm_day) so the CSV
        # schema is self-documenting and consistent with the streamflow join (08).
        wide = wide.rename(columns=sf_mod.FORCING_UNIT_NAMES)
        # Normalize to a date key (drop the noon stamp) so daily series from other
        # sources (streamflow at midnight) align on the same row when joined in 08.
        wide.index = wide.index.normalize()

        dest = out_dir / f"{node}__{sim}.csv"
        wide.to_csv(dest, index=True)
        log.info("wrote %s  (%d rows × %d vars)", dest, len(wide), wide.shape[1])
        written += 1

    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--node", default="cannonsville", help="node-basin column to extract")
    ap.add_argument("--variables", nargs="+", default=FORCING_VARS,
                    help="variables (columns) to include, in order")
    ap.add_argument("--out", default=None, help="output dir (default: <final_parquet>/../csv)")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    parquet_dir = cfg.paths.final_parquet
    out_dir = Path(args.out).resolve() if args.out else (parquet_dir.parent / "csv")

    parquets = list_parquets(parquet_dir)
    log.info("found %d parquets in %s; extracting node=%r vars=%s",
             len(parquets), parquet_dir, args.node, ",".join(args.variables))
    n = export_node(parquets, args.node, args.variables, out_dir)
    log.info("done: %d CSVs written to %s", n, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
