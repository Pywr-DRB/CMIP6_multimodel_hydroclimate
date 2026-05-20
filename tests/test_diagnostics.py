"""Tests for cmip6_drb.diagnostics: stats helpers used by the figure pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_ar1_white_noise_near_zero():
    from cmip6_drb.diagnostics import ar1
    rng = np.random.default_rng(0)
    s = pd.Series(rng.standard_normal(5000))
    assert abs(ar1(s)) < 0.05


def test_ar1_recovers_phi():
    from cmip6_drb.diagnostics import ar1
    rng = np.random.default_rng(0)
    phi = 0.7
    e = rng.standard_normal(5000)
    y = np.zeros_like(e)
    for i in range(1, len(e)):
        y[i] = phi * y[i - 1] + e[i]
    est = ar1(pd.Series(y))
    assert abs(est - phi) < 0.05


def test_mann_kendall_monotone():
    from cmip6_drb.diagnostics import mann_kendall
    res = mann_kendall(np.arange(50, dtype=float))
    assert res["p"] < 1e-6
    assert res["sen_slope"] == pytest.approx(1.0)


def test_mann_kendall_handles_short():
    from cmip6_drb.diagnostics import mann_kendall
    res = mann_kendall(np.array([1.0, 2.0]))
    assert np.isnan(res["p"])


def test_wasserstein_identical_zero():
    from cmip6_drb.diagnostics import wasserstein_pair
    a = np.arange(100, dtype=float)
    assert wasserstein_pair(a, a) == 0.0


def test_wasserstein_shifted():
    from cmip6_drb.diagnostics import wasserstein_pair
    a = np.arange(100, dtype=float)
    assert wasserstein_pair(a, a + 5.0) == pytest.approx(5.0)


def test_spell_lengths_basic():
    from cmip6_drb.diagnostics import spell_lengths
    out = spell_lengths(np.array([1, 1, 0, 1, 1, 1, 0, 0, 1]))
    assert list(out) == [2, 3, 1]


def test_spell_lengths_empty():
    from cmip6_drb.diagnostics import spell_lengths
    assert spell_lengths(np.array([], dtype=int)).size == 0


def test_survival_step_function():
    from cmip6_drb.diagnostics import survival
    L, S = survival(np.array([1, 1, 2, 3, 3, 5]))
    # 6 spells. P(>=1)=6/6, P(>=2)=4/6, P(>=3)=3/6, P(>=5)=1/6
    np.testing.assert_array_equal(L, [1, 2, 3, 5])
    np.testing.assert_allclose(S, [1.0, 4 / 6, 3 / 6, 1 / 6])


def test_doy_anomaly_removes_seasonal_cycle():
    from cmip6_drb.diagnostics import doy_anomaly
    rng = np.random.default_rng(0)
    idx = pd.date_range("2000-01-01", "2009-12-31", freq="D")
    season = 10 * np.sin(2 * np.pi * idx.dayofyear / 365.25)
    noise = rng.standard_normal(len(idx))
    s = pd.Series(season + noise, index=idx)
    anom = doy_anomaly(s)
    assert anom.std() < 1.5  # mostly noise; large seasonal amplitude removed
    # Anomaly mean by month should be near zero (no residual seasonal trend)
    assert abs(anom.groupby(anom.index.month).mean()).max() < 0.5


def test_bh_fdr_rejects_significant_only():
    from cmip6_drb.diagnostics import bh_fdr
    p = np.array([0.001, 0.008, 0.04, 0.06, 0.5])
    rej = bh_fdr(p, alpha=0.05)
    # Step-up: largest k with p_(k) <= k/n*alpha. For n=5,alpha=0.05:
    # k=1: 0.001<=0.01 ok; k=2: 0.008<=0.02 ok; k=3: 0.04<=0.03 fail.
    # But step-up rule rejects everything ranked <= max k where condition holds.
    assert rej[0] and rej[1]
    assert not rej[3] and not rej[4]


def test_annual_maxima_drops_partial_years():
    from cmip6_drb.diagnostics import annual_maxima
    # 2000 has 366 days, 2001 has only 100 days -> dropped at 90% coverage threshold.
    idx_full = pd.date_range("2000-01-01", "2000-12-31", freq="D")
    idx_short = pd.date_range("2001-01-01", "2001-04-10", freq="D")
    idx = idx_full.append(idx_short)
    s = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    am = annual_maxima(s, min_year_coverage=0.9)
    assert 2000 in am.index
    assert 2001 not in am.index


def test_wet_day_stats_threshold_respected():
    from cmip6_drb.diagnostics import wet_day_stats
    s = pd.Series([0.0, 0.05, 0.5, 2.0, 10.0, 0.0])
    stats = wet_day_stats(s, threshold_mm=0.1)
    # 0.5, 2.0, 10.0 are wet (>= 0.1). 3 of 6.
    assert stats["p_wet"] == pytest.approx(3 / 6)
    assert stats["wet_intensity"] == pytest.approx((0.5 + 2.0 + 10.0) / 3)


def test_pairwise_wasserstein_self_zero_diag():
    from cmip6_drb.diagnostics import pairwise_wasserstein
    rng = np.random.default_rng(0)
    samples = {
        "A": rng.standard_normal(100),
        "B": rng.standard_normal(100) + 2.0,
        "C": rng.standard_normal(100) * 3,
    }
    labels, D_ = pairwise_wasserstein(samples)
    assert labels == ["A", "B", "C"]
    assert D_.shape == (3, 3)
    np.testing.assert_array_equal(np.diag(D_), [0.0, 0.0, 0.0])
    assert D_[0, 1] == D_[1, 0]
