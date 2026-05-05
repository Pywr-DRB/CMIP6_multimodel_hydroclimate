"""Enumerate (simulation, variable, year) tasks and their source URLs/paths.

The Kao et al. dataset path pattern is (verified by HTTPS listing of
hydrosource2.ornl.gov/files/SWA9505V3/):

    {simulation}/{variable}/{simulation}_{engine}_{variable}_{year}.nc   # VIC variables
    {simulation}/{variable}/{simulation}_{variable}_{year}.nc            # PRMS_* variables

Engine = "VIC4" for the climate-meteorology + VIC-derived variables
(prcp, tmax, tmin, wind, srad, lrad, qair, rhum, vp, vpd, pres, runoff*,
swe, evap, pet, soilm). For variables already prefixed with "PRMS_" the
filename omits the engine (the PRMS_ in the variable name plays that role).

Historical: DaymetV4, Livneh.
Future:     {gcm}_{ssp}_{ensemble}_{downscaling}_{ref_obs}.

Ensemble IDs differ per GCM (e.g., CNRM-ESM2-1 uses r1i1p1f2). They are
configured per-GCM via config["dataset"]["ensembles"] (optional override);
default is r1i1p1f1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator


def _engine_token(variable: str) -> str:
    """Return the engine token included in the filename for a variable."""
    return "" if variable.startswith("PRMS_") else "VIC4"


@dataclass(frozen=True)
class Task:
    simulation: str
    variable: str
    year: int

    def filename(self) -> str:
        eng = _engine_token(self.variable)
        if eng:
            return f"{self.simulation}_{eng}_{self.variable}_{self.year}.nc"
        return f"{self.simulation}_{self.variable}_{self.year}.nc"

    def relpath(self) -> str:
        return f"{self.simulation}/{self.variable}/{self.filename()}"


def historical_simulations(cfg) -> list[str]:
    return list(cfg["dataset"]["historical_simulations"])


def future_simulation_names(cfg, ensembles: dict[str, list[str]] | None = None) -> list[str]:
    """Build future simulation names from the config cartesian product.

    `ensembles` maps GCM -> list of ensemble IDs. If None, the config's
    `dataset.ensembles` mapping is used; absent entries fall back to r1i1p1f1.
    """
    ds = cfg["dataset"]
    if ensembles is None:
        ensembles = {gcm: list(ds.get("ensembles", {}).get(gcm, ["r1i1p1f1"])) for gcm in ds["gcms"]}
    sims: list[str] = []
    for gcm in ds["gcms"]:
        for ssp in ds["ssps"]:
            for ens in ensembles.get(gcm, ["r1i1p1f1"]):
                for dscl in ds["downscalings"]:
                    for ref in ds["ref_obs"]:
                        sims.append(f"{gcm}_{ssp}_{ens}_{dscl}_{ref}")
    return sims


def all_simulations(cfg, ensembles: dict[str, list[str]] | None = None) -> list[str]:
    return historical_simulations(cfg) + future_simulation_names(cfg, ensembles)


def years_for_simulation(cfg, simulation: str) -> Iterable[int]:
    ds = cfg["dataset"]
    if simulation in ds["historical_simulations"]:
        spec = ds["historical_years"][simulation]
        return range(spec["start"], spec["end"] + 1)
    return range(ds["future_years"]["start"], ds["future_years"]["end"] + 1)


def variables(cfg) -> list[str]:
    return list(cfg["dataset"]["variables"])


def iter_tasks(
    cfg,
    *,
    simulations: list[str] | None = None,
    variables_filter: list[str] | None = None,
    ensembles: dict[str, list[str]] | None = None,
) -> Iterator[Task]:
    sims = simulations if simulations is not None else all_simulations(cfg, ensembles)
    vars_ = variables_filter if variables_filter is not None else variables(cfg)
    for sim in sims:
        for var in vars_:
            for yr in years_for_simulation(cfg, sim):
                yield Task(simulation=sim, variable=var, year=yr)


def http_url(cfg, task: Task) -> str:
    base = cfg["https"]["base_url"].rstrip("/")
    return f"{base}/{task.relpath()}"
