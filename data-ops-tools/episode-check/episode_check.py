"""Checks handheld demonstration episodes (glove or handheld-gripper data)
before they go to annotation or training.

Each episode is a CSV with columns: t, x, y, z, qx, qy, qz, qw and,
optionally, aperture (gripper or hand opening in metres). A manifest lists
every episode with its collector and task, and tasks.json says what each
task needs.

Usage:
    python episode_check.py data/manifest.csv --tasks data/tasks.json --out out
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# Thresholds. Each one is a guess to tune on real data; see the README.
GAP_FACTOR = 3.0          # a step longer than 3x the median step is a gap
GAP_REJECT_S = 0.25       # one gap this long means tracking was lost
FROZEN_REJECT_S = 0.25    # an identical pose held this long means the tracker froze
MAX_SPEED_MS = 3.0        # faster than a hand moves: a tracking jump
MAX_ROT_RADS = 20.0       # faster than a wrist turns: an orientation flip
IDLE_SPEED_MS = 0.03      # slower than this (0.5 s average) counts as still
APERTURE_MIN_M, APERTURE_MAX_M = -0.002, 0.10
APERTURE_STUCK_M = 0.002  # less range than this: the aperture sensor isn't reading
GRASP_CLOSED_M = 0.03     # the hand must close below this to have held something

REASONS = {
    "duplicate_timestamps": "Two samples share a timestamp, so speeds can't be computed there.",
    "tracking_gap": "Samples are missing: the tracker lost the hand.",
    "frozen_pose": "The pose stopped changing while time kept running: the tracker froze.",
    "position_jump": "The hand moved faster than a hand can: a tracking jump.",
    "rotation_jump": "The wrist turned faster than a wrist can: an orientation flip.",
    "aperture_out_of_range": "The hand opening reads outside what the hardware allows.",
    "aperture_stuck": "The hand opening never changed: the sensor isn't reading.",
    "no_grasp": "The task needs a grasp, but the hand never closed.",
    "too_short_path": "The hand barely moved: the task wasn't done.",
    "idle_head": "Long still stretch before the task starts: trim it.",
    "idle_tail": "Long still stretch after the task ends: trim it.",
}

COACHING = {
    "tracking_gap": "Check glove fit and keep the hand in view of the tracker; re-pair before each session.",
    "frozen_pose": "Restart tracking when the live view stops updating.",
    "position_jump": "Avoid fast swipes past reflective surfaces; recalibrate if jumps repeat.",
    "rotation_jump": "Recalibrate the wrist sensor.",
    "aperture_out_of_range": "Recalibrate the aperture sensor.",
    "aperture_stuck": "Replace or reseat the aperture sensor before the next session.",
    "no_grasp": "Re-watch the task video: the object must be held, not pushed.",
    "too_short_path": "Do the full task from the start pose before stopping.",
    "idle_head": "Start recording when ready to move, not before.",
    "idle_tail": "Stop recording as soon as the task ends.",
    "duplicate_timestamps": "Update the recorder firmware.",
}


def load_episode(path):
    """Returns t, pos (n,3), quat (n,4) and aperture (n,) or None."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    t = np.array([float(r["t"]) for r in rows])
    pos = np.array([[float(r[k]) for k in ("x", "y", "z")] for r in rows])
    quat = np.array([[float(r[k]) for k in ("qx", "qy", "qz", "qw")] for r in rows])
    ap = None
    if rows and "aperture" in rows[0] and rows[0]["aperture"] != "":
        ap = np.array([float(r["aperture"]) for r in rows])
    return t, pos, quat, ap


def _runs(mask):
    """Start and end index (inclusive) of each run of True in a boolean array."""
    runs, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _rot_angle(q1, q2):
    """Angle in radians between consecutive unit quaternions, row by row."""
    q1 = q1 / np.linalg.norm(q1, axis=1, keepdims=True)
    q2 = q2 / np.linalg.norm(q2, axis=1, keepdims=True)
    d = np.clip(np.abs(np.sum(q1 * q2, axis=1)), 0.0, 1.0)
    return 2.0 * np.arccos(d)


def smoothed_speed(t, pos, window_s=0.5):
    """Net distance moved over a centred window, divided by the window length.
    Uses net distance because summing small steps picks up sensor jitter."""
    lo = np.clip(np.searchsorted(t, t - window_s / 2), 0, len(t) - 1)
    hi = np.clip(np.searchsorted(t, t + window_s / 2) - 1, 0, len(t) - 1)
    span = t[hi] - t[lo]
    dist = np.linalg.norm(pos[hi] - pos[lo], axis=1)
    return np.where(span > 0, dist / np.where(span > 0, span, 1), 0.0)


