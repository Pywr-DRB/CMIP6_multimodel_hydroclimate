"""High-quality diagnostic figures for the CMIP6-DRB dataset.

Each figure answers a specific scientific question about the distributional
properties or temporal dynamics of basin-aggregated daily climate variables
(prcp, tmax, tmin, wind). Designed to be readable as standalone slides — see
`cmip6_drb.styling.apply_labels` for the explicit-labeling standard.

Run:
    python scripts/diagnostics/02_make_diagnostics.py [--config config.yaml] [--out figures/diagnostics/]
                                          [--only 01,02,07]

Each `fig_NN_xxx()` function:
- declares its required (sim_set, period_set, var_set) at the top,
- skips with `log.warning(...)` if any required parquet is missing,
- writes `figures/diagnostics/NN_name.png` at 300 dpi,
- writes a sibling `NN_name.txt` provenance file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parents[2] / "src"))

from cmip6_drb import config as cfg_mod, io as drb_io  # noqa: E402
from cmip6_drb import diagnostics as D  # noqa: E402
from cmip6_drb import styling as ST  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("diagnostics")


# ---------------------------------------------------------------------------
# Helpers used by multiple figures
# ---------------------------------------------------------------------------

def _gcm_sims(parquets: dict[tuple[str, str], Path]) -> list[str]:
    """Sorted list of unique non-obs simulations present in the parquet set."""
    sims = sorted({s for s, _ in parquets} - set(ST.OBS_NAMES))
    return sims


def _load_basin_series(parquets, sim: str, var: str, basin: str,
                      start: int, end: int) -> pd.Series | None:
    """Load `(sim, var)` parquet, slice by year, return one basin column."""
    p = parquets.get((sim, var))
    if p is None:
        return None
    df = drb_io.read_parquet(p)
    df = D.slice_period(df, start, end)
    if basin not in df.columns or df[basin].dropna().empty:
        return None
    return df[basin].astype(float).rename(f"{sim}|{var}|{basin}|{start}-{end}")


def _load_all_basins(parquets, sim: str, var: str,
                    start: int, end: int) -> pd.DataFrame | None:
    p = parquets.get((sim, var))
    if p is None:
        return None
    df = drb_io.read_parquet(p)
    df = D.slice_period(df, start, end)
    if df.empty:
        return None
    return df.astype(float)


def _period(cfg, key: str) -> tuple[int, int]:
    p = cfg["diagnostics"]["periods"][key]
    return int(p["start"]), int(p["end"])


# ---------------------------------------------------------------------------
# Figure stubs (implemented in subsequent edits)
# ---------------------------------------------------------------------------

def fig_01_quantile_shift(parquets, cfg, out_dir: Path) -> None:
    """Fig 01 — Where in the distribution does the late-21st-century projection shift?

    For each (variable × season), plot each GCM's F-late empirical quantiles
    against the obs-H Daymet quantiles. The 1:1 line means "no change"; lines
    rising above 1:1 mean the F-late distribution is heavier at that quantile.
    Reveals whether the projected shift is concentrated in the tails or the body.
    """
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    variables = list(diag["variables"])
    basin = diag["nodes_focus"][0]
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")

    sims_future = _gcm_sims(parquets)
    if not sims_future:
        log.warning("fig_01: no future GCM sims, skipping")
        return

    seasons = D.SEASONS
    n_rows = len(variables)
    n_cols = len(seasons)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(2.6 * n_cols, 2.4 * n_rows),
                             squeeze=False)
    qs = np.linspace(0.005, 0.995, 80)
    sample_sizes: dict[str, int] = {}

    for r, var in enumerate(variables):
        if (obs, var) not in parquets:
            for c in range(n_cols):
                axes[r][c].set_visible(False)
            continue
        s_obs = _load_basin_series(parquets, obs, var, basin, h_lo, h_hi)
        if s_obs is None:
            continue
        sample_sizes[f"{obs}|{var}|H"] = int(s_obs.size)

        for c, season in enumerate(seasons):
            ax = axes[r][c]
            obs_season = s_obs.loc[D.season_mask(s_obs.index, season)].dropna().values
            if obs_season.size < 30:
                ax.set_visible(False)
                continue
            q_obs = np.quantile(obs_season, qs)

            # Per-GCM F-late curve
            for sim in sims_future:
                s_f = _load_basin_series(parquets, sim, var, basin, fl_lo, fl_hi)
                if s_f is None:
                    continue
                f_season = s_f.loc[D.season_mask(s_f.index, season)].dropna().values
                if f_season.size < 30:
                    continue
                q_f = np.quantile(f_season, qs)
                ax.plot(q_obs, q_f, lw=1.0, alpha=0.85,
                        color=ST.color_for_sim(sim),
                        label=ST.gcm_of(sim) if (r == 0 and c == 0) else None)
                sample_sizes[f"{sim}|{var}|F_late|{season}"] = int(f_season.size)

            # 1:1 reference (no change)
            lo = float(np.min(q_obs))
            hi = float(np.max(q_obs))
            ax.plot([lo, hi], [lo, hi], color="#222", ls="--", lw=1.0,
                    label="1:1 (no change)" if (r == 0 and c == 0) else None)

            ax.set_title(f"{season} · {var}", fontsize=9)
            if r == n_rows - 1:
                ax.set_xlabel(f"{obs} H-quantile  [{ST.VAR_UNITS.get(var, '')}]", fontsize=8)
            if c == 0:
                ax.set_ylabel(f"GCM F-late quantile  [{ST.VAR_UNITS.get(var, '')}]", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3)
            if var == "prcp":
                ax.set_xscale("symlog", linthresh=1.0)
                ax.set_yscale("symlog", linthresh=1.0)

    # Single legend on the top-left axis
    axes[0][0].legend(frameon=False, fontsize=7, loc="upper left")
    fig.tight_layout(rect=(0, 0.01, 1, 0.95))
    sub = (f"H = {h_lo}-{h_hi} ({obs}); F-late = {fl_lo}-{fl_hi} (per GCM, SSP585 DBCCA-Daymet). "
           f"Basin = {basin}. Lines above 1:1 = quantile increases; below = decreases. "
           f"prcp axes use symlog (linthresh=1 mm/day).")
    ST.apply_labels(
        fig, fig_number="01",
        question=("How do the late-21st-century daily distributions differ from the "
                  "historical Daymet baseline, by season and variable?"),
        sub_caption=sub,
    )
    out_path = out_dir / "01_quantile_shift.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="01_quantile_shift",
        sims=[obs] + sims_future,
        periods={"H": [h_lo, h_hi], "F_late": [fl_lo, fl_hi]},
        sample_sizes=sample_sizes,
        notes=(f"Per-quantile F-late vs obs-H comparison at {basin}. "
               f"80 quantile probes from p=0.005 to p=0.995."),
    )
    log.info("wrote %s", out_path)


def fig_02_wet_day_decomp(parquets, cfg, out_dir: Path) -> None:
    """Fig 02 — Is projected mean-prcp change driven by wet-day frequency or intensity?

    Mean daily prcp = P(wet) × E[prcp | wet]. Plot each simulation's position in
    (frequency, intensity) space, with arrows linking each GCM's H-window
    location to its F-late location. Arrows that move right = more wet days;
    arrows up = heavier rain when it does fall. The Daymet H-window position is
    the black anchor.
    """
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    threshold = float(diag["wet_day_threshold_mm"])
    basin = diag["nodes_focus"][0]
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")

    if (obs, "prcp") not in parquets:
        log.warning("fig_02: missing %s|prcp, skipping", obs)
        return
    sims_future = _gcm_sims(parquets)
    if not sims_future:
        log.warning("fig_02: no future GCM sims, skipping")
        return

    seasons = D.SEASONS
    fig, axes = plt.subplots(1, len(seasons), figsize=(3.4 * len(seasons), 5.0),
                             squeeze=False)
    sample_sizes: dict[str, int] = {}

    for c, season in enumerate(seasons):
        ax = axes[0][c]
        # Daymet H anchor
        s_obs = _load_basin_series(parquets, obs, "prcp", basin, h_lo, h_hi)
        if s_obs is None:
            ax.set_visible(False)
            continue
        obs_seas = s_obs.loc[D.season_mask(s_obs.index, season)]
        obs_stats = D.wet_day_stats(obs_seas, threshold)
        sample_sizes[f"{obs}|prcp|H|{season}"] = obs_stats["n"]
        ax.scatter([obs_stats["p_wet"]], [obs_stats["wet_intensity"]],
                   s=110, marker="*", color="#000", zorder=10,
                   label=f"{obs} obs · H" if c == 0 else None,
                   edgecolors="white", linewidths=0.8)

        # Per-GCM arrow from H to F-late
        for sim in sims_future:
            s_h = _load_basin_series(parquets, sim, "prcp", basin, h_lo, h_hi)
            s_f = _load_basin_series(parquets, sim, "prcp", basin, fl_lo, fl_hi)
            color = ST.color_for_sim(sim)
            # The GCMs only have F runs; H comes from Daymet (their BC target).
            # Use the obs anchor as the pre-arrow position so the arrow lengths
            # show projected change relative to historical observations.
            anchor = (obs_stats["p_wet"], obs_stats["wet_intensity"])
            if s_f is None:
                continue
            f_seas = s_f.loc[D.season_mask(s_f.index, season)]
            f_stats = D.wet_day_stats(f_seas, threshold)
            sample_sizes[f"{sim}|prcp|F_late|{season}"] = f_stats["n"]
            ax.annotate(
                "",
                xy=(f_stats["p_wet"], f_stats["wet_intensity"]),
                xytext=anchor,
                arrowprops=dict(arrowstyle="->", color=color, lw=1.2, alpha=0.85),
            )
            ax.scatter([f_stats["p_wet"]], [f_stats["wet_intensity"]],
                       s=42, color=color, alpha=0.95, edgecolors="white",
                       linewidths=0.6,
                       label=ST.gcm_of(sim) if c == 0 else None)

        ax.set_xlabel(f"P(wet day) — daily prcp ≥ {threshold:g} mm")
        if c == 0:
            ax.set_ylabel("Wet-day mean intensity (mm day$^{-1}$)")
        ax.set_title(f"{season}", fontsize=10)
        ax.grid(alpha=0.3)

    axes[0][0].legend(frameon=False, fontsize=7, loc="best")
    fig.tight_layout(rect=(0, 0.02, 1, 0.85))
    sub = (f"Anchor (★) = {obs} H ({h_lo}-{h_hi}); arrowhead = each GCM F-late ({fl_lo}-{fl_hi}). "
           f"Threshold = {threshold:g} mm/day basin-mean. Basin = {basin}. "
           f"→ = wetter days more frequent; ↑ = heavier rain when it does fall. "
           f"Mean prcp change = (Δfrequency · intensity) + (frequency · Δintensity).")
    ST.apply_labels(
        fig, fig_number="02",
        question=("Is the projected mean-prcp shift driven by changes in wet-day "
                  "frequency, in wet-day intensity, or both?"),
        sub_caption=sub,
    )
    out_path = out_dir / "02_wet_day_decomp.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="02_wet_day_decomp",
        sims=[obs] + sims_future,
        periods={"H": [h_lo, h_hi], "F_late": [fl_lo, fl_hi]},
        sample_sizes=sample_sizes,
        notes=f"Wet-day threshold {threshold} mm/day basin-mean at {basin}.",
    )
    log.info("wrote %s", out_path)


def fig_03_spell_survival(parquets, cfg, out_dir: Path) -> None:
    """Fig 03 — Are dry and wet spells getting longer?

    Empirical survival curve S(L) = P(spell length ≥ L) of consecutive dry-day
    and wet-day spells, by season. Bias correction does NOT fix temporal
    structure, so this is one of the few figures where Daymet-H and GCM-H would
    disagree even on the historical period — but here we compare each GCM's
    F-late spell statistics to Daymet-H, the reference baseline.
    """
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    threshold = float(diag["wet_day_threshold_mm"])
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")

    if (obs, "prcp") not in parquets:
        log.warning("fig_03: missing %s|prcp, skipping", obs)
        return
    sims_future = _gcm_sims(parquets)
    if not sims_future:
        log.warning("fig_03: no future GCM sims, skipping")
        return

    # Use upper-DRB composite series (mean of cannonsville/pepacton/neversink) so the
    # spell statistics characterize the headwaters region jointly, not a single point.
    upper_drb = ["cannonsville", "pepacton", "neversink"]
    seasons = D.SEASONS
    fig, axes = plt.subplots(len(seasons), 2, figsize=(8.0, 9.0),
                             squeeze=False, sharex="col")
    sample_sizes: dict[str, int] = {}

    def _composite_prcp(sim, lo, hi) -> pd.Series | None:
        df = _load_all_basins(parquets, sim, "prcp", lo, hi)
        if df is None:
            return None
        cols = [c for c in upper_drb if c in df.columns]
        if not cols:
            return None
        return df[cols].mean(axis=1)

    for r, season in enumerate(seasons):
        for c, kind in enumerate(("dry", "wet")):
            ax = axes[r][c]
            # Daymet H curve (reference)
            s_obs = _composite_prcp(obs, h_lo, h_hi)
            if s_obs is not None:
                obs_seas = s_obs.loc[D.season_mask(s_obs.index, season)]
                wm = D.wet_day_mask(obs_seas, threshold)
                spell_mask = wm if kind == "wet" else (1 - wm)
                lengths = D.spell_lengths(spell_mask)
                if lengths.size:
                    L, S = D.survival(lengths)
                    ax.step(L, S, where="post", color="#000", lw=1.8,
                            label=f"{obs} obs · H ({lengths.size} spells)")
                sample_sizes[f"{obs}|H|{season}|{kind}"] = int(lengths.size)
            # Each GCM F-late
            for sim in sims_future:
                s_f = _composite_prcp(sim, fl_lo, fl_hi)
                if s_f is None:
                    continue
                f_seas = s_f.loc[D.season_mask(s_f.index, season)]
                wm = D.wet_day_mask(f_seas, threshold)
                spell_mask = wm if kind == "wet" else (1 - wm)
                lengths = D.spell_lengths(spell_mask)
                if lengths.size == 0:
                    continue
                L, S = D.survival(lengths)
                ax.step(L, S, where="post", lw=1.0, alpha=0.7,
                        color=ST.color_for_sim(sim),
                        label=ST.gcm_of(sim) + " · F-late")
                sample_sizes[f"{sim}|F_late|{season}|{kind}"] = int(lengths.size)

            ax.set_yscale("log")
            ax.set_title(f"{season} · {kind} spells", fontsize=10)
            if r == len(seasons) - 1:
                ax.set_xlabel("Spell length L (days)")
            if c == 0:
                ax.set_ylabel("S(L) = P(spell ≥ L)")
            ax.grid(alpha=0.3, which="both")
            ax.set_xlim(left=0)

    axes[0][0].legend(frameon=False, fontsize=6.5, loc="lower left")
    fig.tight_layout(rect=(0, 0.02, 1, 0.92))
    sub = (f"Reference: {obs} obs over {h_lo}-{h_hi} (heavy black). "
           f"Per-GCM F-late: {fl_lo}-{fl_hi}. Wet-day threshold = {threshold:g} mm/day "
           f"basin-mean. Series = upper-DRB composite (mean of cannonsville, pepacton, "
           f"neversink). y-axis log-scaled to expose extreme-spell tail.")
    ST.apply_labels(
        fig, fig_number="03",
        question=("How does the persistence of dry and wet weather change in the "
                  "late 21st century?"),
        sub_caption=sub,
    )
    out_path = out_dir / "03_spell_survival.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="03_spell_survival",
        sims=[obs] + sims_future,
        periods={"H": [h_lo, h_hi], "F_late": [fl_lo, fl_hi]},
        sample_sizes=sample_sizes,
        notes=("Empirical survival curves for consecutive dry/wet day spells by season. "
               "Wet day = basin-mean prcp >= threshold. Series = upper-DRB composite."),
    )
    log.info("wrote %s", out_path)


def fig_04_gev_return(parquets, cfg, out_dir: Path) -> None:
    """Fig 04 — How do annual extremes line up across simulations?

    Empirical ranked annual maxima with Weibull plotting position. For each
    (sim × variable × basin), sort the AM series, assign empirical return
    period T_i = (n+1)/(n+1-i) at rank i, and plot. No GEV fit, no bootstrap —
    just the data, sorted, on a Gumbel-style x-axis. Reveals where each
    GCM's extreme tail sits relative to the obs reference, with no
    distributional assumption.
    """
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    nodes = list(diag["nodes_focus"])
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")

    sims_future = _gcm_sims(parquets)
    if not sims_future:
        log.warning("fig_04: no future GCM sims, skipping")
        return

    variables = ["prcp", "tmax"]
    n_rows = len(variables)
    n_cols = len(nodes)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(2.7 * n_cols, 3.0 * n_rows),
                             squeeze=False, sharex="row")
    sample_sizes: dict[str, int] = {}

    def _ranked_T(am: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        am = np.sort(np.asarray(am, dtype=float))
        am = am[np.isfinite(am)]
        n = am.size
        if n == 0:
            return np.array([]), np.array([])
        # Weibull plotting position: i in 1..n, P_nonexceed = i/(n+1), T = 1/(1-P)
        i = np.arange(1, n + 1)
        T = (n + 1) / (n + 1 - i)
        return T, am

    for ri, var in enumerate(variables):
        for ci, node in enumerate(nodes):
            ax = axes[ri][ci]
            # obs H
            s_obs = _load_basin_series(parquets, obs, var, node, h_lo, h_hi)
            if s_obs is not None:
                am = D.annual_maxima(s_obs).values
                T_, vals = _ranked_T(am)
                if T_.size:
                    ax.plot(T_, vals, marker="o", ms=3, color="#000", lw=1.4,
                            alpha=0.95,
                            label=f"{obs} obs · H ({am.size} yr)" if (ri == 0 and ci == 0) else None)
                    sample_sizes[f"{obs}|{var}|H|{node}"] = int(am.size)
            # GCM F-late
            for sim in sims_future:
                s_f = _load_basin_series(parquets, sim, var, node, fl_lo, fl_hi)
                if s_f is None:
                    continue
                am = D.annual_maxima(s_f).values
                T_, vals = _ranked_T(am)
                if T_.size == 0:
                    continue
                ax.plot(T_, vals, marker=".", ms=3, lw=0.9, alpha=0.65,
                        color=ST.color_for_sim(sim),
                        label=ST.gcm_of(sim) + " · F-late" if (ri == 0 and ci == 0) else None)
                sample_sizes[f"{sim}|{var}|F_late|{node}"] = int(am.size)

            ax.set_xscale("log")
            ax.set_title(f"{node} · {var}", fontsize=9)
            if ri == n_rows - 1:
                ax.set_xlabel("Empirical return period T (yr)")
            if ci == 0:
                unit = ST.VAR_UNITS.get(var, "")
                ax.set_ylabel(f"Annual max {var} [{unit}]")
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3, which="both")

    axes[0][0].legend(frameon=False, fontsize=7, loc="best")
    fig.tight_layout(rect=(0, 0.02, 1, 1 - 0.9 / fig.get_figheight()))
    sub = (f"H = {h_lo}-{h_hi} ({obs}, black, ●); F-late = {fl_lo}-{fl_hi} (per GCM). "
           f"Empirical Weibull plotting position T = (n+1)/(n+1-rank). "
           f"No GEV fit, no smoothing — points are sorted annual maxima.")
    ST.apply_labels(
        fig, fig_number="04",
        question=("How do annual-maxima extremes for daily prcp and Tmax "
                  "compare between obs and each GCM, across upper-DRB nodes?"),
        sub_caption=sub,
    )
    out_path = out_dir / "04_annual_maxima_ranked.png"
    ST.fig_save(fig, out_path)
    # Remove the older heavy GEV figure if it's lingering
    legacy = out_dir / "04_gev_return_levels.png"
    if legacy.exists():
        legacy.unlink()
        legacy.with_suffix(".txt").unlink(missing_ok=True)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="04_annual_maxima_ranked",
        sims=[obs] + sims_future,
        periods={"H": [h_lo, h_hi], "F_late": [fl_lo, fl_hi]},
        sample_sizes=sample_sizes,
        notes=("Empirical ranked AM. No fitted distribution — just sorted data "
               "with Weibull plotting position. Replaces an earlier GEV-MLE+bootstrap "
               "draft that was too slow for interactive use."),
    )
    log.info("wrote %s", out_path)


def fig_05_ar1_spectra(parquets, cfg, out_dir: Path) -> None:
    """Fig 05 — Persistence and variance across timescales.

    Top row: lag-1 autocorrelation of daily series, per (variable × season ×
    simulation). A simple bar chart with obs reference. Cheap to compute.

    Bottom row: Welch power spectrum of daily anomalies (DOY climatology
    removed, linearly detrended), one panel per variable, all simulations
    overlaid. Vertical shading marks synoptic (3–7 d) and intra-seasonal
    (~30 d) bands so the reader can see whether downscaling preserves variance
    at meteorological timescales.
    """
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    variables = list(diag["variables"])
    basin = diag["nodes_focus"][0]
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")
    nperseg = int(diag.get("welch_nperseg", 1024))

    sims_future = _gcm_sims(parquets)

    fig = plt.figure(figsize=(3.0 * len(variables), 9.0))
    gs = fig.add_gridspec(2, len(variables), height_ratios=[1.0, 1.4],
                          hspace=0.45, wspace=0.30)
    sample_sizes: dict[str, int] = {}

    # ---- Top row: AR(1) bars per (season × sim) ----
    for vi, var in enumerate(variables):
        ax = fig.add_subplot(gs[0, vi])
        # Build a (season, sim) -> AR1 grid using H for obs and F-late for GCM
        grid_seasons = D.SEASONS
        sim_list = ([obs] if (obs, var) in parquets else []) + [
            s for s in sims_future if (s, var) in parquets
        ]
        ar1_table = np.full((len(grid_seasons), len(sim_list)), np.nan, dtype=float)
        for si, sim in enumerate(sim_list):
            lo, hi = (h_lo, h_hi) if sim == obs else (fl_lo, fl_hi)
            s = _load_basin_series(parquets, sim, var, basin, lo, hi)
            if s is None:
                continue
            for ji, season in enumerate(grid_seasons):
                seas = s.loc[D.season_mask(s.index, season)]
                ar1_table[ji, si] = D.ar1(seas)

        x = np.arange(len(grid_seasons))
        bw = 0.8 / max(len(sim_list), 1)
        for si, sim in enumerate(sim_list):
            offset = (si - (len(sim_list) - 1) / 2.0) * bw
            color = ST.color_for_sim(sim)
            label = ST.gcm_of(sim)
            ax.bar(x + offset, ar1_table[:, si], width=bw, color=color,
                   alpha=0.95 if sim == obs else 0.75, edgecolor="white",
                   linewidth=0.4,
                   label=label if vi == 0 else None)
        ax.set_xticks(x)
        ax.set_xticklabels(grid_seasons, fontsize=8)
        ax.set_ylabel("Daily lag-1 autocorrelation")
        ax.set_title(f"AR(1) — {var}", fontsize=10)
        ax.grid(alpha=0.3, axis="y")
        ax.axhline(0, color="#666", lw=0.5)

    # Legend on top-leftmost AR1 panel
    fig.axes[0].legend(frameon=False, fontsize=7, loc="best", ncol=1)

    # ---- Bottom row: Welch PSD of daily anomalies ----
    for vi, var in enumerate(variables):
        ax = fig.add_subplot(gs[1, vi])
        sim_list = ([obs] if (obs, var) in parquets else []) + [
            s for s in sims_future if (s, var) in parquets
        ]
        for sim in sim_list:
            lo, hi = (h_lo, h_hi) if sim == obs else (fl_lo, fl_hi)
            s = _load_basin_series(parquets, sim, var, basin, lo, hi)
            if s is None or s.dropna().size < nperseg * 2:
                continue
            anom = D.detrend_linear(D.doy_anomaly(s)).dropna()
            f, psd = D.welch_psd(anom, nperseg=nperseg)
            ax.loglog(f[f > 0], psd[f > 0],
                      color=ST.color_for_sim(sim),
                      lw=1.6 if sim == obs else 1.0,
                      alpha=0.95 if sim == obs else 0.7,
                      label=ST.gcm_of(sim) if vi == 0 else None)
            sample_sizes[f"{sim}|{var}|spectra|n_days"] = int(anom.size)
        # Mark synoptic and intraseasonal bands as period -> frequency = 1/period
        for f_lo_p, f_hi_p, name in ((1 / 7, 1 / 3, "synoptic 3-7 d"),
                                      (1 / 60, 1 / 20, "intraseasonal 20-60 d")):
            ax.axvspan(f_lo_p, f_hi_p, color="#ddd", alpha=0.4, lw=0)
            ax.text(np.sqrt(f_lo_p * f_hi_p), ax.get_ylim()[1], name,
                    ha="center", va="top", fontsize=6, color="#666")
        ax.set_xlabel("Frequency (cycles day$^{-1}$)")
        if vi == 0:
            ax.set_ylabel("Welch PSD (variance · day)")
        ax.set_title(f"Spectrum — {var}", fontsize=10)
        ax.grid(alpha=0.3, which="both")

    fig.tight_layout(rect=(0, 0.02, 1, 1 - 0.9 / fig.get_figheight()))
    sub = (f"AR(1) over season-stratified daily series. Spectra: Welch ({nperseg}-d segments) "
           f"on daily anomalies (DOY clim removed, linearly detrended). "
           f"Basin = {basin}. Obs window = {h_lo}-{h_hi}; GCM window = {fl_lo}-{fl_hi}. "
           f"Gray bands = synoptic (3-7 d) and intra-seasonal (20-60 d).")
    ST.apply_labels(
        fig, fig_number="05",
        question=("Do downscaled GCMs reproduce daily persistence and the "
                  "spectral variance distribution of observations?"),
        sub_caption=sub,
    )
    out_path = out_dir / "05_ar1_spectra.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="05_ar1_spectra",
        sims=[obs] + sims_future,
        periods={"obs_H": [h_lo, h_hi], "gcm_F_late": [fl_lo, fl_hi]},
        sample_sizes=sample_sizes,
        notes=(f"AR(1) bars (top) over four seasons. Welch PSD (bottom) on detrended "
               f"DOY-anomaly series, nperseg={nperseg}. Anomaly = remove 31-d-smoothed "
               f"DOY climatology, then linear detrend."),
    )
    log.info("wrote %s", out_path)


def fig_06_snow_and_trend(parquets, cfg, out_dir: Path) -> None:
    """Fig 06 — Spatial fingerprint of climate change across the 33 DRB basins.

    Two rows of small-multiple maps over the 33 Pywr-DRB sub-basins:
      Row 1 — Snow fraction (annual prcp on tmean<=0°C days / annual prcp).
              Three columns per GCM: H, F-late, F-late minus H.
      Row 2 — Sen-slope trend on annual-total prcp 2015-2099, per GCM. Stippled
              where Mann-Kendall p<0.05 after Benjamini-Hochberg FDR correction
              across the 33 basins.

    Uses geopandas to render the existing node_basin_geometries.shp.
    """
    import geopandas as gpd

    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")
    f_full_lo, f_full_hi = 2015, 2099
    snow_thresh = float(diag.get("snow_tmean_threshold_C", 0.0))
    trend_alpha = float(diag.get("trend_alpha", 0.05))

    sims_future = _gcm_sims(parquets)
    if not sims_future:
        log.warning("fig_06: no future GCM sims, skipping")
        return

    # Load shapefile via cmip6_drb config-relative path
    shp = Path(cfg["paths"]["shapefile"])
    if not shp.is_absolute():
        shp = (Path(cfg.paths.repo_root) if hasattr(cfg, "paths") and hasattr(cfg.paths, "repo_root")
               else Path(__file__).resolve().parents[2]) / shp
    if not shp.exists():
        log.warning("fig_06: shapefile not found at %s, skipping", shp)
        return
    gdf = gpd.read_file(shp).to_crs(cfg.get("target_crs", "EPSG:4326"))
    # Identify the basin-name column. Check candidates.
    name_col = None
    for cand in ("name", "node", "node_id", "NAME", "Node", "STAID", "GAGE_ID"):
        if cand in gdf.columns:
            name_col = cand
            break
    if name_col is None:
        # Fallback: take the first string-typed column
        for col in gdf.columns:
            if gdf[col].dtype == object:
                name_col = col
                break
    if name_col is None:
        log.warning("fig_06: cannot find basin-name column on shapefile, skipping")
        return

    def _annual_snow_fraction(prcp_df, tmean_df) -> pd.Series:
        """Per-basin: sum of prcp on snow days / sum of prcp, averaged over the
        years in the slice. Returns Series indexed by basin name."""
        common = sorted(set(prcp_df.columns) & set(tmean_df.columns))
        prcp = prcp_df[common]
        tmean = tmean_df[common]
        snow_mask = (tmean.values <= snow_thresh)
        snow_pr = np.where(snow_mask, prcp.values, 0.0)
        ann_snow = pd.DataFrame(snow_pr, index=prcp.index, columns=common).groupby(prcp.index.year).sum()
        ann_total = prcp.groupby(prcp.index.year).sum()
        frac = (ann_snow / ann_total.where(ann_total > 0, np.nan)).mean(axis=0)
        return frac

    def _ann_total_prcp_table(sim) -> pd.DataFrame | None:
        """Per-basin annual total prcp series, F-full 2015-2099. Rows=year, cols=basin."""
        df = _load_all_basins(parquets, sim, "prcp", f_full_lo, f_full_hi)
        if df is None:
            return None
        return df.groupby(df.index.year).sum()

    n_gcm = len(sims_future)
    fig = plt.figure(figsize=(3.0 * n_gcm + 1.0, 8.0))
    gs = fig.add_gridspec(2, n_gcm * 3, hspace=0.18, wspace=0.04)
    sample_sizes: dict[str, int] = {}

    # ---- Row 1: snow fraction H, F-late, change ----
    # Compute obs H snow fraction once (Daymet for both prcp + tmax/tmin)
    obs_pr = _load_all_basins(parquets, obs, "prcp", h_lo, h_hi)
    obs_tx = _load_all_basins(parquets, obs, "tmax", h_lo, h_hi)
    obs_tn = _load_all_basins(parquets, obs, "tmin", h_lo, h_hi)
    if obs_pr is None or obs_tx is None or obs_tn is None:
        log.warning("fig_06: missing obs prcp/tmax/tmin, skipping")
        return
    common_basins_obs = sorted(set(obs_pr.columns) & set(obs_tx.columns) & set(obs_tn.columns))
    tmean_obs = ((obs_tx[common_basins_obs] + obs_tn[common_basins_obs]) / 2.0)
    snow_obs = _annual_snow_fraction(obs_pr[common_basins_obs], tmean_obs)
    sample_sizes[f"{obs}|snow|H"] = int(len(snow_obs))

    # Determine global snow color range using all sims so panels are comparable
    all_snow_vals = list(snow_obs.dropna().values)
    snow_panels: list[tuple[str, str, pd.Series]] = []  # (sim, label, series)
    for sim in sims_future:
        sim_pr_h = obs_pr  # H = obs reference; using same baseline for all GCMs
        snow_h = snow_obs
        # F-late uses GCM's own prcp + (tmax,tmin); these only exist post-2015
        sim_pr = _load_all_basins(parquets, sim, "prcp", fl_lo, fl_hi)
        sim_tx = _load_all_basins(parquets, sim, "tmax", fl_lo, fl_hi)
        sim_tn = _load_all_basins(parquets, sim, "tmin", fl_lo, fl_hi)
        if sim_pr is None or sim_tx is None or sim_tn is None:
            continue
        common = sorted(set(sim_pr.columns) & set(sim_tx.columns) & set(sim_tn.columns))
        tmean_f = (sim_tx[common] + sim_tn[common]) / 2.0
        snow_f = _annual_snow_fraction(sim_pr[common], tmean_f)
        snow_panels.append((sim, "H", snow_h))
        snow_panels.append((sim, "F-late", snow_f))
        snow_panels.append((sim, "Δ", (snow_f - snow_h)))
        all_snow_vals.extend(snow_f.dropna().values.tolist())

    if not snow_panels:
        log.warning("fig_06: no GCM snow panels could be built, skipping")
        return
    snow_vmax = float(np.nanmax(all_snow_vals))
    snow_vmin = 0.0
    diff_panels = [s for sim, lab, s in snow_panels if lab == "Δ"]
    diff_max = float(np.nanmax([np.nanmax(np.abs(p.values)) for p in diff_panels])) if diff_panels else 0.1

    # Place row-1 panels: per GCM block of 3 cols
    cmap_snow = plt.get_cmap("Blues")
    cmap_diff = plt.get_cmap("RdBu_r")

    for gi, sim in enumerate(sims_future):
        triple = [(s_sim, lab, ser) for s_sim, lab, ser in snow_panels if s_sim == sim]
        for li, (_, lab, ser) in enumerate(triple):
            ax = fig.add_subplot(gs[0, gi * 3 + li])
            data = gdf.copy()
            data["val"] = data[name_col].map(lambda n: ser.get(n, np.nan))
            if lab == "Δ":
                data.plot(column="val", cmap=cmap_diff, ax=ax, edgecolor="white", linewidth=0.3,
                          vmin=-diff_max, vmax=diff_max,
                          missing_kwds={"color": "#eee"})
            else:
                data.plot(column="val", cmap=cmap_snow, ax=ax, edgecolor="white", linewidth=0.3,
                          vmin=snow_vmin, vmax=snow_vmax,
                          missing_kwds={"color": "#eee"})
            ax.set_axis_off()
            if li == 0:
                ax.set_title(f"{ST.gcm_of(sim)}\n{lab}", fontsize=8)
            else:
                ax.set_title(lab, fontsize=8)
            if gi == 0 and li == 0:
                ax.text(-0.10, 0.5, "Snow fraction", transform=ax.transAxes,
                        rotation=90, ha="center", va="center", fontsize=10,
                        fontweight="bold")

    # Row-1 colorbars
    sm_snow = plt.cm.ScalarMappable(cmap=cmap_snow,
                                     norm=plt.Normalize(snow_vmin, snow_vmax))
    sm_diff = plt.cm.ScalarMappable(cmap=cmap_diff,
                                     norm=plt.Normalize(-diff_max, diff_max))
    cbar_snow_ax = fig.add_axes([0.92, 0.55, 0.012, 0.32])
    cbar_diff_ax = fig.add_axes([0.96, 0.55, 0.012, 0.32])
    fig.colorbar(sm_snow, cax=cbar_snow_ax, label="Snow fraction (frac of annual prcp on tmean≤0°C days)")
    fig.colorbar(sm_diff, cax=cbar_diff_ax, label="Δ snow frac (F-late − H)")

    # ---- Row 2: per-basin Mann-Kendall on annual prcp 2015-2099 ----
    sen_slope_max = 0.0
    sen_panels: list[tuple[str, pd.Series, np.ndarray]] = []  # (sim, slopes_series, sig_mask_array)
    for sim in sims_future:
        ann = _ann_total_prcp_table(sim)
        if ann is None:
            continue
        slopes = pd.Series(index=ann.columns, dtype=float)
        ps = pd.Series(index=ann.columns, dtype=float)
        for basin_col in ann.columns:
            res = D.mann_kendall(ann[basin_col].values)
            slopes[basin_col] = res["sen_slope"] * 10  # mm/yr per decade
            ps[basin_col] = res["p"]
        sig_mask = D.bh_fdr(ps.values, alpha=trend_alpha)
        sen_panels.append((sim, slopes, sig_mask))
        sen_slope_max = max(sen_slope_max, float(np.nanmax(np.abs(slopes.values))))
        sample_sizes[f"{sim}|MK_sig_basins"] = int(sig_mask.sum())

    cmap_sen = plt.get_cmap("BrBG")
    for gi, (sim, slopes, sig_mask) in enumerate(sen_panels):
        ax = fig.add_subplot(gs[1, gi * 3:(gi + 1) * 3])
        data = gdf.copy()
        data["val"] = data[name_col].map(lambda n: slopes.get(n, np.nan))
        data["sig"] = data[name_col].map(
            lambda n: bool(sig_mask[list(slopes.index).index(n)])
            if n in slopes.index else False
        )
        data.plot(column="val", cmap=cmap_sen, ax=ax, edgecolor="white", linewidth=0.3,
                  vmin=-sen_slope_max, vmax=sen_slope_max,
                  missing_kwds={"color": "#eee"})
        # Stipple the significant basins by overlaying a hatched layer
        sig_data = data[data["sig"]]
        if not sig_data.empty:
            sig_data.plot(ax=ax, facecolor="none", edgecolor="black",
                          hatch="...", linewidth=0.4)
        ax.set_axis_off()
        n_sig = int(sig_mask.sum())
        ax.set_title(f"{ST.gcm_of(sim)} — {n_sig}/{len(slopes)} basins sig.",
                     fontsize=9)
        if gi == 0:
            ax.text(-0.05, 0.5, "Annual prcp Sen slope\n(F_full 2015–2099)",
                    transform=ax.transAxes, rotation=90, ha="center",
                    va="center", fontsize=10, fontweight="bold")

    sm_sen = plt.cm.ScalarMappable(cmap=cmap_sen,
                                    norm=plt.Normalize(-sen_slope_max, sen_slope_max))
    cbar_sen_ax = fig.add_axes([0.92, 0.10, 0.012, 0.32])
    fig.colorbar(sm_sen, cax=cbar_sen_ax, label="Annual prcp Sen slope (mm yr$^{-1}$ per decade)")

    sub = (f"Row 1: snow fraction = annual sum of prcp on days with tmean=(tmax+tmin)/2 ≤ "
           f"{snow_thresh:g}°C, divided by annual prcp. H = {h_lo}-{h_hi} ({obs}); "
           f"F-late = {fl_lo}-{fl_hi} (per GCM). "
           f"Row 2: Sen-slope on annual total prcp over {f_full_lo}-{f_full_hi} per GCM. "
           f"Hatching = Mann-Kendall p<{trend_alpha:g} after Benjamini-Hochberg FDR (n=33).")
    ST.apply_labels(
        fig, fig_number="06",
        question=("Where in the basin does the climate-change fingerprint show up "
                  "most strongly — snowfall fraction and prcp trend?"),
        sub_caption=sub,
    )
    out_path = out_dir / "06_snow_and_trend_maps.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="06_snow_and_trend_maps",
        sims=[obs] + sims_future,
        periods={"H": [h_lo, h_hi], "F_late": [fl_lo, fl_hi],
                 "F_full": [f_full_lo, f_full_hi]},
        sample_sizes=sample_sizes,
        notes=(f"Per-basin snow fraction (H, F-late, Δ) maps + per-basin Mann-Kendall "
               f"Sen slope on annual total prcp with BH-FDR significance stippling. "
               f"Snow threshold = {snow_thresh:g}°C tmean."),
    )
    log.info("wrote %s", out_path)


def fig_07_compound_hot_dry(parquets, cfg, out_dir: Path) -> None:
    """Fig 07 — Joint hot-dry behavior: density and event counts.

    Left: 2D hexbin of (Tmax DOY anomaly, prcp) for each simulation. Reveals
    the joint distribution structure that bias-correction does NOT reshape.

    Right: Annual count of "hot-dry compound days" (Tmax > P90(DOY) AND
    prcp < P10(DOY) using a 30-day moving DOY window for percentiles).
    Time-series 1980-2099, GCMs joining at 2015. Draws out the projected
    intensification of compound dry-warm summer events.
    """
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    basin = diag["nodes_focus"][0]
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")

    sims_future = _gcm_sims(parquets)
    if not sims_future:
        log.warning("fig_07: no future GCM sims, skipping")
        return
    if (obs, "tmax") not in parquets or (obs, "prcp") not in parquets:
        log.warning("fig_07: missing obs tmax or prcp, skipping")
        return

    # n columns of hexbin = obs + each GCM (so we can compare side by side)
    n_panels = 1 + len(sims_future)
    fig = plt.figure(figsize=(2.6 * n_panels, 6.5))
    gs = fig.add_gridspec(2, n_panels, height_ratios=[1.6, 1.0],
                          hspace=0.35, wspace=0.20)
    sample_sizes: dict[str, int] = {}

    # ---- Top row: 2D hexbin of (Tmax anomaly, prcp) ----
    # Use F-late for GCMs, H for obs.
    panel_specs: list[tuple[str, int, int, str]] = [(obs, h_lo, h_hi, "H")]
    panel_specs.extend((sim, fl_lo, fl_hi, "F-late") for sim in sims_future)

    # Determine common axes by pre-loading
    all_anom_t = []
    all_p = []
    panel_data = []
    for sim, lo, hi, lab in panel_specs:
        s_t = _load_basin_series(parquets, sim, "tmax", basin, lo, hi)
        s_p = _load_basin_series(parquets, sim, "prcp", basin, lo, hi)
        if s_t is None or s_p is None:
            panel_data.append(None)
            continue
        anom_t = D.doy_anomaly(s_t)
        df = pd.DataFrame({"a": anom_t, "p": s_p}).dropna()
        panel_data.append((sim, lab, df))
        all_anom_t.extend(df["a"].values)
        all_p.extend(df["p"].values)
        sample_sizes[f"{sim}|{lab}|hexbin_n"] = int(len(df))
    if not all_anom_t:
        log.warning("fig_07: no hexbin data, skipping")
        return
    a_lo = float(np.quantile(all_anom_t, 0.005))
    a_hi = float(np.quantile(all_anom_t, 0.995))
    p_hi = float(np.quantile(all_p, 0.995))

    for ci, (sim, lab, df) in enumerate(d for d in panel_data if d is not None):
        ax = fig.add_subplot(gs[0, ci])
        hb = ax.hexbin(df["a"], df["p"], gridsize=30, mincnt=1,
                       extent=(a_lo, a_hi, 0, p_hi),
                       cmap="viridis",
                       norm=plt.matplotlib.colors.LogNorm(vmin=1))
        ax.set_xlim(a_lo, a_hi)
        ax.set_ylim(0, p_hi)
        ax.set_title(f"{ST.gcm_of(sim)} · {lab}\n(n={len(df):,})", fontsize=8)
        if ci == 0:
            ax.set_ylabel("Daily prcp (mm day$^{-1}$)")
        ax.set_xlabel("Tmax anomaly ($^\\circ$C)")
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)

    cbar_ax = fig.add_axes([0.93, 0.55, 0.012, 0.32])
    fig.colorbar(hb, cax=cbar_ax, label="Day count (log)")

    # ---- Bottom row: annual count of compound hot-dry days, single wide panel ----
    ax_ts = fig.add_subplot(gs[1, :])

    # Build per-DOY P90(Tmax) from Daymet H using a 30-day window.
    # Dry day defined as prcp < dry_thresh (mm) — using P10 of prcp would be ~0
    # because most days are dry, so a fixed mm threshold is more meaningful.
    dry_thresh_mm = 1.0
    s_t_obs_H = _load_basin_series(parquets, obs, "tmax", basin, h_lo, h_hi)
    s_p_obs_H = _load_basin_series(parquets, obs, "prcp", basin, h_lo, h_hi)
    if s_t_obs_H is None or s_p_obs_H is None:
        log.warning("fig_07: cannot build DOY thresholds, skipping bottom panel")
    else:
        df_obs = pd.DataFrame({"t": s_t_obs_H, "p": s_p_obs_H}).dropna()
        doy = df_obs.index.dayofyear.values
        thresh_t = np.full(367, np.nan)
        win = 15
        for d in range(1, 367):
            offsets = np.arange(d - win, d + win + 1)
            offsets = ((offsets - 1) % 366) + 1
            mask = np.isin(doy, offsets)
            if mask.sum() < 30:
                continue
            thresh_t[d] = np.quantile(df_obs["t"].values[mask], 0.90)

        def _count_hd(s_t, s_p):
            df = pd.DataFrame({"t": s_t, "p": s_p}).dropna()
            df_doy = df.index.dayofyear.values
            tt = thresh_t[df_doy]
            hd_mask = (df["t"].values > tt) & (df["p"].values < dry_thresh_mm)
            ann = pd.Series(hd_mask.astype(int), index=df.index).groupby(df.index.year).sum()
            return ann

        # Obs full record
        obs_full_lo, obs_full_hi = h_lo, h_hi
        s_t = _load_basin_series(parquets, obs, "tmax", basin, obs_full_lo, obs_full_hi)
        s_p = _load_basin_series(parquets, obs, "prcp", basin, obs_full_lo, obs_full_hi)
        if s_t is not None and s_p is not None:
            ann_obs = _count_hd(s_t, s_p)
            ax_ts.plot(ann_obs.index, ann_obs.values, color="#000",
                       lw=1.8, marker="o", ms=3, alpha=0.95,
                       label=f"{obs} obs ({ann_obs.size} yr)")
            sample_sizes[f"{obs}|hot_dry|years"] = int(ann_obs.size)

        # Each GCM, full F record (2015-2099)
        for sim in sims_future:
            s_t = _load_basin_series(parquets, sim, "tmax", basin, 2015, 2099)
            s_p = _load_basin_series(parquets, sim, "prcp", basin, 2015, 2099)
            if s_t is None or s_p is None:
                continue
            ann = _count_hd(s_t, s_p)
            ax_ts.plot(ann.index, ann.values, color=ST.color_for_sim(sim),
                       lw=1.0, alpha=0.7, label=ST.gcm_of(sim))
            sample_sizes[f"{sim}|hot_dry|years"] = int(ann.size)

        ax_ts.axvline(2014.5, color="#888", ls=":", lw=1)
        ax_ts.set_xlabel("Year")
        ax_ts.set_ylabel("Hot-dry days / year")
        ax_ts.set_title(f"Annual count of compound hot-dry days "
                        f"(Tmax > DOY-P90 AND prcp < DOY-P10) @ {basin}",
                        fontsize=10)
        ax_ts.grid(alpha=0.3)
        ax_ts.legend(frameon=False, fontsize=7, ncol=2, loc="upper left")

    fig.tight_layout(rect=(0, 0.02, 0.91, 1 - 0.9 / fig.get_figheight()))
    sub = (f"Top: 2D hexbin of (Tmax DOY-anomaly, daily prcp) at {basin}. "
           f"H = {h_lo}-{h_hi} ({obs}); F-late = {fl_lo}-{fl_hi} (per GCM, SSP585). "
           f"Bottom: annual hot-dry day count, DOY-P90(Tmax) threshold from {obs} H "
           f"(±15-day window) AND prcp < 1 mm/day basin-mean.")
    ST.apply_labels(
        fig, fig_number="07",
        question=("How does the joint distribution of warm and dry conditions "
                  "shift in the late 21st century, and how often do compound hot-dry "
                  "days occur?"),
        sub_caption=sub,
    )
    out_path = out_dir / "07_compound_hot_dry.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="07_compound_hot_dry",
        sims=[obs] + sims_future,
        periods={"H": [h_lo, h_hi], "F_late": [fl_lo, fl_hi], "F_full": [2015, 2099]},
        sample_sizes=sample_sizes,
        notes=(f"Hexbin (Tmax-anom, prcp). Compound hot-dry day = Tmax > DOY-P90 "
               f"AND prcp < DOY-P10 with ±15 d window. Thresholds from obs-H."),
    )
    log.info("wrote %s", out_path)


def fig_08_cross_obs(parquets, cfg, out_dir: Path) -> None:
    """Fig 08 — How much do the two reference observational datasets disagree?

    Q–Q comparison of DaymetV4 vs Livneh on the H_obs_full window (1980-2018),
    by season, for each focus variable. One thin curve per basin (33 lines)
    plus a heavy black basin-mean overlay. Quantifies the irreducible
    observational uncertainty floor against which model biases are judged.
    """
    diag = cfg["diagnostics"]
    obs_a = diag["reference_obs"]
    obs_b = diag["obs_secondary"]
    variables = list(diag["variables"])
    yr0, yr1 = _period(cfg, "H_obs_full")

    needed = [(obs_a, v) for v in variables] + [(obs_b, v) for v in variables]
    missing = [k for k in needed if k not in parquets]
    if missing:
        log.warning("fig_08: missing parquets %s, skipping", missing)
        return

    seasons = D.SEASONS
    n_rows = len(variables)
    n_cols = len(seasons)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(2.6 * n_cols, 2.4 * n_rows),
                             squeeze=False, sharex=False, sharey=False)
    sample_sizes: dict[str, int] = {}

    qs = np.linspace(0.005, 0.995, 80)  # quantile probabilities

    for r, var in enumerate(variables):
        df_a = drb_io.read_parquet(parquets[(obs_a, var)])
        df_b = drb_io.read_parquet(parquets[(obs_b, var)])
        df_a = D.slice_period(df_a, yr0, yr1)
        df_b = D.slice_period(df_b, yr0, yr1)
        common_basins = sorted(set(df_a.columns) & set(df_b.columns))
        sample_sizes[f"{obs_a}|{var}"] = int(df_a.shape[0])
        sample_sizes[f"{obs_b}|{var}"] = int(df_b.shape[0])

        for c, season in enumerate(seasons):
            ax = axes[r][c]
            mask_a = D.season_mask(df_a.index, season)
            mask_b = D.season_mask(df_b.index, season)
            sub_a = df_a.loc[mask_a]
            sub_b = df_b.loc[mask_b]

            # Per-basin Q-Q (one thin gray curve each)
            for basin in common_basins:
                a = sub_a[basin].dropna().values
                b = sub_b[basin].dropna().values
                if a.size < 30 or b.size < 30:
                    continue
                qa = np.quantile(a, qs)
                qb = np.quantile(b, qs)
                ax.plot(qa, qb, color="#bbbbbb", lw=0.4, alpha=0.6)

            # Basin-mean overlay (heavy black)
            a_mean = sub_a[common_basins].mean(axis=1).dropna().values
            b_mean = sub_b[common_basins].mean(axis=1).dropna().values
            qa_m = np.quantile(a_mean, qs)
            qb_m = np.quantile(b_mean, qs)
            ax.plot(qa_m, qb_m, color="#000000", lw=1.6,
                    label=f"DRB-mean (33 basins)")

            # 1:1 reference line
            lim_lo = min(qa_m.min(), qb_m.min())
            lim_hi = max(qa_m.max(), qb_m.max())
            ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], color="#d62728",
                    ls="--", lw=0.9, label="1:1 (no obs disagreement)")

            ax.set_title(f"{season} · {var}", fontsize=9)
            if r == n_rows - 1:
                ax.set_xlabel(f"{obs_a} quantile  [{ST.VAR_UNITS.get(var, '')}]", fontsize=8)
            if c == 0:
                ax.set_ylabel(f"{obs_b} quantile  [{ST.VAR_UNITS.get(var, '')}]", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.3)
            if var == "prcp":
                # Heavy upper tail; log-log helps but only if positive.
                ax.set_xscale("symlog", linthresh=1.0)
                ax.set_yscale("symlog", linthresh=1.0)

            if r == 0 and c == 0:
                ax.legend(frameon=False, fontsize=7, loc="upper left")

    fig.tight_layout(rect=(0, 0.01, 1, 0.95))
    n_basins = len(common_basins)
    sub = (f"{obs_a} vs {obs_b}, basin-aggregated daily data, {yr0}–{yr1}. "
           f"Thin gray = each of {n_basins} basins; heavy black = DRB-mean. "
           f"Departures from the 1:1 line indicate cross-obs disagreement.")
    ST.apply_labels(
        fig,
        fig_number="08",
        question=("Where do the two reference observation datasets disagree? "
                  "Per-quantile Q–Q comparison, by season."),
        sub_caption=sub,
    )

    out_path = out_dir / "08_cross_obs_qq.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="08_cross_obs_qq",
        sims=[obs_a, obs_b],
        periods={"H_obs_full": [yr0, yr1]},
        sample_sizes=sample_sizes,
        notes=("Per-basin Q-Q for each (var, season) over the Daymet∩Livneh overlap. "
               "Heavy black is the 33-basin-mean Q-Q. prcp axes use symlog (linthresh=1)."),
    )
    log.info("wrote %s", out_path)


def fig_09_handoff_continuity(parquets, cfg, out_dir: Path) -> None:
    """Fig 09 — Do the historical-obs and downscaled-future series glue together
    cleanly across the 2014/2015 boundary?

    Three panels (annual, monthly, distribution) over the bias-correction
    handoff window. Stair-step or distribution offset would indicate a
    BC artifact that downstream users would inherit.
    """
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    basin = diag["nodes_focus"][0]  # cannonsville
    sims_future = _gcm_sims(parquets)
    if not sims_future:
        log.warning("fig_09: no future GCM sims, skipping")
        return
    # Check obs has prcp+tmax
    for v in ("prcp", "tmax"):
        if (obs, v) not in parquets:
            log.warning("fig_09: missing %s|%s, skipping", obs, v)
            return

    # Window: span the handoff. Use 2010-2025 for time-series + the HO window for distribution.
    win_lo, win_hi = 2010, 2025
    ho_lo, ho_hi = _period(cfg, "HO")

    fig = plt.figure(figsize=(13, 9))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.0, 1.0], hspace=0.45, wspace=0.25)
    ax_a_p = fig.add_subplot(gs[0, 0])  # annual prcp ts
    ax_a_t = fig.add_subplot(gs[0, 1])  # annual tmax ts
    ax_b_p = fig.add_subplot(gs[1, 0])  # monthly clim prcp HO
    ax_b_t = fig.add_subplot(gs[1, 1])  # monthly clim tmax HO
    ax_c_p = fig.add_subplot(gs[2, 0])  # daily anom KDE prcp HO
    ax_c_t = fig.add_subplot(gs[2, 1])  # daily anom KDE tmax HO

    sample_sizes: dict[str, int] = {}

    # ---- (a) annual time series, 2010-2025 ----
    for ax, var, ylabel in ((ax_a_p, "prcp", "Annual total prcp (mm)"),
                            (ax_a_t, "tmax", "Annual mean Tmax ($^\\circ$C)")):
        # Daymet
        s_obs = _load_basin_series(parquets, obs, var, basin, win_lo, win_hi)
        if s_obs is not None:
            if var == "prcp":
                ann = s_obs.groupby(s_obs.index.year).sum()
            else:
                ann = s_obs.groupby(s_obs.index.year).mean()
            ax.plot(ann.index, ann.values, color="#222", lw=1.8, marker="o",
                    markersize=4, label=f"{obs} obs", zorder=5)
            sample_sizes[f"{obs}|{var}|annual"] = int(ann.size)
        # Each GCM
        for sim in sims_future:
            s = _load_basin_series(parquets, sim, var, basin, win_lo, win_hi)
            if s is None:
                continue
            if var == "prcp":
                ann = s.groupby(s.index.year).sum()
            else:
                ann = s.groupby(s.index.year).mean()
            ax.plot(ann.index, ann.values, lw=0.9, alpha=0.7,
                    color=ST.color_for_sim(sim), label=ST.gcm_of(sim))
            sample_sizes[f"{sim}|{var}|annual"] = int(ann.size)
        ax.axvline(2014.5, color="#888", ls=":", lw=1.0)
        ax.text(2014.6, ax.get_ylim()[1], " BC handoff →", fontsize=7, color="#666",
                va="top")
        ax.set_xlabel("Year")
        ax.set_ylabel(ylabel)
        ax.set_title(f"(a) Annual time series — {var} @ {basin}", fontsize=10)
        ax.grid(alpha=0.3)
        if var == "prcp":
            ax.legend(frameon=False, fontsize=7, loc="best", ncol=2)

    # ---- (b) monthly climatology over HO window ----
    for ax, var, ylabel in ((ax_b_p, "prcp", "Mean monthly prcp (mm/month)"),
                            (ax_b_t, "tmax", "Mean monthly Tmax ($^\\circ$C)")):
        # Daymet HO climatology
        s_obs = _load_basin_series(parquets, obs, var, basin, ho_lo, ho_hi)
        if s_obs is not None:
            if var == "prcp":
                mclim = s_obs.groupby(s_obs.index.month).sum() / max(1, s_obs.index.year.nunique())
            else:
                mclim = s_obs.groupby(s_obs.index.month).mean()
            ax.plot(mclim.index, mclim.values, color="#222", lw=2.0, marker="o",
                    markersize=4, label=f"{obs} obs", zorder=5)
        for sim in sims_future:
            s = _load_basin_series(parquets, sim, var, basin, ho_lo, ho_hi)
            if s is None:
                continue
            if var == "prcp":
                mclim = s.groupby(s.index.month).sum() / max(1, s.index.year.nunique())
            else:
                mclim = s.groupby(s.index.month).mean()
            ax.plot(mclim.index, mclim.values, lw=1.0, alpha=0.7,
                    color=ST.color_for_sim(sim), marker="s", markersize=3,
                    label=ST.gcm_of(sim))
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
        ax.set_xlabel("Month")
        ax.set_ylabel(ylabel)
        ax.set_title(f"(b) Monthly climatology over HO {ho_lo}-{ho_hi} — {var} @ {basin}",
                     fontsize=10)
        ax.grid(alpha=0.3)

    # ---- (c) daily anomaly KDE over HO window ----
    from scipy.stats import gaussian_kde
    for ax, var, xlabel in ((ax_c_p, "prcp", "Daily prcp anomaly (mm/day)"),
                            (ax_c_t, "tmax", "Daily Tmax anomaly ($^\\circ$C)")):
        s_obs = _load_basin_series(parquets, obs, var, basin, ho_lo, ho_hi)
        if s_obs is None:
            continue
        anom_obs = D.doy_anomaly(s_obs).dropna().values
        if anom_obs.size > 30:
            xs = np.linspace(np.quantile(anom_obs, 0.005),
                             np.quantile(anom_obs, 0.995), 200)
            kde = gaussian_kde(anom_obs)
            ax.fill_between(xs, kde(xs), color="#222", alpha=0.18,
                            label=f"{obs} obs ({anom_obs.size} d)")
            ax.plot(xs, kde(xs), color="#222", lw=1.6)
        for sim in sims_future:
            s = _load_basin_series(parquets, sim, var, basin, ho_lo, ho_hi)
            if s is None:
                continue
            anom = D.doy_anomaly(s).dropna().values
            if anom.size < 30:
                continue
            xs = np.linspace(np.quantile(anom, 0.005), np.quantile(anom, 0.995), 200)
            kde = gaussian_kde(anom)
            ax.plot(xs, kde(xs), lw=1.1, alpha=0.85,
                    color=ST.color_for_sim(sim), label=ST.gcm_of(sim))
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Density")
        ax.set_title(f"(c) HO-window daily anomaly KDE — {var} @ {basin}", fontsize=10)
        ax.grid(alpha=0.3)
        if var == "prcp":
            ax.legend(frameon=False, fontsize=7, loc="best")

    fig.tight_layout(rect=(0, 0.01, 1, 0.94))
    sub = (f"Window 2010–2025 for (a); HO = {ho_lo}–{ho_hi} for (b)/(c). "
           f"Basin = {basin}. Vertical dotted line marks the {obs}→GCM-future handoff. "
           f"Visible jumps would indicate a BC artifact carried into projections.")
    ST.apply_labels(
        fig,
        fig_number="09",
        question="Do historical observations and downscaled GCM futures glue together cleanly at 2015?",
        sub_caption=sub,
    )
    out_path = out_dir / "09_handoff_continuity.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="09_handoff_continuity",
        sims=[obs] + sims_future,
        periods={"window_a": [win_lo, win_hi], "HO": [ho_lo, ho_hi]},
        sample_sizes=sample_sizes,
        notes=(f"Three-panel BC-handoff QC at basin {basin}: (a) annual time series, "
               f"(b) HO-window monthly climatology, (c) HO-window daily-anomaly KDE."),
    )
    log.info("wrote %s", out_path)


def fig_10_wasserstein_cluster(parquets, cfg, out_dir: Path) -> None:
    """Fig 10 — Which simulations cluster together, and where do obs sit?

    Per variable: pairwise 1-Wasserstein distance between standardized daily
    anomalies (DOY clim + linear trend removed) for every simulation in the
    ensemble. Hierarchical clustering (Ward linkage) reorders the matrix so
    that similar simulations sit adjacent.

    Reveals (a) whether bias-corrected GCMs have collapsed onto the obs
    distribution as expected, (b) which GCM is the structural outlier, and
    (c) how F-late projections move models away from each other.
    """
    from scipy.cluster.hierarchy import linkage, leaves_list
    diag = cfg["diagnostics"]
    obs = diag["reference_obs"]
    obs_b = diag["obs_secondary"]
    variables = list(diag["variables"])
    basin = diag["nodes_focus"][0]
    h_lo, h_hi = _period(cfg, "H")
    fl_lo, fl_hi = _period(cfg, "F_late")
    h_obs_lo, h_obs_hi = _period(cfg, "H_obs_full")

    sims_future = _gcm_sims(parquets)

    n_cols = 2
    n_rows = (len(variables) + 1) // 2
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5.0 * n_cols, 4.5 * n_rows),
                             squeeze=False)
    sample_sizes: dict[str, int] = {}

    for vi, var in enumerate(variables):
        ax = axes[vi // n_cols][vi % n_cols]
        # Build samples: standardized anomalies of each (sim, period) series.
        samples: dict[str, np.ndarray] = {}
        # Obs
        for o, lo, hi in ((obs, h_lo, h_hi), (obs_b, h_obs_lo, h_obs_hi)):
            s = _load_basin_series(parquets, o, var, basin, lo, hi)
            if s is None:
                continue
            samples[f"{o}\nH"] = D.standardized_anomaly(s).dropna().values
        # Per-GCM F-late
        for sim in sims_future:
            s = _load_basin_series(parquets, sim, var, basin, fl_lo, fl_hi)
            if s is None:
                continue
            samples[f"{ST.gcm_of(sim)}\nF-late"] = D.standardized_anomaly(s).dropna().values

        if len(samples) < 3:
            ax.set_visible(False)
            continue

        labels, D_mat = D.pairwise_wasserstein(samples)
        # Hierarchical clustering on a condensed matrix
        from scipy.spatial.distance import squareform
        cond = squareform(D_mat, checks=False)
        Z = linkage(cond, method="ward")
        order = leaves_list(Z)
        labels_o = [labels[i] for i in order]
        D_o = D_mat[np.ix_(order, order)]

        im = ax.imshow(D_o, cmap="magma_r", aspect="equal")
        ax.set_xticks(range(len(labels_o)))
        ax.set_yticks(range(len(labels_o)))
        ax.set_xticklabels(labels_o, rotation=45, ha="right", fontsize=7)
        ax.set_yticklabels(labels_o, fontsize=7)
        # Numeric annotations
        for i in range(len(labels_o)):
            for j in range(len(labels_o)):
                ax.text(j, i, f"{D_o[i, j]:.2f}", ha="center", va="center",
                        fontsize=6,
                        color="white" if D_o[i, j] > D_o.max() * 0.5 else "black")
        ax.set_title(f"{var}", fontsize=10)
        cbar = fig.colorbar(im, ax=ax, fraction=0.045)
        cbar.set_label("1-Wasserstein distance\n(standardized daily anomalies)",
                       fontsize=7)
        for k, v in samples.items():
            sample_sizes[f"{var}|{k.replace(chr(10),'/')}|n_days"] = int(len(v))

    # Hide unused axis if odd number of variables
    for i in range(len(variables), n_rows * n_cols):
        axes[i // n_cols][i % n_cols].set_visible(False)

    fig.tight_layout(rect=(0, 0.02, 1, 1 - 0.9 / fig.get_figheight()))
    sub = (f"Pairwise 1-Wasserstein distance between standardized daily anomalies "
           f"(DOY climatology removed, divided by DOY std). Obs windows: "
           f"{obs} {h_lo}-{h_hi}, {obs_b} {h_obs_lo}-{h_obs_hi}. "
           f"GCM windows: F-late {fl_lo}-{fl_hi}. Basin = {basin}. "
           f"Order = Ward linkage on condensed distance matrix.")
    ST.apply_labels(
        fig, fig_number="10",
        question=("Which simulations have similar daily-distribution shapes? "
                  "Where do the obs sit relative to the GCM cloud?"),
        sub_caption=sub,
    )
    out_path = out_dir / "10_wasserstein_clustermap.png"
    ST.fig_save(fig, out_path)
    D.write_provenance(
        out_path.with_suffix(".txt"),
        fig_name="10_wasserstein_clustermap",
        sims=[obs, obs_b] + sims_future,
        periods={"obs_H": [h_lo, h_hi], "obs_b_H": [h_obs_lo, h_obs_hi],
                 "F_late": [fl_lo, fl_hi]},
        sample_sizes=sample_sizes,
        notes=("Pairwise 1-Wasserstein on standardized daily anomalies. "
               "Ward-linkage clustermap reorder."),
    )
    log.info("wrote %s", out_path)


FIGURES: dict[str, callable] = {
    "01": fig_01_quantile_shift,
    "02": fig_02_wet_day_decomp,
    "03": fig_03_spell_survival,
    "04": fig_04_gev_return,
    "05": fig_05_ar1_spectra,
    "06": fig_06_snow_and_trend,
    "07": fig_07_compound_hot_dry,
    "08": fig_08_cross_obs,
    "09": fig_09_handoff_continuity,
    "10": fig_10_wasserstein_cluster,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="figures/diagnostics")
    parser.add_argument("--only", default="",
                        help="Comma-separated figure IDs to render, e.g. '01,02,07'. Default: all.")
    args = parser.parse_args(argv)

    cfg = cfg_mod.Config.load(args.config)
    parquet_dir = Path(cfg["paths"]["final_parquet"])
    parquets = D.list_parquets(parquet_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("found %d parquets in %s", len(parquets), parquet_dir)
    log.info("output -> %s", out_dir)

    only = {x.strip() for x in args.only.split(",") if x.strip()} or set(FIGURES)
    n_ok = n_skip = n_err = 0
    for fig_id, fn in FIGURES.items():
        if fig_id not in only:
            continue
        log.info("--- figure %s: %s ---", fig_id, fn.__name__)
        try:
            fn(parquets, cfg, out_dir)
            n_ok += 1
        except NotImplementedError:
            log.warning("figure %s not yet implemented", fig_id)
            n_skip += 1
        except Exception as e:  # noqa: BLE001
            log.exception("figure %s failed: %s", fig_id, e)
            n_err += 1

    log.info("summary: %d rendered, %d skipped, %d errored", n_ok, n_skip, n_err)
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
