"""Least-squares alignment of two point sets (Umeyama, 1991).

Used by PA-MPJPE (align a predicted skeleton to ground truth) and by ATE
(align an estimated trajectory to ground truth before measuring error).
"""
import numpy as np


def umeyama(src, dst, with_scale=True):
    """Find s, R, t minimising sum ||dst_i - (s * R @ src_i + t)||^2.

    src, dst: arrays of shape (N, 3) with matching rows.
    Returns (s, R, t). With with_scale=False, s is fixed at 1 (rigid fit).
    """
    src = np.asarray(src, dtype=float)
    dst = np.asarray(dst, dtype=float)
    if src.shape != dst.shape or src.ndim != 2:
        raise ValueError("src and dst must both have shape (N, 3)")
    n = src.shape[0]
    mu_src = src.mean(axis=0)
    mu_dst = dst.mean(axis=0)
    xs = src - mu_src
    xd = dst - mu_dst
    cov = xd.T @ xs / n
    u, d, vt = np.linalg.svd(cov)
    sign = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign[2, 2] = -1.0  # avoid returning a reflection
    rot = u @ sign @ vt
    if with_scale:
        var_src = (xs ** 2).sum() / n
        scale = np.trace(np.diag(d) @ sign) / var_src
    else:
        scale = 1.0
    trans = mu_dst - scale * rot @ mu_src
    return scale, rot, trans


def apply(points, scale, rot, trans):
    """Apply s * R @ p + t to every row of points (N, 3)."""
    return scale * np.asarray(points) @ rot.T + trans
