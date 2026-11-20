"""Camera trajectory metrics: ATE and RPE, as defined for the TUM RGB-D
benchmark (Sturm et al., IROS 2012).

ATE: align the estimate to ground truth once, then measure the absolute
     position error at every timestamp. Catches global drift.
RPE: compare the motion between frame i and frame i + delta. Catches
     local jitter and drift rate, and ignores where the trajectory started.
"""
import numpy as np
from scipy.spatial.transform import Rotation

from .align import umeyama, apply


def read_tum(path):
    """Read a TUM file: 'timestamp tx ty tz qx qy qz qw' per line.

    Returns (timestamps (N,), positions (N, 3), quaternions xyzw (N, 4)).
    """
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            vals = line.replace(",", " ").split()
            if len(vals) != 8:
                raise ValueError(f"{path}: expected 8 columns, got {len(vals)}")
            rows.append([float(v) for v in vals])
    a = np.array(rows)
    order = np.argsort(a[:, 0])
    a = a[order]
    return a[:, 0], a[:, 1:4], a[:, 4:8]


def associate(t_est, t_gt, max_diff=0.01):
    """Match each estimate timestamp to the nearest ground-truth one.

    Pairs further apart than max_diff seconds are dropped, and each
    ground-truth pose is used at most once.
    Returns two index arrays (into est, into gt).
    """
    idx = np.searchsorted(t_gt, t_est)
    idx = np.clip(idx, 1, len(t_gt) - 1)
    left = t_gt[idx - 1]
    right = t_gt[idx]
    nearest = np.where(np.abs(t_est - left) <= np.abs(t_est - right), idx - 1, idx)
    diff = np.abs(t_gt[nearest] - t_est)
    keep = diff <= max_diff
    est_i = np.nonzero(keep)[0]
    gt_i = nearest[keep]
    _, first = np.unique(gt_i, return_index=True)
    first = np.sort(first)
    return est_i[first], gt_i[first]


def _poses(pos, quat):
    n = len(pos)
    T = np.tile(np.eye(4), (n, 1, 1))
    T[:, :3, :3] = Rotation.from_quat(quat).as_matrix()
    T[:, :3, 3] = pos
    return T


def ate(est_pos, gt_pos, align="se3"):
    """Absolute trajectory error on matched positions (N, 3).

    align: 'se3' (rotation + translation, for stereo or RGB-D),
           'sim3' (adds scale, for monocular SLAM), or 'none'.
    Returns dict with per-pose errors (m), rmse, mean, median, max
    and the alignment used.
    """
    est_pos = np.asarray(est_pos, float)
    gt_pos = np.asarray(gt_pos, float)
    if align == "none":
        s, r, t = 1.0, np.eye(3), np.zeros(3)
    elif align in ("se3", "sim3"):
        s, r, t = umeyama(est_pos, gt_pos, with_scale=(align == "sim3"))
    else:
        raise ValueError("align must be 'se3', 'sim3' or 'none'")
    err = np.linalg.norm(apply(est_pos, s, r, t) - gt_pos, axis=1)
    return {
        "errors": err,
        "rmse": float(np.sqrt((err ** 2).mean())),
        "mean": float(err.mean()),
        "median": float(np.median(err)),
        "max": float(err.max()),
        "scale": float(s),
    }


def rpe(est_pos, est_quat, gt_pos, gt_quat, delta=1):
    """Relative pose error over a fixed frame gap delta.

    E_i = (Q_i^-1 Q_{i+d})^-1 (P_i^-1 P_{i+d}), with Q ground truth and
    P the estimate. Returns translational errors (m) and rotational
    errors (degrees) with their RMSE.
    """
    P = _poses(est_pos, est_quat)
    Q = _poses(gt_pos, gt_quat)
    n = len(P) - delta
    if n < 1:
        raise ValueError("trajectory shorter than delta")
    trans = np.empty(n)
    rot = np.empty(n)
    for i in range(n):
        dq = np.linalg.inv(Q[i]) @ Q[i + delta]
        dp = np.linalg.inv(P[i]) @ P[i + delta]
        e = np.linalg.inv(dq) @ dp
        trans[i] = np.linalg.norm(e[:3, 3])
        cos = np.clip((np.trace(e[:3, :3]) - 1.0) / 2.0, -1.0, 1.0)
        rot[i] = np.degrees(np.arccos(cos))
    return {
        "trans_errors": trans,
        "rot_errors_deg": rot,
        "trans_rmse": float(np.sqrt((trans ** 2).mean())),
        "rot_rmse_deg": float(np.sqrt((rot ** 2).mean())),
    }


def tracking_gaps(timestamps, expected_hz, tolerance=1.5):
    """Find gaps longer than tolerance x the expected frame interval.

    Returns a list of (start_time, gap_seconds). A gap is a stretch where
    tracking was lost or frames were dropped.
    """
    t = np.asarray(timestamps, float)
    dt = np.diff(t)
    limit = tolerance / expected_hz
    where = np.nonzero(dt > limit)[0]
    return [(float(t[i]), float(dt[i])) for i in where]