def check_episode(t, pos, quat, ap=None, task=None):
    """Runs every check. Returns a list of issues:
    {"code", "action" (reject or trim), "start", "end", "detail"}."""
    task = task or {}
    issues = []
    dt = np.diff(t)
    if len(t) < 3:
        return [{"code": "too_short_path", "action": "reject", "start": 0.0, "end": 0.0, "detail": "under 3 samples"}]
    med = float(np.median(dt[dt > 0])) if np.any(dt > 0) else 0.0

    dup = int(np.sum(dt <= 0))
    if dup:
        issues.append({"code": "duplicate_timestamps", "action": "reject", "start": float(t[0]), "end": float(t[-1]),
                       "detail": f"{dup} repeated or backward timestamps"})

    gaps = np.where(dt > max(GAP_FACTOR * med, 0.02))[0]
    if len(gaps):
        longest = float(dt[gaps].max())
        if longest >= GAP_REJECT_S:
            i = int(gaps[np.argmax(dt[gaps])])
            issues.append({"code": "tracking_gap", "action": "reject", "start": float(t[i]), "end": float(t[i + 1]),
                           "detail": f"{len(gaps)} gaps, longest {longest:.2f} s, {float(dt[gaps].sum()):.2f} s missing"})

    same = np.all(np.diff(pos, axis=0) == 0, axis=1) & np.all(np.diff(quat, axis=0) == 0, axis=1) & (dt > 0)
    for a, b in _runs(same):
        length = float(t[b + 1] - t[a])
        if length >= FROZEN_REJECT_S:
            issues.append({"code": "frozen_pose", "action": "reject", "start": float(t[a]), "end": float(t[b + 1]),
                           "detail": f"pose unchanged for {length:.2f} s"})
            break

    ok = dt > 0
    step = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    speed = np.where(ok, step / np.where(ok, dt, 1), 0)
    fast = np.where(speed > MAX_SPEED_MS)[0]
    if len(fast):
        i = int(fast[0])
        issues.append({"code": "position_jump", "action": "reject", "start": float(t[i]), "end": float(t[i + 1]),
                       "detail": f"{len(fast)} steps over {MAX_SPEED_MS} m/s, peak {speed.max():.1f} m/s"})

    rot = np.where(ok, _rot_angle(quat[:-1], quat[1:]) / np.where(ok, dt, 1), 0)
    spin = np.where(rot > MAX_ROT_RADS)[0]
    if len(spin):
        i = int(spin[0])
        issues.append({"code": "rotation_jump", "action": "reject", "start": float(t[i]), "end": float(t[i + 1]),
                       "detail": f"peak {rot.max():.0f} rad/s"})

    path = float(step.sum())
    if path < task.get("min_path_m", 0.2):
        issues.append({"code": "too_short_path", "action": "reject", "start": float(t[0]), "end": float(t[-1]),
                       "detail": f"hand moved {path:.2f} m in total"})

    if ap is not None:
        if ap.min() < APERTURE_MIN_M or ap.max() > APERTURE_MAX_M:
            issues.append({"code": "aperture_out_of_range", "action": "reject", "start": float(t[0]), "end": float(t[-1]),
                           "detail": f"reads {ap.min():.3f} to {ap.max():.3f} m"})
        elif np.ptp(ap) < APERTURE_STUCK_M:
            issues.append({"code": "aperture_stuck", "action": "reject", "start": float(t[0]), "end": float(t[-1]),
                           "detail": f"range {np.ptp(ap) * 1000:.1f} mm over the whole episode"})
        elif task.get("requires_grasp") and ap.min() > GRASP_CLOSED_M:
            issues.append({"code": "no_grasp", "action": "reject", "start": float(t[0]), "end": float(t[-1]),
                           "detail": f"hand never closed below {GRASP_CLOSED_M * 100:.0f} cm (min {ap.min() * 100:.1f} cm)"})

    still = smoothed_speed(t, pos) < IDLE_SPEED_MS
    moving = np.where(~still)[0]
    if len(moving):
        head = float(t[moving[0]] - t[0])
        tail = float(t[-1] - t[moving[-1]])
        if head > task.get("max_idle_head_s", 2.0):
            issues.append({"code": "idle_head", "action": "trim", "start": float(t[0]), "end": float(t[moving[0]]),
                           "detail": f"{head:.1f} s still before the task; trim to {t[moving[0]] - t[0] - 0.5:.1f} s"})
        if tail > task.get("max_idle_tail_s", 2.0):
            issues.append({"code": "idle_tail", "action": "trim", "start": float(t[moving[-1]]), "end": float(t[-1]),
                           "detail": f"{tail:.1f} s still after the task; trim from {t[moving[-1]] - t[0] + 0.5:.1f} s"})
    return issues


