import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from episode_check import check_episode, smoothed_speed, task_report, verdict  # noqa: E402

TASK = {"requires_grasp": True, "min_path_m": 0.2, "max_idle_head_s": 2.0, "max_idle_tail_s": 2.0}


def clean(n=500, hz=50):
    t = np.arange(n) / hz
    pos = np.column_stack([0.3 * np.sin(t), 0.2 * np.cos(0.7 * t), 0.05 * t])
    quat = np.tile([0.0, 0.0, 0.0, 1.0], (n, 1))
    ap = 0.08 - 0.06 * ((t > 3) & (t < 7))
    return t, pos, quat, ap


def codes(issues):
    return {i["code"] for i in issues}


def test_clean_episode_is_accepted():
    assert check_episode(*clean(), TASK) == []


def test_gap_frozen_and_jumps():
    t, p, q, a = clean()
    keep = np.r_[0:200, 230:500]
    assert "tracking_gap" in codes(check_episode(t[keep], p[keep], q[keep], a[keep], TASK))
    p2 = p.copy()
    p2[200:240] = p2[200]
    assert "frozen_pose" in codes(check_episode(t, p2, q, a, TASK))
    p3 = p.copy()
    p3[300:] += 0.2
    assert "position_jump" in codes(check_episode(t, p3, q, a, TASK))
    q4 = q.copy()
    q4[300:] = [1.0, 0.0, 0.0, 0.0]
    assert "rotation_jump" in codes(check_episode(t, p, q4, a, TASK))


def test_sign_flipped_quaternion_is_not_a_jump():
    t, p, q, a = clean()
    q2 = q.copy()
    q2[250:] *= -1  # same rotation, opposite sign
    assert "rotation_jump" not in codes(check_episode(t, p, q2, a, TASK))


def test_aperture_checks():
    t, p, q, a = clean()
    assert "aperture_stuck" in codes(check_episode(t, p, q, np.full_like(a, 0.05), TASK))
    bad = a.copy()
    bad[100] = 0.15
    assert "aperture_out_of_range" in codes(check_episode(t, p, q, bad, TASK))
    assert "no_grasp" in codes(check_episode(t, p, q, np.clip(a, 0.05, None), TASK))
    assert "no_grasp" not in codes(check_episode(t, p, q, np.clip(a, 0.05, None), {**TASK, "requires_grasp": False}))


def test_idle_ignores_jitter_and_trims():
    t, p, q, a = clean()
    rng = np.random.default_rng(0)
    still = p[-1] + rng.normal(0, 0.0004, (200, 3))  # 4 s of a still, jittery hand
    p2 = np.vstack([p, still])
    t2 = np.arange(len(p2)) / 50
    q2 = np.tile(q[:1], (len(p2), 1))
    a2 = np.concatenate([a, np.full(200, a[-1])])
    issues = check_episode(t2, p2, q2, a2, TASK)
    assert codes(issues) == {"idle_tail"}
    assert verdict(issues) == "trim"
    assert smoothed_speed(t2, p2)[-50:].max() < 0.03


def test_short_path_and_duplicates():
    t, p, q, a = clean()
    assert "too_short_path" in codes(check_episode(t, p * 0.01, q, a, TASK))
    t2 = t.copy()
    t2[100] = t2[99]
    assert "duplicate_timestamps" in codes(check_episode(t2, p, q, a, TASK))


def test_spec_problem_vs_collector_problem():
    issue = lambda c: [{"code": c, "action": "reject", "start": 0, "end": 0, "detail": ""}]
    results = [{"task": "drawer", "collector_id": f"C{i}", "issues": issue("no_grasp") if i < 6 else []} for i in range(8)]
    results += [{"task": "cup", "collector_id": "C1", "issues": issue("tracking_gap")} for _ in range(5)]
    results += [{"task": "cup", "collector_id": f"C{i}", "issues": []} for i in range(2, 9)]
    rep = task_report(results)
    assert "| drawer | no_grasp | 6 | 75% | 6 of 8 | Spec problem" in rep
    assert "| cup | tracking_gap | 5 | 42% | 1 of 8 | Collector problem" in rep


@pytest.mark.parametrize("seed", [1, 2, 3, 7])
def test_end_to_end_catches_every_planted_problem(seed, tmp_path):
    subprocess.run([sys.executable, str(ROOT / "make_test_data.py"), "--seed", str(seed)], check=True, capture_output=True)
    subprocess.run([sys.executable, str(ROOT / "evaluate.py"), "--out", str(tmp_path)], check=True, capture_output=True, cwd=ROOT)
    text = (tmp_path / "evaluation.md").read_text()
    truth = json.loads((ROOT / "data" / "truth.json").read_text())
    for kind in {k for v in truth.values() for k in v}:
        n = sum(kind in v for v in truth.values())
        assert f"| {kind} | {n} | {n} |" in text, kind
    assert "| fr2_desk_groundtruth.txt | 99.4 | 20957 |" in text
    assert "11.99 s" in text
    subprocess.run([sys.executable, str(ROOT / "make_test_data.py")], check=True, capture_output=True)
