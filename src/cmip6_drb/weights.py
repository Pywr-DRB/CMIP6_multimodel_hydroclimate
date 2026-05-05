"""Polygon-grid intersection weights for catchment aggregation.

Computes fractional area weights for each (polygon, grid_cell) pair using
exactextract's coverage_fraction operation. Weights are persisted as a
sparse CSR matrix of shape (n_polygons, n_lat * n_lon) so applying them
to a (time, lat, lon) DataArray reduces to one sparse @ dense matmul.

Why exactextract: it computes exact fractional pixel coverage (not just
"centroid in polygon" or "raster of polygon"), so weighted means are
unbiased even for polygons smaller than a few cells.

The weights are computed ONCE per (shapefile, grid). Since every Kao et al.
NetCDF shares the same lat/lon coordinates after bbox clipping, we persist
ONE weights file and reuse it for every (sim, var, year) task.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
import xarray as xr

log = logging.getLogger(__name__)

NODE_ID_FIELD_CANDIDATES = ("node", "Node", "name", "NAME", "node_name")


@dataclass
class GridSpec:
    """The geographic grid (after DRB-bbox clip) that weights are valid for."""
    lat: np.ndarray  # 1D, ascending or descending
    lon: np.ndarray  # 1D
    crs: str

    @classmethod
    def from_dataarray(cls, da: xr.DataArray, crs: str = "EPSG:4326") -> "GridSpec":
        return cls(lat=np.asarray(da["lat"].values),
                   lon=np.asarray(da["lon"].values),
                   crs=crs)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.lat.size, self.lon.size)


@dataclass
class Weights:
    """Sparse weights ready for matmul.

    matrix: scipy.sparse.csr_matrix of shape (n_polygons, n_lat * n_lon)
    node_ids: array of polygon identifiers, length n_polygons
    grid: GridSpec the weights apply to (lat, lon flattened in C order)
    """
    matrix: object  # scipy.sparse.csr_matrix; type-hinted as object to defer scipy import
    node_ids: np.ndarray
    grid: GridSpec

    @property
    def n_polygons(self) -> int:
        return self.matrix.shape[0]


def _detect_node_id(gdf) -> str:
    for c in NODE_ID_FIELD_CANDIDATES:
        if c in gdf.columns:
            return c
    raise KeyError(
        f"Could not find a node-id column in shapefile; tried {NODE_ID_FIELD_CANDIDATES}. "
        f"Available columns: {list(gdf.columns)}"
    )


def _build_template_dataarray(grid: GridSpec) -> xr.DataArray:
    """Construct a north-up xarray DataArray matching the grid for exactextract.

    exactextract internally rasterizes against the DataArray's coords; we hand
    it a north-up grid (descending y) so cell_id row 0 == northernmost. We then
    map cell_id -> (raster_row, raster_col) -> back to grid (lat, lon) ordering.
    """
    import rioxarray  # noqa: F401  (registers .rio accessor)

    n_lat, n_lon = grid.shape
    # Build a north-up template (y descending). If the input grid.lat is ascending
    # we keep that as the canonical "grid" axis and translate cell_id back.
    lat_north_up = grid.lat[::-1] if grid.lat[0] < grid.lat[-1] else grid.lat
    da = xr.DataArray(
        np.zeros((n_lat, n_lon), dtype=np.float32),
        dims=("y", "x"),
        coords={"y": lat_north_up, "x": grid.lon},
        name="template",
    )
    da = da.rio.write_crs(grid.crs)
    return da


def compute_weights(shapefile: str | Path, grid: GridSpec) -> Weights:
    """Compute fractional-area weights for each polygon × cell.

    Uses exactextract.exact_extract with ops ["cell_id", "coverage"]. Returns a
    row-normalized sparse CSR matrix of shape (n_polygons, n_lat*n_lon).
    Cell flattening is C-order: flat = lat_idx * n_lon + lon_idx, where lat_idx
    indexes grid.lat (whatever its native orientation).
    """
    import geopandas as gpd
    from exactextract import exact_extract
    from scipy import sparse

    gdf = gpd.read_file(shapefile)
    if gdf.crs is None:
        raise ValueError(f"Shapefile {shapefile} has no CRS metadata")
    gdf = gdf.to_crs(grid.crs)
    id_field = _detect_node_id(gdf)
    node_ids = np.asarray(gdf[id_field].values, dtype=object)

    template = _build_template_dataarray(grid)
    n_lat, n_lon = grid.shape

    results = exact_extract(
        template,
        gdf,
        ops=["cell_id", "coverage"],
        output="pandas",
    )

    grid_lat_ascending = grid.lat[0] < grid.lat[-1]
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for poly_idx, rec in results.iterrows():
        cell_ids = np.asarray(rec["cell_id"], dtype=np.int64).ravel()
        fractions = np.asarray(rec["coverage"], dtype=np.float32).ravel()
        if cell_ids.size == 0:
            continue
        # cell_id row-major against the north-up template: row 0 = northernmost.
        raster_row = cell_ids // n_lon
        raster_col = cell_ids % n_lon
        # Translate raster_row -> grid lat_idx
        if grid_lat_ascending:
            lat_idx = n_lat - 1 - raster_row
        else:
            lat_idx = raster_row
        flat = (lat_idx * n_lon + raster_col).astype(np.int32)
        keep = fractions > 0.0
        rows.extend([int(poly_idx)] * int(keep.sum()))
        cols.extend(flat[keep].tolist())
        data.extend(fractions[keep].tolist())

    matrix = sparse.csr_matrix(
        (np.asarray(data, dtype=np.float32),
         (np.asarray(rows, dtype=np.int32), np.asarray(cols, dtype=np.int32))),
        shape=(len(node_ids), n_lat * n_lon),
    )
    # Normalize each row to sum to 1.0 so weighted means are unitless.
    row_sums = np.asarray(matrix.sum(axis=1)).flatten()
    nonzero = row_sums > 0
    inv = np.zeros_like(row_sums, dtype=np.float64)
    inv[nonzero] = 1.0 / row_sums[nonzero]
    matrix = sparse.diags(inv) @ matrix
    matrix = matrix.tocsr().astype(np.float32)

    log.info("Computed weights: %d polygons × %d cells, %d non-zero entries",
             matrix.shape[0], matrix.shape[1], matrix.nnz)
    return Weights(matrix=matrix, node_ids=node_ids, grid=grid)


def save_weights(weights: Weights, out_dir: str | Path) -> dict[str, Path]:
    """Persist weights to parquet (tidy) and npz (sparse CSR + grid)."""
    from scipy import sparse

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    coo = weights.matrix.tocoo()
    n_lon = weights.grid.lon.size
    flat = coo.col
    df = pd.DataFrame({
        "node_idx": coo.row.astype(np.int32),
        "node_id": weights.node_ids[coo.row],
        "lat_idx": (flat // n_lon).astype(np.int32),
        "lon_idx": (flat % n_lon).astype(np.int32),
        "weight": coo.data.astype(np.float32),
    })
    parquet_path = out_dir / "drb_node_weights.parquet"
    df.to_parquet(parquet_path, index=False)

    npz_path = out_dir / "drb_node_weights.npz"
    sparse.save_npz(npz_path, weights.matrix)

    grid_npz = out_dir / "drb_node_weights_grid.npz"
    np.savez(
        grid_npz,
        lat=weights.grid.lat,
        lon=weights.grid.lon,
        node_ids=np.asarray(weights.node_ids, dtype=object),
        crs=np.asarray([weights.grid.crs], dtype=object),
    )
    return {"parquet": parquet_path, "matrix": npz_path, "grid": grid_npz}


def load_weights(weights_dir: str | Path) -> Weights:
    from scipy import sparse

    weights_dir = Path(weights_dir)
    matrix = sparse.load_npz(weights_dir / "drb_node_weights.npz")
    grid = np.load(weights_dir / "drb_node_weights_grid.npz", allow_pickle=True)
    return Weights(
        matrix=matrix.astype(np.float32),
        node_ids=np.asarray(grid["node_ids"]),
        grid=GridSpec(lat=grid["lat"], lon=grid["lon"], crs=str(grid["crs"][0])),
    )


def verify_weights(weights: Weights, *, tol_sum: float = 1e-3, tol_zero_rows: int = 0) -> Mapping[str, float]:
    """Sanity checks on the weights matrix.

    Returns a dict of summary stats; raises AssertionError if checks fail.
    """
    row_sums = np.asarray(weights.matrix.sum(axis=1)).flatten()
    n_zero = int(np.sum(row_sums == 0))
    max_dev = float(np.max(np.abs(row_sums - 1.0)))
    if n_zero > tol_zero_rows:
        raise AssertionError(f"{n_zero} polygon(s) have zero total weight (no grid overlap).")
    if max_dev > tol_sum:
        raise AssertionError(f"Max row-sum deviation {max_dev:.4g} exceeds tolerance {tol_sum:.4g}.")
    return {"n_polygons": float(weights.n_polygons), "max_row_sum_dev": max_dev, "nnz": float(weights.matrix.nnz)}
