"""Tests for cmip6_drb.aggregate against synthetic DataArrays."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr


def _identity_weights(n_lat: int, n_lon: int):
    """One polygon that is the entire grid with uniform weights."""
    from scipy import sparse
    from cmip6_drb.weights import GridSpec, Weights

    grid = GridSpec(
        lat=np.array([i + 0.5 for i in range(n_lat)], dtype=np.float64),
        lon=np.array([j + 0.5 for j in range(n_lon)], dtype=np.float64),
        crs="EPSG:4326",
    )
    n_cells = n_lat * n_lon
    matrix = sparse.csr_matrix(np.full((1, n_cells), 1.0 / n_cells, dtype=np.float32))
    return Weights(matrix=matrix, node_ids=np.array(["whole_grid"], dtype=object), grid=grid)


def test_aggregate_mean_of_constant_field():
    """Constant 5.0 across 4x4 -> weighted mean is 5.0 every day."""
    from cmip6_drb.aggregate import aggregate_to_nodes

    n_t, n_lat, n_lon = 3, 4, 4
    da = xr.DataArray(
        np.full((n_t, n_lat, n_lon), 5.0, dtype=np.float32),
        dims=("time", "lat", "lon"),
        coords={
            "time": pd.date_range("2000-01-01", periods=n_t, freq="D"),
            "lat": [0.5, 1.5, 2.5, 3.5],
            "lon": [0.5, 1.5, 2.5, 3.5],
        },
    )
    w = _identity_weights(n_lat, n_lon)
    df = aggregate_to_nodes(da, w)
    assert df.shape == (n_t, 1)
    assert df.dtypes.iloc[0] == np.float32
    np.testing.assert_array_almost_equal(df["whole_grid"].values, 5.0)


def test_aggregate_handles_nan_cells():
    """NaN cells should be excluded from the weighted mean (renormalization)."""
    from cmip6_drb.aggregate import aggregate_to_nodes

    n_t, n_lat, n_lon = 1, 2, 2
    arr = np.array([[[1.0, np.nan], [3.0, 4.0]]], dtype=np.float32)  # mean of {1,3,4}=2.667
    da = xr.DataArray(
        arr,
        dims=("time", "lat", "lon"),
        coords={"time": pd.date_range("2000-01-01", periods=n_t),
                "lat": [0.5, 1.5], "lon": [0.5, 1.5]},
    )
    w = _identity_weights(n_lat, n_lon)
    df = aggregate_to_nodes(da, w)
    assert df.iloc[0, 0] == pytest.approx((1 + 3 + 4) / 3, abs=1e-5)


def test_aggregate_grid_mismatch_raises():
    from cmip6_drb.aggregate import aggregate_to_nodes

    da = xr.DataArray(np.zeros((1, 3, 3), dtype=np.float32),
                      dims=("time", "lat", "lon"),
                      coords={"time": [pd.Timestamp("2000-01-01")],
                              "lat": [0.5, 1.5, 2.5], "lon": [0.5, 1.5, 2.5]})
    w = _identity_weights(4, 4)  # grid 4x4 != 3x3
    with pytest.raises(ValueError, match="does not match"):
        aggregate_to_nodes(da, w)
