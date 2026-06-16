"""Sanity-check the streamflow join: is routed flow physically coupled to forcing?

A correct scenario mapping should show routed streamflow responding to
precipitation. For each joined CSV with both columns, this scatters
`prcp_mm_day` vs each `streamflow_*_mgd`, prints Pearson & Spearman
correlations, and saves a PNG per config under `figures/streamflow_validation/`.

A clearly positive relationship (and positive correlations) is the pass signal;
a flat or nonsensical cloud points to a mis-mapped or misaligned scenario.

    python scripts/diagnostics/03_validate_streamflow_join.py [--config config.yaml]
                                                              [--node cannonsville]
                                                              [--csv-dir data/final/csv]
                                                              [--out figures/streamflow_validation]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[2] / "src"))

from cmip6_drb import config as cfg_mod, streamflow as sf_mod  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("validate_streamflow")

PRCP_COL = sf_mod.FORCING_UNIT_NAMES["prcp"]  # "prcp_mm_day"


def streamflow_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("streamflow_") and c.endswith("_mgd")]


def validate_one(sim: str, csv_path: Path, out_dir: Path) -> bool:
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    flow_cols = streamflow_cols(df)
    if PRCP_COL not in df.columns or not flow_cols:
        log.info("%s: missing %s or streamflow cols; skipping", sim, PRCP_COL)
        return False

    # Annual water-balance view: a correct mapping makes annual precipitation
    # (mm/yr) and annual mean routed flow (mgd) clearly co-vary. Same-day daily
    # values are decoupled by snow storage, baseflow, and routing lag, so they
    # are a weak test; the annual aggregation is the physically meaningful one.
    # Keep only complete years so partial-year endpoints don't distort sums.
    counts = df[PRCP_COL].resample("YE").count()
    full_years = counts[counts >= 365].index.year
    prcp_yr = df[PRCP_COL].resample("YE").sum()
    prcp_yr = prcp_yr[prcp_yr.index.year.isin(full_years)]

    fig, axes = plt.subplots(1, len(flow_cols), figsize=(5 * len(flow_cols), 4.5), squeeze=False)
    for ax, fcol in zip(axes[0], flow_cols):
        flow_yr = df[fcol].resample("YE").mean()
        pair = pd.concat([prcp_yr, flow_yr], axis=1).dropna()
        pair = pair[pair.index.year.isin(full_years)]
        if pair.empty:
            ax.set_title(f"{fcol}\n(no overlapping data)")
            continue
        pearson = pair[PRCP_COL].corr(pair[fcol], method="pearson")
        spearman = pair[PRCP_COL].corr(pair[fcol], method="spearman")
        ax.scatter(pair[PRCP_COL], pair[fcol], s=18, alpha=0.7)
        ax.set_xlabel("annual " + PRCP_COL + " (sum)")
        ax.set_ylabel("annual " + fcol + " (mean)")
        ax.set_title(f"{fcol}\nPearson={pearson:.2f}  Spearman={spearman:.2f}  n={len(pair)} yrs")
        log.info("%s | %s (annual): Pearson=%.3f Spearman=%.3f (n=%d yrs)",
                 sim, fcol, pearson, spearman, len(pair))
    fig.suptitle(f"{sim} — annual precip vs routed streamflow (water-balance check)",
                 fontsize=10, y=1.02)
    fig.tight_layout()
    out_path = out_dir / f"{sim}__prcp_vs_streamflow.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", out_path)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--node", default="cannonsville")
    ap.add_argument("--csv-dir", default=None)
    ap.add_argument("--out", default="figures/streamflow_validation")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    csv_dir = Path(args.csv_dir).resolve() if args.csv_dir else (cfg.paths.final_parquet.parent / "csv")
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(csv_dir.glob(f"{args.node}__*.csv"))
    if not paths:
        log.warning("no %s__*.csv files in %s", args.node, csv_dir)
        return 0

    made = 0
    for p in paths:
        sim = p.name[len(args.node) + 2 : -len(".csv")]
        if validate_one(sim, p, out_dir):
            made += 1
    log.info("done: %d validation figures in %s", made, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
