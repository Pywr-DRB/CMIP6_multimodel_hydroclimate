"""Parquet IO with dtype coercion and atomic writes.

Wide-format convention: index = DatetimeIndex named 'date',
columns = node_id strings, values = float32.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd


def write_parquet_atomic(df: pd.DataFrame, dest: str | Path) -> Path:
    """Atomic parquet write: write to .tmp and rename. Float32 enforced."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    out = df.copy()
    if out.index.name is None:
        out.index.name = "date"
    out = out.astype(np.float32, copy=False)
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.DatetimeIndex(out.index)

    out.to_parquet(tmp, index=True, compression="zstd", compression_level=3)
    os.replace(tmp, dest)
    return dest


def read_parquet(path: str | Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.DatetimeIndex(df.index)
    return df.astype(np.float32, copy=False)


def concat_yearly(parts: list[Path]) -> pd.DataFrame:
    """Concatenate per-year intermediate parquets into one DataFrame."""
    frames = [read_parquet(p) for p in sorted(parts)]
    df = pd.concat(frames, axis=0)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df
