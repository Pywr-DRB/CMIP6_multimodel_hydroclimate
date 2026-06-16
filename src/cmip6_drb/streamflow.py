"""Join RAPID-routed streamflow from the sibling streamflow repo onto per-node CSVs.

The streamflow repo (``CMIP6_multimodel_streamflow``) routes the *same* Kao et al.
SWA9505V3 VIC/PRMS runoff through RAPID and publishes per-node daily flow
(``gage_flow_mgd.csv``, mgd) under one directory per dataset:

    {LSM}_RAPID_{core}[_{version}]_{period}/gage_flow_mgd.csv

where ``LSM`` is ``VIC5`` or ``PRMS``, ``core`` is either a historical stem
(``Daymet2019``/``Livneh2018``) or a projection stem
(``{GCM}_{ssp}_{ens}_DBCCA_Daymet``), and ``period`` is a year range. The VIC5
historical dirs carry an extra ``v20200704D``-style version token that PRMS dirs
omit, so directories are resolved by **glob** rather than exact construction.

This module is deliberately name-driven: a hydroclimate simulation maps to its
streamflow counterpart purely through naming, so scenarios retrieved in the
future join automatically with no code change.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from . import config as cfg_mod

log = logging.getLogger("streamflow")

# Canonical, unit-suffixed column names so the wide CSV schema is self-documenting.
# Used by both scripts/05_export_node_csv.py (forcing) and scripts/06_join_streamflow.py.
FORCING_UNIT_NAMES: dict[str, str] = {
    "prcp": "prcp_mm_day",
    "tmax": "tmax_degC",
    "tmin": "tmin_degC",
    "wind": "wind_m_s",
    "srad": "srad_W_m2",
    "lrad": "lrad_W_m2",
    "qair": "qair_kg_kg",
    "rhum": "rhum_pct",
}

# Local VIC/PRMS runoff parquet variable -> unit-suffixed column name (mm/day).
RUNOFF_UNIT_NAMES: dict[str, str] = {
    "runoff": "runoff_vic_mm_day",
    "PRMS_runoff": "runoff_prms_mm_day",
}

# Map an LSM token (as named in the streamflow repo) to its short column tag.
_LSM_SHORT: dict[str, str] = {"VIC5": "vic", "PRMS": "prms"}


def lsm_short(lsm: str) -> str:
    """Short tag for an LSM token, e.g. 'VIC5' -> 'vic'. Falls back to lowercase."""
    return _LSM_SHORT.get(lsm, lsm.lower())


def streamflow_col(lsm: str) -> str:
    """Unit-suffixed routed-streamflow column name for an LSM, e.g. streamflow_vic_mgd."""
    return f"streamflow_{lsm_short(lsm)}_mgd"


def _sf_cfg(cfg: cfg_mod.Config) -> dict[str, Any]:
    sf = cfg.get("streamflow")
    if not sf:
        raise KeyError("config has no 'streamflow' block; see config.yaml")
    return sf


def repo_inputs_dir(cfg: cfg_mod.Config) -> Path:
    """Absolute path to the streamflow repo's per-dataset inputs directory."""
    sf = _sf_cfg(cfg)
    p = Path(sf["repo_inputs"])
    if not p.is_absolute():
        p = (cfg_mod.REPO_ROOT / p).resolve()
    return p


def _core_and_periods(sim: str, cfg: cfg_mod.Config) -> tuple[str, list[str]]:
    """Resolve a hydroclimate sim name to its streamflow stem and period list."""
    sf = _sf_cfg(cfg)
    aliases = sf.get("hist_aliases", {})
    if sim in aliases:
        a = aliases[sim]
        return a["stem"], [str(a["period"])]
    # Projection: the streamflow stem equals the hydroclimate sim name verbatim.
    return sim, [str(p) for p in sf.get("proj_periods", [])]


def resolve_streamflow_dirs(sim: str, lsm: str, cfg: cfg_mod.Config) -> list[Path]:
    """Return existing streamflow dataset dirs (with a flow file) for sim × lsm.

    Globs ``{lsm}_RAPID_{core}*{period}`` so the optional version token in VIC5
    historical dirs is absorbed. Returns dirs sorted by period order.
    """
    sf = _sf_cfg(cfg)
    base = repo_inputs_dir(cfg)
    flow_file = sf.get("flow_file", "gage_flow_mgd.csv")
    core, periods = _core_and_periods(sim, cfg)

    dirs: list[Path] = []
    for period in periods:
        matches = sorted(base.glob(f"{lsm}_RAPID_{core}*{period}"))
        matches = [m for m in matches if (m / flow_file).exists()]
        if not matches:
            continue
        if len(matches) > 1:
            log.warning("%s [%s]: ambiguous match for period %s: %s; using first",
                        sim, lsm, period, [m.name for m in matches])
        dirs.append(matches[0])
    return dirs


def load_node_streamflow(
    sim: str, node: str, lsm: str, cfg: cfg_mod.Config
) -> pd.Series | None:
    """Concatenated daily routed-flow series (mgd) for one node, or None if absent.

    Reads each resolved ``gage_flow_mgd.csv``, selects the node column, then
    concatenates periods, drops duplicate dates (keep last), and sorts.
    """
    sf = _sf_cfg(cfg)
    flow_file = sf.get("flow_file", "gage_flow_mgd.csv")
    dirs = resolve_streamflow_dirs(sim, lsm, cfg)
    if not dirs:
        return None

    parts: list[pd.Series] = []
    for d in dirs:
        df = pd.read_csv(d / flow_file, index_col=0, parse_dates=True)
        if node not in df.columns:
            log.warning("%s [%s]: node %r absent in %s; skipping", sim, lsm, node, d.name)
            continue
        parts.append(df[node])
    if not parts:
        return None

    s = pd.concat(parts, axis=0)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.index = pd.DatetimeIndex(s.index).normalize()  # daily date key for alignment
    s.index.name = "date"
    s.name = streamflow_col(lsm)
    return s
