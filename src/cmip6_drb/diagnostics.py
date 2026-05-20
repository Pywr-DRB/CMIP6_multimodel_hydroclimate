"""Shared analysis helpers for diagnostic figures.

Each helper takes plain pandas/numpy in and returns plain pandas/numpy out
so they are trivially testable. Figure code lives in
`scripts/06_make_diagnostics.py`; nothing here imports matplotlib.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats, signal


# ---------------------------------------------------------------------------
# Parquet discovery
# ---------------------------------------------------------------------------

_PARQUET_RE = re.compile(r"^(.+)__([A-Za-z0-9_]+)\.parquet$")


def list_parquets(parquet_dir: Path) -> dict[tuple[str, str], Path]:
    """Return {(sim, var): path} for every parquet under `parquet_dir`."""
    out: dict[tuple[str, str], Path] = {}
    for p in sorted(Path(parquet_dir).glob("*.parquet")):
        m = _PARQUET_RE.match(p.name)
        if m:
            out[(m.group(1), m.group(2))] = p
    return out


def slice_period(df: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """Inclusive year slice on a DatetimeIndex DataFrame."""
    return df.loc[f"{start}-01-01":f"{end}-12-31"]


# ---------------------------------------------------------------------------
# Season / DOY utilities
# ---------------------------------------------------------------------------

SEASONS = ("DJF", "MAM", "JJA", "SON")


def season_mask(idx: pd.DatetimeIndex, season: str) -> np.ndarray:
    m = idx.month.values
    if season == "DJF":
        return (m == 12) | (m <= 2)
    if season == "MAM":
        return (m >= 3) & (m <= 5)
    if season == "JJA":
        return (m >= 6) & (m <= 8)
    if season == "SON":
        return (m >= 9) & (m <= 11)
    raise ValueError(f"unknown season: {season}")


def doy_climatology(s: pd.Series, smooth: int = 31) -> pd.Series:
    """Return a 1-366 indexed Series of day-of-year mean, optionally smoothed
    with a centered moving average. Works on any DatetimeIndex Series."""
    by_doy = s.groupby(s.index.dayofyear).mean()
    by_doy = by_doy.reindex(range(1, 367))
    if smooth and smooth > 1:
        # Wrap-pad to avoid edge effects.
        pad = smooth // 2
        padded = pd.concat([by_doy.iloc[-pad:], by_doy, by_doy.iloc[:pad]])
        by_doy = padded.rolling(smooth, center=True, min_periods=1).mean().iloc[pad:-pad]
        by_doy.index = range(1, 367)
    return by_doy


def doy_anomaly(s: pd.Series, smooth: int = 31) -> pd.Series:
    """Subtract the (smoothed) DOY climatology, leaving a series that has
    seasonal cycle removed but year-to-year variability preserved."""
    clim = doy_climatology(s, smooth=smooth)
    return s - s.index.dayofyear.map(clim)


def detrend_linear(s: pd.Series) -> pd.Series:
    """OLS linear-trend removal. Returns a Series with same index."""
    x = np.arange(len(s), dtype=float)
    y = s.values.astype(float)
    finite = np.isfinite(y)
    if finite.sum() < 3:
        return s.copy()
    slope, intercept, *_ = stats.linregress(x[finite], y[finite])
    return pd.Series(y - (slope * x + intercept), index=s.index)


# ---------------------------------------------------------------------------
# Wet-day / spell statistics
# ---------------------------------------------------------------------------

def wet_day_mask(prcp: pd.Series, threshold_mm: float = 0.1) -> np.ndarray:
    return (prcp.values >= threshold_mm).astype(np.int8)


def wet_day_stats(prcp: pd.Series, threshold_mm: float = 0.1) -> dict:
    """Return dict with P(wet), mean wet-day intensity, max, sample size."""
    arr = prcp.dropna().values.astype(float)
    if arr.size == 0:
        return {"p_wet": np.nan, "wet_intensity": np.nan, "n": 0}
    wet = arr >= threshold_mm
    return {
        "p_wet": float(wet.mean()),
        "wet_intensity": float(arr[wet].mean()) if wet.any() else 0.0,
        "n": int(arr.size),
    }


def spell_lengths(mask: np.ndarray) -> np.ndarray:
    """Return lengths of consecutive runs where mask == 1.

    Edge runs are counted normally (no truncation correction).
    """
    if mask.size == 0:
        return np.array([], dtype=int)
    arr = np.asarray(mask, dtype=np.int8)
    # Find run starts/ends via diff on padded array.
    padded = np.concatenate(([0], arr, [0]))
    diffs = np.diff(padded)
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    return ends - starts


def survival(lengths: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Empirical survival function S(L) = P(spell >= L). Returns (L, S)."""
    if lengths.size == 0:
        return np.array([1]), np.array([np.nan])
    sorted_L = np.sort(lengths)
    n = sorted_L.size
    # P(X >= L) at each unique L.
    uniq, counts = np.unique(sorted_L, return_counts=True)
    cumfrom_top = np.cumsum(counts[::-1])[::-1]  # # of spells >= each unique L
    return uniq, cumfrom_top / n


