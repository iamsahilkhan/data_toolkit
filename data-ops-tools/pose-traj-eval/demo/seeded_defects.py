"""Seeded-defect demo: which metric or check catches which defect?

Builds synthetic two-hand sessions (21 joints per hand, 30 fps), makes a
clean 'prediction' with small smooth noise, then plants one known defect
per experiment. Every metric and check runs on every experiment, and a
defect counts as caught when a number moves past what clean data shows.

The data is synthetic on purpose: only planted defects give a known
answer to score each detector against. Nothing here is real capture data.

Usage: python demo/seeded_defects.py   (writes results/seeded_defects.md)
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import posetraj as pt  # noqa: E402
from posetraj.checks import FINGERTIPS, HAND_BONES  # noqa: E402
from scipy.spatial.transform import Rotation  # noqa: E402

FPS = 30
FRAMES = 300          # 10 seconds per session
SESSIONS = 12
NOISE_MM = 2.0        # clean tracker noise, temporally smoothed

# Finger base offsets from the wrist (m) and bone lengths (m), base to tip.
BASES = np.array([[-0.030, 0.020, 0.0], [-0.020, 0.085, 0.0], [0.000, 0.090, 0.0],
                  [0.020, 0.085, 0.0], [0.038, 0.075, 0.0]])
LENGTHS = np.array([[0.035, 0.032, 0.028], [0.040, 0.025, 0.020], [0.045, 0.028, 0.022],
                    [0.042, 0.026, 0.021], [0.032, 0.020, 0.018]])


def hand_frame(curls, size):
    """One hand in its local frame: 21 joints, fingers curling in y-z."""
    j = np.zeros((21, 3))
    for f in range(5):
        base = BASES[f] * size
        j[1 + 4 * f] = base
        p = base.copy()
        ang = 0.0
        for k in range(3):
            ang += curls[f]
            p = p + size * LENGTHS[f, k] * np.array([0.0, np.cos(ang), -np.sin(ang)])
            j[2 + 4 * f + k] = p
    return j


def make_session(rng, mirror=False):
    """Ground-truth hand sequence: (FRAMES, 21, 3) in world metres."""
    size = rng.uniform(0.9, 1.1)
    phase = rng.uniform(0, 2 * np.pi, 5)
    speed = rng.uniform(0.5, 1.0)
    t = np.arange(FRAMES) / FPS
    out = np.empty((FRAMES, 21, 3))
    for i, ti in enumerate(t):
        curls = 0.35 + 0.3 * np.sin(2 * np.pi * speed * ti + phase)
        local = hand_frame(curls, size)
        if mirror:
            local[:, 0] *= -1
        rot = Rotation.from_euler("zyx", [20 * np.sin(0.5 * ti), 15 * np.sin(0.3 * ti), 10], degrees=True)
        wrist = np.array([0.15 * np.sin(0.6 * ti) + (-0.15 if mirror else 0.15),
                          0.35 + 0.05 * np.sin(0.9 * ti), 0.30])
        out[i] = rot.apply(local) + wrist
    return out


def smooth_noise(rng, shape, sd_mm, width=5):
    n = rng.normal(size=shape)
    kernel = np.ones(width) / width
    n = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode="same"), 0, n)
    return n / n.std() * sd_mm / 1000.0


def predict(rng, gt):
    """A clean prediction: smooth noise plus a small per-session offset."""
    offset = rng.normal(0, 1.5, 3) / 1000.0
    return gt + smooth_noise(rng, gt.shape, NOISE_MM) + offset


# ---- defects: each takes (pred_right, pred_left, rng) and returns new pair
def d_rotation(r, l, rng):
    rot = Rotation.from_euler("z", 15, degrees=True)
    w = r[:, :1]
    return rot.apply((r - w).reshape(-1, 3)).reshape(r.shape) + w, l


def d_scale(r, l, rng):
    w = r[:, :1]
    return (r - w) * 1.15 + w, l


def d_scale_drift(r, l, rng):
    w = r[:, :1]
    s = np.linspace(0.90, 1.15, len(r))[:, None, None]
    return (r - w) * s + w, l


def d_fingertips(r, l, rng):
    r = r.copy()
    r[:, FINGERTIPS] += rng.normal(0, 20, (len(r), len(FINGERTIPS), 3)) / 1000.0
    return r, l


def d_teleport(r, l, rng):
    r = r.copy()
    frames = rng.choice(np.arange(1, len(r) - 1), size=int(0.03 * len(r)), replace=False)
    for f in frames:
        j = rng.integers(0, 21)
        r[f, j] += rng.normal(size=3) / np.sqrt(3) * 0.15
    return r, l


def d_swap(r, l, rng):
    r, l = r.copy(), l.copy()
    for start in (60, 150, 240):
        seg = slice(start, start + 10)
        r[seg], l[seg] = l[seg].copy(), r[seg].copy()
    return r, l


DEFECTS = [
    ("Clean (no defect)", None),
    ("Whole hand rotated 15 degrees", d_rotation),
    ("Hand 15% too large", d_scale),
    ("Hand size drifts 0.90 to 1.15", d_scale_drift),
    ("Fingertip noise, 20 mm", d_fingertips),
    ("Keypoints jump 15 cm on 3% of frames", d_teleport),
    ("Left and right labels swapped, 30 frames", d_swap),
]


def measure(sessions):
    """All metrics and checks for a list of (gt_r, gt_l, pred_r, pred_l)."""
    je, pa, tips, cv, spikes, swaps, clusters = [], [], [], [], 0, 0, []
    for k, (gr, gl, pr, pl) in enumerate(sessions):
        e = pt.joint_errors(pr, gr)
        je.append(e.ravel())
        clusters.append(np.full(e.size, k))
        pa.append(pt.pa_joint_errors(pr, gr).ravel())
        tips.append(e[:, FINGERTIPS].ravel())
        c, _ = pt.checks.hand_size_drift(pr, HAND_BONES)
        cv.append(c)
        spikes += len(pt.speed_spikes(pr, FPS, max_speed=3.0))
        swaps += len(pt.left_right_swaps(pl, pr))
    je = np.concatenate(je)
    return {
        "mpjpe": float(je.mean()),
        "pa": float(np.concatenate(pa).mean()),
        "tip_p95": float(np.percentile(np.concatenate(tips), 95)),
        "bone_cv": float(np.median(cv)),
        "spikes": spikes,
        "swaps": swaps,
        "_errors": je,
        "_clusters": np.concatenate(clusters),
    }


def build(defect, seed=7):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(SESSIONS):
        gr, gl = make_session(rng), make_session(rng, mirror=True)
        pr, pl = predict(rng, gr), predict(rng, gl)
        if defect is not None:
            pr, pl = defect(pr, pl, rng)
        out.append((gr, gl, pr, pl))
    return out


def main():
    results = [(name, measure(build(fn))) for name, fn in DEFECTS]
    clean = results[0][1]
    cols = [("mpjpe", "MPJPE mean (mm)", "{:.1f}"), ("pa", "PA-MPJPE mean (mm)", "{:.1f}"),
            ("tip_p95", "Fingertip p95 (mm)", "{:.1f}"), ("bone_cv", "Hand size variation (%)", "{:.1f}"),
            ("spikes", "Speed spike frames", "{:d}"), ("swaps", "L/R swap flags", "{:d}")]

    def caught(key, v):
        base = clean[key]
        if key in ("spikes", "swaps"):
            return v > base
        return v > 1.5 * base  # moved past 1.5x the clean level

    lines = ["# Seeded-defect results", "",
             f"Synthetic data: {SESSIONS} two-hand sessions x {FRAMES} frames at {FPS} fps per experiment, "
             f"clean noise {NOISE_MM:.0f} mm. Bold = defect caught (past 1.5x the clean value, or any flags "
             "where clean data has none). Metrics need ground truth; checks do not.", "",
             "| Planted defect | " + " | ".join(c[1] for c in cols) + " |",
             "| --- | " + " | ".join("---:" for _ in cols) + " |"]
    for name, r in results:
        cells = []
        for key, _, fmt in cols:
            txt = fmt.format(r[key])
            if name != "Clean (no defect)" and caught(key, r[key]):
                txt = f"**{txt}**"
            cells.append(txt)
        lines.append(f"| {name} | " + " | ".join(cells) + " |")

    m, lo, hi, n = pt.cluster_bootstrap_ci(clean["_errors"], clean["_clusters"])
    _, nlo, nhi = pt.stats.naive_ci(clean["_errors"])
    lines += ["", "## Confidence interval on clean MPJPE", "",
              f"- Treating every joint-frame as independent: {m:.2f} mm, 95% CI {nlo:.2f} to {nhi:.2f} "
              f"(width {nhi - nlo:.3f} mm)",
              f"- Resampling whole sessions ({n} clusters): {m:.2f} mm, 95% CI {lo:.2f} to {hi:.2f} "
              f"(width {hi - lo:.3f} mm)",
              f"- The naive interval is {(hi - lo) / (nhi - nlo):.0f}x too narrow, because frames "
              "within a session share the same offset."]

    out = ROOT / "results" / "seeded_defects.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
