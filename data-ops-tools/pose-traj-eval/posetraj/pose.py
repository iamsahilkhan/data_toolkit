"""3D pose error metrics: MPJPE, PA-MPJPE and per-joint error.

All inputs are arrays of shape (frames, joints, 3) in metres.
Outputs are in millimetres, the unit pose papers report.
"""
import numpy as np

from .align import umeyama, apply


def _check(pred, gt):
    pred = np.asarray(pred, dtype=float)
    gt = np.asarray(gt, dtype=float)
    if pred.shape != gt.shape or pred.ndim != 3 or pred.shape[2] != 3:
        raise ValueError("pred and gt must both have shape (frames, joints, 3)")
    return pred, gt


def joint_errors(pred, gt, root=0):
    """Root-aligned error for every joint in every frame, in mm.

    Both skeletons are shifted so the root joint (the wrist for hands,
    the pelvis for bodies) sits at the origin. Rotation and scale errors
    are kept, so this is the strict metric.
    Returns an array of shape (frames, joints).
    """
    pred, gt = _check(pred, gt)
    p = pred - pred[:, root:root + 1]
    g = gt - gt[:, root:root + 1]
    return np.linalg.norm(p - g, axis=2) * 1000.0


def pa_joint_errors(pred, gt):
    """Per-joint error after Procrustes alignment, in mm.

    Each predicted frame is rotated, translated and scaled to best fit
    the ground truth before measuring. This isolates articulation error
    and, by design, hides global rotation and scale errors.
    """
    pred, gt = _check(pred, gt)
    out = np.empty(pred.shape[:2])
    for f in range(pred.shape[0]):
        s, r, t = umeyama(pred[f], gt[f], with_scale=True)
        out[f] = np.linalg.norm(apply(pred[f], s, r, t) - gt[f], axis=1)
    return out * 1000.0


def mpjpe(pred, gt, root=0):
    """Mean per-joint position error (mm), root-aligned."""
    return float(joint_errors(pred, gt, root).mean())


def pa_mpjpe(pred, gt):
    """Procrustes-aligned MPJPE (mm)."""
    return float(pa_joint_errors(pred, gt).mean())


def summarize(errors):
    """Mean, median, 95th percentile and max of an error array (mm)."""
    e = np.asarray(errors, dtype=float).ravel()
    return {
        "mean": float(e.mean()),
        "median": float(np.median(e)),
        "p95": float(np.percentile(e, 95)),
        "max": float(e.max()),
    }


def per_joint_mean(errors, names=None):
    """Mean error per joint, worst first: list of (name, mm)."""
    m = np.asarray(errors).mean(axis=0)
    names = names or [f"joint_{i}" for i in range(len(m))]
    return sorted(zip(names, m.tolist()), key=lambda x: -x[1])
