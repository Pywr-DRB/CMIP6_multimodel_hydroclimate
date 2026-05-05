"""Clip a NetCDF file to the DRB bbox and apply pre-computed weights.

The hot path (per (sim, var, year) task) is:
    open NetCDF -> clip lat/lon -> reshape (time, lat*lon) -> sparse matmul
    -> wide pandas DataFrame indexed by time, columns by node_id.

Float32 throughout. The clipping step is the single biggest memory saver:
the full grid is 697×1405×T but the DRB bbox is ~40×25×T (~700× fewer cells).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
import xarray as xr

from .weights import Weights

log = logging.getLogger(__name__)


@dataclass
class Bbox:
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float

    @classmethod
    def from_config(cls, cfg) -> "Bbox":
        b = cfg["drb_bbox"]
        return cls(b["lon_min"], b["lon_max"], b["lat_min"], b["lat_max"])


def open_clipped(nc_path: str | Path, variable: str, bbox: Bbox, *, time_chunk: int = 90) -> xr.DataArray:
    """Open a NetCDF and return the variable as a (time, lat, lon) DataArray clipped to bbox.

    Uses xarray + h5netcdf when available (faster than netCDF4 for HDF5-backed files).
    """
    ds = xr.open_dataset(nc_path, chunks={"time": time_chunk})
    if variable not in ds.data_vars:
        # PRMS_* files store the variable WITHOUT the "PRMS_" prefix
        # (filename has it, internal var name doesn't).
        bare = variable[5:] if variable.startswith("PRMS_") else variable
        candidates = [v for v in ds.data_vars if v.lower() in (variable.lower(), bare.lower())]
        if not candidates:
            raise KeyError(f"Variable {variable!r} not found in {nc_path}; vars={list(ds.data_vars)}")
        variable = candidates[0]
    da = ds[variable]

    lon = da["lon"]
    lat = da["lat"]
    # Slice respects ascending or descending lat axes.
    if float(lat[0]) <= float(lat[-1]):
        lat_sel = slice(bbox.lat_min, bbox.lat_max)
    else:
        lat_sel = slice(bbox.lat_max, bbox.lat_min)
    if float(lon[0]) <= float(lon[-1]):
        lon_sel = slice(bbox.lon_min, bbox.lon_max)
    else:
        lon_sel = slice(bbox.lon_max, bbox.lon_min)

    da = da.sel(lat=lat_sel, lon=lon_sel)
    return da.astype(np.float32)


def aggregate_to_nodes(da: xr.DataArray, weights: Weights) -> pd.DataFrame:
    """Apply pre-computed weights to a clipped DataArray.

    Returns a wide-format DataFrame: index = time (datetime64[ns]),
    columns = node_id (string), values = float32 weighted means.
    """
    n_lat = weights.grid.lat.size
    n_lon = weights.grid.lon.size

    if da.sizes.get("lat") != n_lat or da.sizes.get("lon") != n_lon:
        raise ValueError(
            f"DataArray grid {da.sizes['lat']}×{da.sizes['lon']} does not match weights grid {n_lat}×{n_lon}. "
            "Was the weights file computed against a different bbox or shapefile?"
        )

    values = da.values  # (time, lat, lon)
    if values.dtype != np.float32:
        values = values.astype(np.float32, copy=False)

    n_t = values.shape[0]
    flat = values.reshape(n_t, n_lat * n_lon)  # C-order matches weights flattening
    nan_mask = np.isnan(flat)
    if nan_mask.any():
        flat = np.where(nan_mask, 0.0, flat)
        # Adjust per-(time, node) divisor by which cells contributed
        # (otherwise NaN cells get treated as zeros in the weighted mean).
        valid = (~nan_mask).astype(np.float32)
        # weights @ valid.T  -> (n_node, n_t). Transpose to align.
        denom = weights.matrix @ valid.T  # shape (n_node, n_t)
        numer = weights.matrix @ flat.T   # shape (n_node, n_t)
        with np.errstate(invalid="ignore", divide="ignore"):
            agg = np.where(denom > 0, numer / denom, np.nan).astype(np.float32)
    else:
        agg = (weights.matrix @ flat.T).astype(np.float32)  # (n_node, n_t)

    time_index = pd.DatetimeIndex(_to_datetime(da["time"].values))
    columns = [str(n) for n in weights.node_ids]
    return pd.DataFrame(agg.T, index=time_index, columns=columns).astype(np.float32)


def _to_datetime(values) -> np.ndarray:
    """Convert NetCDF time values (cftime or numpy datetime64) to datetime64[ns]."""
    if values.dtype.kind == "M":
        return values.astype("datetime64[ns]")
    # cftime objects: convert one-by-one. Skip Feb 29 in noleap; pad in 360-day handled upstream.
    out: list[pd.Timestamp] = []
    for t in values:
        try:
            out.append(pd.Timestamp(t.year, t.month, t.day))
        except Exception:
            # 360-day calendars can have day=30 in months without it; clip to month-end.
            from calendar import monthrange
            day = min(t.day, monthrange(t.year, t.month)[1])
            out.append(pd.Timestamp(t.year, t.month, day))
    return np.asarray(out, dtype="datetime64[ns]")


def aggregate_file(
    nc_path: str | Path,
    variable: str,
    bbox: Bbox,
    weights: Weights,
) -> pd.DataFrame:
    """One-call aggregator: open + clip + matmul. Returns wide DataFrame."""
    da = open_clipped(nc_path, variable, bbox)
    return aggregate_to_nodes(da, weights)
