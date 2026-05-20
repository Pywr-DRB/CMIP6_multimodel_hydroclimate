"""Plot styling: GCM color palette, period labels, and the explicit-label helper.

Single source of truth for colors and decorations across `scripts/05_make_figures.py`
and `scripts/06_make_diagnostics.py`. Designed so figures are readable as standalone
slides without captions.
"""

from __future__ import annotations

import datetime as _dt
import subprocess
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.figure import Figure


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

GCM_COLORS: dict[str, str] = {
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

OBS_NAMES: tuple[str, ...] = ("DaymetV4", "Livneh")


def color_for_sim(sim: str) -> str:
    if sim in GCM_COLORS:
        return GCM_COLORS[sim]
    for gcm, c in GCM_COLORS.items():
        if sim.startswith(gcm + "_"):
            return c
    return "#999999"


def is_obs(sim: str) -> bool:
    return sim in OBS_NAMES


def gcm_of(sim: str) -> str:
    """Extract GCM family name from a full simulation identifier."""
    if sim in OBS_NAMES:
        return sim
    for gcm in GCM_COLORS:
        if sim == gcm or sim.startswith(gcm + "_"):
            return gcm
    return sim.split("_")[0]


def line_kwargs(sim: str, period: str | None = None) -> dict:
    """Default line styling. Obs/historical are heavy and opaque; future GCMs are
    light and translucent so multiple curves overlay without obscuring each other."""
    if is_obs(sim):
        return {"color": color_for_sim(sim), "lw": 1.8, "alpha": 0.95}
    return {"color": color_for_sim(sim), "lw": 1.0, "alpha": 0.55}


# ---------------------------------------------------------------------------
# Variable units / formulas / pretty names
# ---------------------------------------------------------------------------

VAR_PRETTY: dict[str, str] = {
    "prcp": "Daily total precipitation",
    "tmax": "Daily maximum air temperature",
    "tmin": "Daily minimum air temperature",
    "tmean": "Daily mean air temperature",
    "wind": "Daily mean 10 m wind speed",
    "srad": "Downwelling shortwave radiation",
    "vpd": "Vapor pressure deficit",
    "qair": "Specific humidity",
    "rhum": "Relative humidity",
    "vp": "Vapor pressure",
    "pres": "Surface pressure",
}

VAR_UNITS: dict[str, str] = {
    "prcp": "mm day$^{-1}$",
    "tmax": "$^\\circ$C",
    "tmin": "$^\\circ$C",
    "tmean": "$^\\circ$C",
    "wind": "m s$^{-1}$",
    "srad": "W m$^{-2}$",
    "vpd": "kPa",
    "qair": "kg kg$^{-1}$",
    "rhum": "%",
    "vp": "kPa",
    "pres": "Pa",
}


def var_label(variable: str) -> str:
    pretty = VAR_PRETTY.get(variable, variable)
    units = VAR_UNITS.get(variable, "")
    return f"{pretty} ({units})" if units else pretty


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------

PERIOD_PRETTY: dict[str, str] = {
    "H": "1980–2014 (H)",
    "H_obs_full": "1980–2018 (H_obs_full)",
    "HO": "2015–2018 (HO overlap)",
    "F_early": "2020–2049 (F-early)",
    "F_late": "2070–2099 (F-late)",
}


def period_label(period: str) -> str:
    return PERIOD_PRETTY.get(period, period)


def season_of(month_array):
    """Map an array of months (1-12) to season strings (DJF, MAM, JJA, SON)."""
    import numpy as np
    m = np.asarray(month_array)
    out = np.empty(m.shape, dtype=object)
    out[(m == 12) | (m <= 2)] = "DJF"
    out[(m >= 3) & (m <= 5)] = "MAM"
    out[(m >= 6) & (m <= 8)] = "JJA"
    out[(m >= 9) & (m <= 11)] = "SON"
    return out


SEASONS = ("DJF", "MAM", "JJA", "SON")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def _git_sha_short() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2, check=True,
        )
        return out.stdout.strip() or "?"
    except Exception:  # noqa: BLE001
        return "?"


# ---------------------------------------------------------------------------
# Explicit-labeling helper
# ---------------------------------------------------------------------------

def apply_labels(
    fig: Figure,
    *,
    fig_number: str,
    question: str,
    sub_caption: str = "",
    script: str = "scripts/06_make_diagnostics.py",
    wrap_chars: int = 130,
) -> None:
    """Apply the explicit-labeling standard for diagnostic figures.

    - Suptitle = "Fig. NN — {plain-English question}"
    - Sub-caption = analysis windows / sample sizes / thresholds (small italic),
      wrapped to ~`wrap_chars` per line for readability on slides
    - Provenance footer = "<date> · <script> · <git>"

    Call AFTER tight_layout() so the suptitle/footer don't crowd the axes.
    Reserve top whitespace via tight_layout(rect=(0, 0.02, 1, top)) where
    `top` accounts for the title + caption — a 2-line caption needs top≈0.88
    on a 5" figure; a 4-line caption needs top≈0.82.
    """
    import textwrap as _tw
    fig_h = fig.get_figheight()
    # Pre-wrap so we know how many lines we'll consume.
    wrapped = _tw.fill(sub_caption, width=wrap_chars) if sub_caption else ""
    n_lines = wrapped.count("\n") + 1 if wrapped else 0

    title_y = 1.0 - (0.30 / fig_h)
    # Each line of caption ~0.18" tall; reserve that height below the title.
    cap_y = 1.0 - (0.55 / fig_h)
    suptitle = f"Fig. {fig_number} — {question}"
    fig.suptitle(suptitle, fontsize=12, y=title_y, fontweight="bold")
    if wrapped:
        fig.text(
            0.5, cap_y, wrapped,
            ha="center", va="top", fontsize=8.5, style="italic", color="#444",
        )
    today = _dt.date.today().isoformat()
    fig.text(
        0.995, 0.005,
        f"generated {today} · {script} · git {_git_sha_short()}",
        ha="right", va="bottom", fontsize=6.5, color="#888",
    )


def add_legend_full_names(ax, sim_period_pairs: Iterable[tuple[str, str]] | None = None) -> None:
    """Replace the legend with one whose entries are full sim names.

    `sim_period_pairs` is an iterable of (sim, period) tuples to override the
    label text; if None, uses whatever was passed via `label=` to plot calls.
    """
    handles, labels = ax.get_legend_handles_labels()
    if sim_period_pairs is not None:
        labels = [f"{sim} — {period}" if period else sim for sim, period in sim_period_pairs]
    if not handles:
        return
    ax.legend(handles, labels, frameon=False, fontsize=8, ncol=1, loc="best")


def fig_save(fig: Figure, path) -> None:
    """Standard 300-dpi PNG save with tight bbox."""
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
