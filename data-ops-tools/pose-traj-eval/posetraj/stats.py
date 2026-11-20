"""Confidence intervals that respect sessions.

Frames from one session are correlated, so resampling frames makes an
interval look tighter than it is. Resampling whole sessions does not
(see Miller, 'Adding Error Bars to Evals', 2024, on clustered errors).
"""
import numpy as np


def cluster_bootstrap_ci(values, clusters, n_boot=2000, level=0.95, seed=0):
    """Mean of values with a CI from resampling whole clusters.

    values: per-frame (or per-item) metric values.
    clusters: same length, the session id of each value.
    Returns (mean, low, high, number_of_clusters).
    """
    values = np.asarray(values, float)
    clusters = np.asarray(clusters)
    ids = np.unique(clusters)
    sums = np.array([values[clusters == c].sum() for c in ids])
    counts = np.array([(clusters == c).sum() for c in ids])
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(ids), size=(n_boot, len(ids)))
    boot = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    alpha = (1.0 - level) / 2.0
    lo, hi = np.quantile(boot, [alpha, 1.0 - alpha])
    return float(values.mean()), float(lo), float(hi), int(len(ids))


def naive_ci(values, level=0.95):
    """Normal-approximation CI that treats every value as independent.

    Kept only to show how much narrower (and wrong) it is when values
    are clustered.
    """
    values = np.asarray(values, float)
    z = 1.959963984540054 if level == 0.95 else None
    if z is None:
        raise ValueError("only level=0.95 is supported")
    se = values.std(ddof=1) / np.sqrt(len(values))
    m = values.mean()
    return float(m), float(m - z * se), float(m + z * se)
