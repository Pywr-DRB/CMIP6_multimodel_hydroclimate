"""Tests for cmip6_drb.weights against analytical answers."""

from __future__ import annotations

import numpy as np
import pytest


def _make_unit_grid(n: int) -> "weights.GridSpec":  # noqa: F821
    from cmip6_drb.weights import GridSpec
    # Cells of size 1x1 covering [0, n] x [0, n], pixel centers at half-integers.
    lat = np.array([i + 0.5 for i in range(n)], dtype=np.float64)  # ascending
    lon = np.array([j + 0.5 for j in range(n)], dtype=np.float64)
    return GridSpec(lat=lat, lon=lon, crs="EPSG:4326")


def test_single_unit_polygon_centered_on_grid_cell(tmp_path):
    """A 1x1 polygon perfectly aligned to one cell -> that cell has weight 1.0."""
    import geopandas as gpd
    from shapely.geometry import box
    from cmip6_drb.weights import compute_weights

    grid = _make_unit_grid(4)
    poly_path = tmp_path / "p.gpkg"
    gpd.GeoDataFrame({"node": ["A"]},
                     geometry=[box(1.0, 1.0, 2.0, 2.0)],
                     crs="EPSG:4326").to_file(poly_path, driver="GPKG")

    w = compute_weights(str(poly_path), grid)
    assert w.matrix.shape == (1, 16)
    row = np.asarray(w.matrix.todense()).ravel()
    # Cell center at lat=1.5 (idx 1), lon=1.5 (idx 1) -> flat idx 1*4 + 1 = 5
    assert row[5] == pytest.approx(1.0, abs=1e-6)
    assert row.sum() == pytest.approx(1.0, abs=1e-6)


def test_quarter_overlap_polygon(tmp_path):
    """A polygon covering quarter-cells across 4 cells -> each gets weight 0.25."""
    import geopandas as gpd
    from shapely.geometry import box
    from cmip6_drb.weights import compute_weights

    grid = _make_unit_grid(4)
    poly_path = tmp_path / "p.gpkg"
    # Shift polygon by half-cell so it straddles 4 grid cells equally.
    gpd.GeoDataFrame({"node": ["A"]},
                     geometry=[box(0.5, 0.5, 1.5, 1.5)],
                     crs="EPSG:4326").to_file(poly_path, driver="GPKG")
    w = compute_weights(str(poly_path), grid)
    row = np.asarray(w.matrix.todense()).ravel()
    nz = np.where(row > 0)[0]
    assert nz.size == 4
    for v in row[nz]:
        assert v == pytest.approx(0.25, abs=1e-6)
    assert row.sum() == pytest.approx(1.0, abs=1e-6)


def test_save_and_load_roundtrip(tmp_path):
    import geopandas as gpd
    from shapely.geometry import box
    from cmip6_drb.weights import compute_weights, save_weights, load_weights

    grid = _make_unit_grid(4)
    poly_path = tmp_path / "p.gpkg"
    gpd.GeoDataFrame({"node": ["A", "B"]},
                     geometry=[box(0.0, 0.0, 1.0, 1.0), box(2.0, 2.0, 4.0, 4.0)],
                     crs="EPSG:4326").to_file(poly_path, driver="GPKG")
    w = compute_weights(str(poly_path), grid)
    save_weights(w, tmp_path / "out")
    w2 = load_weights(tmp_path / "out")
    assert w2.matrix.nnz == w.matrix.nnz
    assert list(w2.node_ids) == list(w.node_ids)
    np.testing.assert_array_equal(w2.matrix.toarray(), w.matrix.toarray())