def verdict(issues):
    actions = {i["action"] for i in issues}
    return "reject" if "reject" in actions else "trim" if "trim" in actions else "accept"


def run(manifest_path, tasks_path, out_dir):
    manifest_path = Path(manifest_path)
    tasks = json.loads(Path(tasks_path).read_text())
    rows = list(csv.DictReader(open(manifest_path, newline="")))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for r in rows:
        t, pos, quat, ap = load_episode(manifest_path.parent / r["file"])
        issues = check_episode(t, pos, quat, ap, tasks.get(r["task"], {}))
        results.append({**r, "verdict": verdict(issues), "issues": issues, "duration_s": float(t[-1] - t[0])})

    with open(out / "verdicts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["episode_id", "collector_id", "task", "verdict", "reasons", "details"])
        for r in results:
            w.writerow([r["episode_id"], r["collector_id"], r["task"], r["verdict"],
                        ";".join(i["code"] for i in r["issues"]), " | ".join(i["detail"] for i in r["issues"])])

    scorecard = collector_scorecard(results)
    (out / "collector_scorecard.md").write_text(scorecard)
    spec = task_report(results)
    (out / "task_report.md").write_text(spec)

    counts = Counter(r["verdict"] for r in results)
    reasons = Counter(i["code"] for r in results for i in r["issues"])
    summary = {"episodes": len(results), "verdicts": dict(counts), "reasons": dict(reasons),
               "usable_share": round((counts["accept"] + counts["trim"]) / max(len(results), 1), 3)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return results, summary


def collector_scorecard(results):
    by = defaultdict(list)
    for r in results:
        by[r["collector_id"]].append(r)
    overall = sum(r["verdict"] == "reject" for r in results) / max(len(results), 1)
    L = ["# Collector scorecard", "",
         f"Overall reject rate: {overall:.0%}. Collectors at more than 1.5x that rate, with at least 5 episodes, get a coaching note.", "",
         "| Collector | Episodes | Accept | Trim | Reject | Top reason | Coaching |", "| --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for c in sorted(by):
        rs = by[c]
        n = len(rs)
        v = Counter(r["verdict"] for r in rs)
        reasons = Counter(i["code"] for r in rs for i in r["issues"])
        top, k = reasons.most_common(1)[0] if reasons else ("", 0)
        flagged = n >= 5 and (v["reject"] + v["trim"]) / n > max(1.5 * overall, 0.25) and k / n >= 0.3
        L.append(f"| {c} | {n} | {v['accept']} | {v['trim']} | {v['reject']} | "
                 f"{f'{top} ({k})' if top else ''} | {COACHING.get(top, '') if flagged else ''} |")
    return "\n".join(L) + "\n"


def task_report(results, spread=0.6, rate=0.2):
    """If a problem shows up for most collectors on the same task, treat it as
    a problem with the task instructions rather than with the collectors."""
    by_task = defaultdict(list)
    for r in results:
        by_task[r["task"]].append(r)
    L = ["# Task report", "",
         f"A reason counts as a spec problem when it affects at least {rate:.0%} of a task's episodes "
         f"and at least {spread:.0%} of the collectors who did that task. Otherwise it's a collector problem.", "",
         "| Task | Reason | Episodes | Share | Collectors affected | Diagnosis |", "| --- | --- | ---: | ---: | --- | --- |"]
    for task in sorted(by_task):
        rs = by_task[task]
        collectors = {r["collector_id"] for r in rs}
        per = defaultdict(set)
        cnt = Counter()
        for r in rs:
            for code in {i["code"] for i in r["issues"]}:
                per[code].add(r["collector_id"])
                cnt[code] += 1
        for code, k in cnt.most_common():
            share = k / len(rs)
            hit = len(per[code]) / len(collectors)
            diag = "Spec problem: rewrite the task instructions" if share >= rate and hit >= spread else "Collector problem: coach individuals"
            L.append(f"| {task} | {code} | {k} | {share:.0%} | {len(per[code])} of {len(collectors)} | {diag} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    _, summary = run(a.manifest, a.tasks, a.out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
