"""Builds test episodes from real handheld motion, then plants known problems.

Motion: the TUM RGB-D ground-truth trajectories in data/real/ (a person
carrying a sensor by hand, recorded by motion capture). Only clean stretches
are used: no gaps, no repeated timestamps. Each episode is a 6 to 12 s window
cut at a random point and resampled to 50 Hz.

Simulated on top: the hand opening (aperture) for each task, collector IDs,
a short natural pause at the start and end, and the planted problems listed
in data/truth.json.

Usage: python make_test_data.py [--seed 7]
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REAL = ROOT / "data" / "real"
HZ = 50
TASKS = {
    "pick_place_cup": {"requires_grasp": True, "min_path_m": 0.2, "max_idle_head_s": 2.0, "max_idle_tail_s": 2.0,
                       "close": (0.30, 0.40), "open": (0.70, 0.80)},
    "wipe_table": {"requires_grasp": True, "min_path_m": 0.2, "max_idle_head_s": 2.0, "max_idle_tail_s": 2.0,
                   "close": (0.10, 0.15), "open": (0.85, 0.90)},
    "open_drawer": {"requires_grasp": True, "min_path_m": 0.2, "max_idle_head_s": 2.0, "max_idle_tail_s": 2.0,
                    "close": (0.35, 0.45), "open": (0.60, 0.70)},
}
COLLECTORS = [f"C{i}" for i in range(1, 9)]


def load_tum(path):
    a = np.loadtxt(path, comments="#")
    return a[:, 0], a[:, 1:4], a[:, 4:8]


def clean_stretches(t, min_len_s=13.0):
    dt = np.diff(t)
    med = np.median(dt[dt > 0])
    bad = (dt <= 0) | (dt > 3 * med)
    cuts = np.concatenate([[-1], np.where(bad)[0], [len(t) - 1]])
    out = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        lo, hi = a + 1, b
        if hi > lo and t[hi] - t[lo] >= min_len_s:
            out.append((lo, hi))
    return out


def continuous_signs(quat):
    """q and -q are the same rotation. Make neighbouring signs agree before
    interpolating, otherwise the interpolation creates a fake rotation."""
    q = quat.copy()
    for i in range(1, len(q)):
        if np.dot(q[i], q[i - 1]) < 0:
            q[i] = -q[i]
    return q


def resample(t, pos, quat, t0, dur):
    quat = continuous_signs(quat)
    tt = np.arange(0, dur, 1 / HZ) + t0
    p = np.column_stack([np.interp(tt, t, pos[:, k]) for k in range(3)])
    q = np.column_stack([np.interp(tt, t, quat[:, k]) for k in range(4)])
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    return tt - t0, p, q


def aperture(n, spec, rng):
    u = np.linspace(0, 1, n)
    c0, o0 = rng.uniform(*spec["close"]), rng.uniform(*spec["open"])
    open_w, closed_w = rng.uniform(0.07, 0.085), rng.uniform(0.01, 0.022)
    close = 1 / (1 + np.exp(-(u - c0) * 60))
    reopen = 1 / (1 + np.exp(-(u - o0) * 60))
    w = open_w - (open_w - closed_w) * (close - reopen)
    return w + rng.normal(0, 0.0008, n)


def pad_still(t, p, q, ap, head_s, tail_s):
    """Holds the first and last pose still, like a collector pausing."""
    nh, nt = int(head_s * HZ), int(tail_s * HZ)
    jitter = lambda n: np.random.default_rng(len(t) + n).normal(0, 0.0004, (n, 3))
    p = np.vstack([p[:1] + jitter(nh), p, p[-1:] + jitter(nt)])
    q = np.vstack([np.repeat(q[:1], nh, 0), q, np.repeat(q[-1:], nt, 0)])
    ap = np.concatenate([np.full(nh, ap[0]), ap, np.full(nt, ap[-1])])
    t = np.arange(len(p)) / HZ
    return t, p, q, ap


def write_episode(path, t, p, q, ap):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "x", "y", "z", "qx", "qy", "qz", "qw", "aperture"])
        for i in range(len(t)):
            w.writerow([f"{t[i]:.3f}", *(f"{v:.5f}" for v in p[i]), *(f"{v:.6f}" for v in q[i]), f"{ap[i]:.5f}"])


def plant(kind, t, p, q, ap, rng):
    n = len(t)
    if kind == "tracking_gap":
        a = int(rng.uniform(0.3, 0.6) * n)
        k = int(rng.uniform(0.3, 0.8) * HZ)
        keep = np.r_[0:a, a + k:n]
        return t[keep], p[keep], q[keep], ap[keep]
    if kind == "frozen_pose":
        a = int(rng.uniform(0.3, 0.6) * n)
        k = int(rng.uniform(0.5, 1.5) * HZ)
        p, q = p.copy(), q.copy()
        p[a:a + k] = p[a]
        q[a:a + k] = q[a]
        return t, p, q, ap
    if kind == "position_jump":
        a = int(rng.uniform(0.3, 0.7) * n)
        p = p.copy()
        p[a:] += rng.choice([-1, 1], 3) * rng.uniform(0.08, 0.2, 3)
        return t, p, q, ap
    if kind == "rotation_jump":
        a = int(rng.uniform(0.3, 0.7) * n)
        q = q.copy()
        q[a:] = q[a:][:, [3, 2, 1, 0]] * np.array([1, -1, 1, -1])
        q[a:] /= np.linalg.norm(q[a:], axis=1, keepdims=True)
        return t, p, q, ap
    if kind == "aperture_stuck":
        return t, p, q, np.full(n, rng.uniform(0.03, 0.08))
    if kind == "aperture_out_of_range":
        ap = ap.copy()
        a = int(rng.uniform(0.3, 0.7) * n)
        ap[a:a + 10] = rng.uniform(0.12, 0.2)
        return t, p, q, ap
    if kind == "no_grasp":
        return t, p, q, np.clip(ap, rng.uniform(0.045, 0.06), None)
    if kind == "too_short_path":
        c = p.mean(axis=0)
        return t, c + (p - c) * 0.03, q, ap
    if kind == "idle_tail":
        nt = int(rng.uniform(3, 6) * HZ)
        p = np.vstack([p, p[-1:] + rng.normal(0, 0.0004, (nt, 3))])
        q = np.vstack([q, np.repeat(q[-1:], nt, 0)])
        ap = np.concatenate([ap, np.full(nt, ap[-1])])
        return np.arange(len(p)) / HZ, p, q, ap
    if kind == "idle_head":
        nh = int(rng.uniform(3, 6) * HZ)
        p = np.vstack([p[:1] + rng.normal(0, 0.0004, (nh, 3)), p])
        q = np.vstack([np.repeat(q[:1], nh, 0), q])
        ap = np.concatenate([np.full(nh, ap[0]), ap])
        return np.arange(len(p)) / HZ, p, q, ap
    raise ValueError(kind)


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--seed", type=int, default=7)
    ap_.add_argument("--episodes", type=int, default=160)
    args = ap_.parse_args()
    rng = np.random.default_rng(args.seed)

    sources = []
    for name in ("freiburg1_xyz-groundtruth.txt", "fr2_desk_groundtruth.txt"):
        t, pos, quat = load_tum(REAL / name)
        for lo, hi in clean_stretches(t):
            sources.append((name, t[lo:hi + 1], pos[lo:hi + 1], quat[lo:hi + 1]))

    out = ROOT / "data"
    ep_dir = out / "episodes"
    ep_dir.mkdir(parents=True, exist_ok=True)
    for f in ep_dir.glob("*.csv"):
        f.unlink()

    task_names = list(TASKS)
    plan = []
    for i in range(args.episodes):
        plan.append({"episode_id": f"ep{i:03d}", "collector_id": COLLECTORS[i % len(COLLECTORS)],
                     "task": task_names[(i // len(COLLECTORS)) % len(task_names)], "planted": []})

    # Collector habits
    for e in plan:
        if e["collector_id"] == "C4" and rng.random() < 0.6:
            e["planted"].append("idle_tail")
        if e["collector_id"] == "C6" and rng.random() < 0.5:
            e["planted"].append("tracking_gap")
    # A task-spec problem: everyone pushes the drawer instead of gripping the handle
    for e in plan:
        if e["task"] == "open_drawer" and not e["planted"] and rng.random() < 0.4:
            e["planted"].append("no_grasp")
    # One-off faults, three of each, on otherwise clean episodes of clean collectors
    singles = ["frozen_pose", "position_jump", "rotation_jump", "aperture_stuck",
               "aperture_out_of_range", "too_short_path", "idle_head"]
    free = [e for e in plan if not e["planted"] and e["collector_id"] not in ("C4", "C6")]
    picks = rng.choice(len(free), size=3 * len(singles), replace=False)
    for k, idx in enumerate(picks):
        free[idx]["planted"].append(singles[k // 3])

    rows = []
    for e in plan:
        name, t, pos, quat = sources[rng.integers(len(sources))]
        dur = rng.uniform(6, 12)
        t0 = rng.uniform(t[0], t[-1] - dur)
        tt, p, q = resample(t, pos, quat, t0, dur)
        apv = aperture(len(tt), TASKS[e["task"]], rng)
        tt, p, q, apv = pad_still(tt, p, q, apv, rng.uniform(0.3, 1.0), rng.uniform(0.3, 1.0))
        for kind in e["planted"]:
            tt, p, q, apv = plant(kind, tt, p, q, apv, rng)
        f = f"episodes/{e['episode_id']}.csv"
        write_episode(out / f, tt, p, q, apv)
        rows.append({"episode_id": e["episode_id"], "collector_id": e["collector_id"], "task": e["task"],
                     "file": f, "source": name, "source_start": round(float(t0 - t[0]), 2)})

    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["episode_id", "collector_id", "task", "file"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in ("episode_id", "collector_id", "task", "file")})
    tasks = {k: {kk: vv for kk, vv in v.items() if kk not in ("close", "open")} for k, v in TASKS.items()}
    (out / "tasks.json").write_text(json.dumps(tasks, indent=2))
    truth = {e["episode_id"]: e["planted"] for e in plan}
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    sources_used = {r["episode_id"]: {"source": r["source"], "start_s": r["source_start"]} for r in rows}
    (out / "sources.json").write_text(json.dumps(sources_used, indent=1))
    n_planted = sum(1 for e in plan if e["planted"])
    print(f"{len(plan)} episodes from {len(sources)} clean real stretches; {n_planted} with planted problems")


if __name__ == "__main__":
    main()