# ---------------------------------------------------------------------------
# AR(1) / Welch spectrum
# ---------------------------------------------------------------------------

def ar1(s: pd.Series) -> float:
    """Lag-1 autocorrelation of a series, NaN-tolerant."""
    arr = s.dropna().values.astype(float)
    if arr.size < 3:
        return np.nan
    return float(np.corrcoef(arr[:-1], arr[1:])[0, 1])


def welch_psd(s: pd.Series, nperseg: int = 1024, fs: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Welch power spectral density. Series should be evenly daily-sampled.

    fs=1.0 => frequency in cycles per day; period (days) = 1/freq.
    """
    arr = s.dropna().values.astype(float)
    if arr.size < nperseg * 2:
        nperseg = max(64, arr.size // 4)
    f, psd = signal.welch(arr, fs=fs, nperseg=nperseg, detrend="linear")
    return f, psd


# ---------------------------------------------------------------------------
# Annual maxima / GEV (MLE via scipy)
# ---------------------------------------------------------------------------

def annual_maxima(s: pd.Series, min_year_coverage: float = 0.9) -> pd.Series:
    """Annual block maxima. Years with <`min_year_coverage` of expected days
    are dropped (defends against partial first/last calendar years)."""
    by_year = s.groupby(s.index.year)
    counts = by_year.count()
    expected = by_year.size().rename("n_days")
    # `expected` is the number of days actually present; we only have it from
    # `size()`. For partial years, `size() < 360`.
    valid = expected[expected >= 365 * min_year_coverage].index
    return by_year.max().loc[valid].astype(float)


def gev_fit(am: np.ndarray) -> tuple[float, float, float]:
    """Fit GEV via scipy MLE. Returns (shape, loc, scale).

    scipy parameterizes as genextreme(c, loc, scale) where c = -shape (Hosking).
    We return Hosking-convention shape, i.e. shape = -c.
    """
    am = np.asarray(am, dtype=float)
    am = am[np.isfinite(am)]
    if am.size < 8:
        return (np.nan, np.nan, np.nan)
    c, loc, scale = stats.genextreme.fit(am)
    return (-float(c), float(loc), float(scale))


def gev_return_levels(am: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Return levels at periods T (years), MLE GEV. Returns shape == T.shape."""
    shape, loc, scale = gev_fit(am)
    if not np.isfinite(loc):
        return np.full_like(T, np.nan, dtype=float)
    p_nonexceed = 1.0 - 1.0 / np.asarray(T, dtype=float)
    # scipy's c = -shape. We computed shape, so c = -shape.
    c = -shape
    return stats.genextreme.ppf(p_nonexceed, c, loc=loc, scale=scale)


def gev_bootstrap(am: np.ndarray, T: np.ndarray, n_boot: int = 200,
                  rng: np.random.Generator | None = None,
                  ci: tuple[float, float] = (0.05, 0.95)) -> dict:
    """Nonparametric bootstrap of return levels. Returns dict with 'point',
    'lo', 'hi' arrays (each len(T))."""
    rng = rng or np.random.default_rng(42)
    am = np.asarray(am, dtype=float)
    am = am[np.isfinite(am)]
    point = gev_return_levels(am, T)
    if am.size < 8:
        return {"point": point, "lo": point.copy(), "hi": point.copy()}
    boot = np.empty((n_boot, len(T)), dtype=float)
    for i in range(n_boot):
        sample = rng.choice(am, size=am.size, replace=True)
        try:
            boot[i] = gev_return_levels(sample, T)
        except Exception:  # noqa: BLE001
            boot[i] = np.nan
    lo = np.nanquantile(boot, ci[0], axis=0)
    hi = np.nanquantile(boot, ci[1], axis=0)
    return {"point": point, "lo": lo, "hi": hi}


# ---------------------------------------------------------------------------
# Mann-Kendall + Sen slope (hand-rolled, no pymannkendall dep)
# ---------------------------------------------------------------------------

def mann_kendall(y: np.ndarray) -> dict:
    """Mann-Kendall trend test. Returns dict with S, var, z, p, sen_slope.

    Two-sided p-value. Sen slope is the median pairwise slope.
    Tied-rank correction included.
    """
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    n = y.size
    if n < 4:
        return {"S": np.nan, "var": np.nan, "z": np.nan, "p": np.nan, "sen_slope": np.nan, "n": n}
    # S statistic
    S = 0
    for i in range(n - 1):
        S += np.sum(np.sign(y[i + 1:] - y[i]))
    # Tied-rank variance correction
    _, counts = np.unique(y, return_counts=True)
    tie_term = np.sum(counts * (counts - 1) * (2 * counts + 5))
    var_S = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if S > 0:
        z = (S - 1) / math.sqrt(var_S) if var_S > 0 else np.nan
    elif S < 0:
        z = (S + 1) / math.sqrt(var_S) if var_S > 0 else np.nan
    else:
        z = 0.0
    p = 2.0 * (1.0 - stats.norm.cdf(abs(z))) if np.isfinite(z) else np.nan
    # Sen slope
    slopes = []
    for i in range(n - 1):
        slopes.extend((y[i + 1:] - y[i]) / np.arange(1, n - i))
    sen = float(np.median(slopes)) if slopes else np.nan
    return {"S": float(S), "var": float(var_S), "z": float(z), "p": float(p),
            "sen_slope": sen, "n": n}


def bh_fdr(pvalues: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg FDR. Returns boolean array of which tests reject H0."""
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    order = np.argsort(p)
    ranked = p[order]
    thresh = (np.arange(1, n + 1) / n) * alpha
    passing = ranked <= thresh
    if not passing.any():
        return np.zeros(n, dtype=bool)
    k = np.where(passing)[0].max()
    reject = np.zeros(n, dtype=bool)
    reject[order[: k + 1]] = True
    return reject


# ---------------------------------------------------------------------------
# Wasserstein distance on standardized anomalies
# ---------------------------------------------------------------------------

def standardized_anomaly(s: pd.Series, smooth: int = 31) -> pd.Series:
    """Subtract DOY climatology and divide by DOY std (robustly).

    Used as a normalization before cross-simulation distance comparison so the
    metric is unaffected by mean / amplitude differences and reflects shape only.
    """
    clim = doy_climatology(s, smooth=smooth)
    sd_by_doy = s.groupby(s.index.dayofyear).std().reindex(range(1, 367))
    sd_by_doy = sd_by_doy.fillna(sd_by_doy.median())
    sd_by_doy = sd_by_doy.replace(0, sd_by_doy.median())
    anom = s - s.index.dayofyear.map(clim)
    sigma = s.index.dayofyear.map(sd_by_doy).astype(float).to_numpy()
    return pd.Series(anom.values / sigma, index=s.index)


def wasserstein_pair(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if a.size == 0 or b.size == 0:
        return np.nan
    return float(stats.wasserstein_distance(a, b))


def pairwise_wasserstein(samples: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray]:
    """Pairwise 1-Wasserstein distance matrix over keyed sample arrays.

    Returns (labels, D) where D is an (n,n) symmetric distance matrix.
    """
    labels = list(samples.keys())
    n = len(labels)
    D = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            d = wasserstein_pair(samples[labels[i]], samples[labels[j]])
            D[i, j] = D[j, i] = d
    return labels, D


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def write_provenance(path: Path, *, fig_name: str, sims: Iterable[str],
                     periods: dict, sample_sizes: dict[str, int],
                     notes: str = "") -> None:
    """Write a sibling .txt file recording exactly which inputs the figure used."""
    lines = [f"figure: {fig_name}"]
    lines.append(f"periods: {periods}")
    lines.append(f"simulations ({len(list(sims))}):")
    for s in sims:
        lines.append(f"  - {s}")
    if sample_sizes:
        lines.append("sample_sizes:")
        for k, v in sample_sizes.items():
            lines.append(f"  - {k}: {v}")
    if notes:
        lines.append(f"notes: {notes}")
    Path(path).write_text("\n".join(lines) + "\n")
