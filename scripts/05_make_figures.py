"""Reproducible figures from data/final/parquet/.

Defensive: each figure attempts to render with whatever (sim, var) parquets
are present and skips with a warning if its required inputs are missing. Safe
to run at any pipeline stage — useful both for early peeks and final docs.

    python scripts/05_make_figures.py [--config config.yaml] [--out figures/]

All figures are saved as PNG (300 dpi) under `figures/`. Re-running overwrites.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[1] / "src"))

from cmip6_drb import config as cfg_mod, io as drb_io  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("figures")

UPPER_DRB_NODES = ["cannonsville", "pepacton", "neversink"]
HISTORICAL_SIMS = {"DaymetV4", "Livneh"}

# Stable-ish color map for simulations grouped by GCM family.
GCM_COLORS = {
    "DaymetV4": "#222222",
    "Livneh": "#666666",
    "ACCESS-CM2": "#1f77b4",
    "BCC-CSM2-MR": "#ff7f0e",
    "CNRM-ESM2-1": "#2ca02c",
    "EC-Earth3": "#d62728",
    "MPI-ESM1-2-HR": "#9467bd",
    "MRI-ESM2-0": "#8c564b",
    "NorESM2-MM": "#e377c2",
}


def _color_for_sim(sim: str) -> str:
    if sim in GCM_COLORS:
        return GCM_COLORS[sim]
    for gcm, c in GCM_COLORS.items():
        if sim.startswith(gcm + "_"):
            return c
    return "#999999"


def list_parquets(parquet_dir: Path) -> dict[tuple[str, str], Path]:
    out: dict[tuple[str, str], Path] = {}
    for p in sorted(parquet_dir.glob("*.parquet")):
        m = re.match(r"^(.+)__([A-Za-z0-9_]+)\.parquet$", p.name)
        if not m:
            continue
        out[(m.group(1), m.group(2))] = p
    return out


# ---------------------------------------------------------------------------
# Figure 1: data inventory heatmap
# ---------------------------------------------------------------------------

def fig_inventory(parquets: dict[tuple[str, str], Path], out_path: Path) -> None:
    if not parquets:
        log.warning("inventory: no parquets, skipping")
        return
    sims = sorted({s for s, _ in parquets})
    vars_ = sorted({v for _, v in parquets})

    coverage = np.full((len(sims), len(vars_)), np.nan, dtype=np.float32)
    for i, s in enumerate(sims):
        for j, v in enumerate(vars_):
            p = parquets.get((s, v))
            if not p:
                continue
            try:
                df = drb_io.read_parquet(p)
            except Exception as e:  # noqa: BLE001
                log.warning("inventory: skip %s: %s", p.name, e)
                continue
            yrs = df.index.year.unique()
            coverage[i, j] = len(yrs)

    fig, ax = plt.subplots(figsize=(max(8, 0.45 * len(vars_)), max(4, 0.35 * len(sims))))
    im = ax.imshow(coverage, aspect="auto", cmap="viridis", vmin=0)
    ax.set_xticks(range(len(vars_)))
    ax.set_xticklabels(vars_, rotation=70, ha="right", fontsize=8)
    ax.set_yticks(range(len(sims)))
    ax.set_yticklabels(sims, fontsize=8)
    ax.set_xlabel("variable")
    ax.set_title(f"Years populated per (simulation × variable)  —  {len(parquets)} parquets, "
                 f"{int(np.nansum(coverage)):,} sim·var·year combinations")
    cbar = fig.colorbar(im, ax=ax, label="years")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", out_path)


# ---------------------------------------------------------------------------
# Figure 2: annual total precipitation at upper-DRB nodes
# ---------------------------------------------------------------------------

def fig_annual_prcp(parquets: dict[tuple[str, str], Path], out_path: Path) -> None:
    sims_with_prcp = [(s, v, p) for (s, v), p in parquets.items() if v == "prcp"]
    if not sims_with_prcp:
        log.warning("annual_prcp: no prcp parquets, skipping")
        return

    fig, axes = plt.subplots(len(UPPER_DRB_NODES), 1, figsize=(10, 8), sharex=True)
    if len(UPPER_DRB_NODES) == 1:
        axes = [axes]

    for ax, node in zip(axes, UPPER_DRB_NODES):
        for sim, _, p in sims_with_prcp:
            try:
                df = drb_io.read_parquet(p)
            except Exception as e:  # noqa: BLE001
                log.warning("annual_prcp: skip %s: %s", sim, e)
                continue
            if node not in df.columns:
                continue
            annual = df[node].resample("YE").sum()
            # drop incomplete years (any sim with <300 daily obs for the year)
            counts = df[node].resample("YE").count()
            annual = annual.where(counts >= 300)
            ax.plot(annual.index.year, annual.values,
                    color=_color_for_sim(sim),
                    alpha=0.85 if sim in HISTORICAL_SIMS else 0.55,
                    lw=1.6 if sim in HISTORICAL_SIMS else 0.8,
                    label=sim if sim in HISTORICAL_SIMS else None)
        ax.set_ylabel(f"annual prcp\n{node} (mm/yr)")
        ax.grid(alpha=0.3)

    # legend on top-most axis (historical only — future runs share GCM colors)
    axes[0].legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    axes[-1].set_xlabel("year")
    fig.suptitle("Annual total precipitation at upper-DRB / NYC reservoirs\n"
                 f"(historical bold, future runs faded — {len(sims_with_prcp)} simulations shown)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", out_path)


# ---------------------------------------------------------------------------
# Figure 3: monthly climatology (prcp, tmax, tmin) at upper-DRB nodes
# ---------------------------------------------------------------------------

def _monthly_climatology(df: pd.DataFrame, node: str, agg: str) -> pd.Series | None:
    if node not in df.columns:
        return None
    series = df[node].dropna()
    if series.empty:
        return None
    grouped = series.groupby(series.index.month)
    if agg == "sum_per_month":
        # average over years of monthly totals
        monthly_totals = series.resample("ME").sum()
        return monthly_totals.groupby(monthly_totals.index.month).mean()
    if agg == "mean":
        return grouped.mean()
    raise ValueError(agg)


def fig_seasonal_climatology(parquets: dict[tuple[str, str], Path], out_path: Path) -> None:
    plot_specs = [
        ("prcp", "Precip (mm/month)", "sum_per_month"),
        ("tmax", "Max temp (°C)", "mean"),
        ("tmin", "Min temp (°C)", "mean"),
    ]
    available = [(v, lbl, agg) for v, lbl, agg in plot_specs
                 if any(parq_var == v for _, parq_var in parquets)]
    if not available:
        log.warning("seasonal_climatology: no prcp/tmax/tmin parquets, skipping")
        return

    fig, axes = plt.subplots(len(available), len(UPPER_DRB_NODES),
                              figsize=(4 * len(UPPER_DRB_NODES), 2.6 * len(available)),
                              sharex=True, squeeze=False)
    months = np.arange(1, 13)
    for r, (var, ylabel, agg) in enumerate(available):
        for c, node in enumerate(UPPER_DRB_NODES):
            ax = axes[r, c]
            for (sim, parq_var), p in parquets.items():
                if parq_var != var:
                    continue
                try:
                    df = drb_io.read_parquet(p)
                except Exception:
                    continue
                clim = _monthly_climatology(df, node, agg)
                if clim is None:
                    continue
                clim = clim.reindex(months)
                is_hist = sim in HISTORICAL_SIMS
                ax.plot(months, clim.values,
                        color=_color_for_sim(sim),
                        lw=1.8 if is_hist else 0.8,
                        alpha=0.95 if is_hist else 0.45,
                        label=sim if is_hist and r == 0 and c == 0 else None)
            if r == 0:
                ax.set_title(node, fontsize=10)
            if c == 0:
                ax.set_ylabel(ylabel, fontsize=9)
            if r == len(available) - 1:
                ax.set_xlabel("month")
            ax.set_xticks(months)
            ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
            ax.grid(alpha=0.3)

    if any(s in HISTORICAL_SIMS for s, _ in parquets):
        axes[0, 0].legend(loc="best", fontsize=8, frameon=False)
    fig.suptitle("Monthly climatology at upper-DRB / NYC reservoirs\n"
                 "(historical bold; future runs faded, colored by GCM)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", out_path)


# ---------------------------------------------------------------------------
# Figure 4: catchment polygons with annual mean prcp shading
# ---------------------------------------------------------------------------

def fig_node_basin_map(cfg, parquets: dict[tuple[str, str], Path], out_path: Path) -> None:
    try:
        import geopandas as gpd
    except ImportError:
        log.warning("map: geopandas not available, skipping")
        return

    shp = Path(cfg["paths"]["shapefile"])
    if not shp.exists():
        log.warning("map: shapefile %s not found, skipping", shp)
        return

    gdf = gpd.read_file(shp)
    if gdf.crs is None or "ISN" in str(gdf.crs):
        gdf = gdf.set_crs("EPSG:4326", allow_override=True)

    # Optional: shade by DaymetV4 long-term annual prcp if available
    annual = None
    daymet_prcp = parquets.get(("DaymetV4", "prcp"))
    if daymet_prcp is not None:
        try:
            df = drb_io.read_parquet(daymet_prcp)
            annual = df.resample("YE").sum().mean(axis=0)  # long-term mean annual prcp per node
        except Exception as e:  # noqa: BLE001
            log.warning("map: could not load DaymetV4 prcp: %s", e)

    # The 33 polygons are upstream-of-node basins, so they overlap heavily
    # (e.g. delTrenton contains everything upstream). Draw largest first so
    # smaller upper-headwater basins layer on top and remain visible.
    node_field = "node" if "node" in gdf.columns else gdf.columns[0]
    # Bounding-box area proxy works on geographic CRS without precision warnings;
    # ordering is what matters here (largest behind, smallest in front).
    bounds = gdf.geometry.bounds
    gdf = gdf.assign(_area=(bounds["maxx"] - bounds["minx"]) * (bounds["maxy"] - bounds["miny"])
                     ).sort_values("_area", ascending=False)

    fig, ax = plt.subplots(figsize=(8, 9))
    if annual is not None:
        gdf["_prcp"] = gdf[node_field].map(annual.to_dict())
        gdf.plot(column="_prcp", ax=ax, cmap="YlGnBu", edgecolor="black",
                 linewidth=0.5, alpha=0.55, legend=True,
                 legend_kwds={"label": "Long-term annual prcp\n(mm/yr, DaymetV4)",
                              "shrink": 0.6})
    else:
        gdf.plot(ax=ax, edgecolor="black", facecolor="none", linewidth=0.5)

    # Centroid markers + labels for upper-DRB / NYC reservoirs
    for _, row in gdf.iterrows():
        name = row[node_field]
        if name in UPPER_DRB_NODES:
            cx, cy = row.geometry.centroid.x, row.geometry.centroid.y
            ax.plot(cx, cy, marker="*", markersize=12, color="red",
                    markeredgecolor="black", zorder=5)
            ax.annotate(name, xy=(cx, cy), xytext=(8, 6), textcoords="offset points",
                        fontsize=9, weight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="black", alpha=0.85),
                        zorder=6)

    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title("Pywr-DRB node basins (33 catchments)\n"
                 + ("shaded by long-term DaymetV4 annual prcp" if annual is not None
                    else "DaymetV4 prcp parquet not yet available"),
                 fontsize=11)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", out_path)


# ---------------------------------------------------------------------------
# Figure 5: historical sim cross-validation at cannonsville (overlap years only)
# ---------------------------------------------------------------------------

def fig_historical_cross_validation(parquets: dict[tuple[str, str], Path], out_path: Path) -> None:
    daymet = parquets.get(("DaymetV4", "prcp"))
    livneh = parquets.get(("Livneh", "prcp"))
    if not (daymet and livneh):
        log.warning("hist_cross_val: need DaymetV4 and Livneh prcp; skipping")
        return

    df_d = drb_io.read_parquet(daymet)
    df_l = drb_io.read_parquet(livneh)
    overlap = df_d.index.intersection(df_l.index)
    if overlap.empty or "cannonsville" not in df_d.columns or "cannonsville" not in df_l.columns:
        log.warning("hist_cross_val: insufficient overlap or missing column; skipping")
        return
    d_ann = df_d.loc[overlap, "cannonsville"].resample("YE").sum()
    l_ann = df_l.loc[overlap, "cannonsville"].resample("YE").sum()

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    ax.plot(d_ann.index.year, d_ann.values, color=GCM_COLORS["DaymetV4"], lw=1.8, label="DaymetV4")
    ax.plot(l_ann.index.year, l_ann.values, color=GCM_COLORS["Livneh"], lw=1.8, label="Livneh")
    ax.set_xlabel("year"); ax.set_ylabel("annual prcp (mm/yr)")
    ax.set_title("Cannonsville annual prcp — historical reference cross-check")
    ax.grid(alpha=0.3); ax.legend()

    ax = axes[1]
    ax.scatter(d_ann.values, l_ann.values, s=14, alpha=0.7, color="#444")
    lim = [min(d_ann.min(), l_ann.min()) * 0.95, max(d_ann.max(), l_ann.max()) * 1.05]
    ax.plot(lim, lim, color="red", lw=1, ls="--", label="1:1")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("DaymetV4 annual prcp (mm/yr)")
    ax.set_ylabel("Livneh annual prcp (mm/yr)")
    ax.set_title("DaymetV4 vs Livneh — overlap years")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3); ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", out_path)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(cfg_mod.default_config_path()))
    ap.add_argument("--out", default="figures", help="Output directory")
    args = ap.parse_args()

    cfg = cfg_mod.Config.load(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    parquets = list_parquets(cfg.paths.final_parquet)
    log.info("Found %d parquet files (%d sims × %d vars)",
             len(parquets), len({s for s, _ in parquets}), len({v for _, v in parquets}))

    fig_inventory(parquets, out_dir / "01_data_inventory.png")
    fig_annual_prcp(parquets, out_dir / "02_annual_prcp_upper_drb.png")
    fig_seasonal_climatology(parquets, out_dir / "03_seasonal_climatology.png")
    fig_node_basin_map(cfg, parquets, out_dir / "04_node_basins_map.png")
    fig_historical_cross_validation(parquets, out_dir / "05_historical_cross_validation.png")
    log.info("Done. Figures in %s/", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
