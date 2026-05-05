"""Tests for cmip6_drb.io: parquet round-trip + dtype enforcement + atomic write."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _sample_df():
    idx = pd.date_range("2000-01-01", periods=10, freq="D")
    return pd.DataFrame(
        {"a": np.arange(10, dtype=np.float64),
         "b": np.linspace(0, 1, 10, dtype=np.float64)},
        index=idx,
    )


def test_write_read_roundtrip(tmp_path):
    from cmip6_drb.io import read_parquet, write_parquet_atomic

    dest = tmp_path / "out.parquet"
    df = _sample_df()
    write_parquet_atomic(df, dest)
    assert dest.exists()
    out = read_parquet(dest)
    assert out.shape == df.shape
    assert out.dtypes.iloc[0] == np.float32
    np.testing.assert_array_almost_equal(out["a"].values, df["a"].values.astype(np.float32))


def test_atomic_write_no_partial(tmp_path):
    from cmip6_drb.io import write_parquet_atomic

    dest = tmp_path / "atomic.parquet"
    df = _sample_df()
    write_parquet_atomic(df, dest)
    # The .tmp companion should not survive a successful write.
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()


def test_concat_yearly(tmp_path):
    from cmip6_drb.io import concat_yearly, write_parquet_atomic

    parts = []
    for year, off in zip([2000, 2001, 2002], [0, 100, 200]):
        idx = pd.date_range(f"{year}-01-01", periods=5, freq="D")
        df = pd.DataFrame({"x": np.arange(off, off + 5, dtype=np.float32)}, index=idx)
        p = tmp_path / f"part_{year}.parquet"
        write_parquet_atomic(df, p)
        parts.append(p)
    combined = concat_yearly(parts)
    assert combined.shape == (15, 1)
    np.testing.assert_array_equal(
        combined["x"].values,
        np.concatenate([np.arange(0, 5), np.arange(100, 105), np.arange(200, 205)]).astype(np.float32),
    )
