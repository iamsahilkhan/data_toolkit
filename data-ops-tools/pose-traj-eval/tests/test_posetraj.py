import os
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import posetraj as pt  # noqa: E402
from posetraj.align import umeyama, apply  # noqa: E402

RNG = np.random.default_rng(0)
ROT = Rotation.from_euler("zyx", [30, -20, 10], degrees=True).as_matrix()


def test_umeyama_recovers_similarity():
    src = RNG.normal(size=(50, 3))
    dst = 1.7 * src @ ROT.T + np.array([0.3, -1.0, 2.0])
    s, r, t = umeyama(src, dst)
    assert s == pytest.approx(1.7)
    assert np.allclose(r, ROT)
    assert np.allclose(t, [0.3, -1.0, 2.0])


def test_umeyama_never_returns_reflection():
    src = RNG.normal(size=(20, 3))
    dst = src * np.array([1, 1, -1])  # a mirror image
    _, r, _ = umeyama(src, dst)
    assert np.linalg.det(r) == pytest.approx(1.0)


def test_pa_mpjpe_hides_rotation_and_scale_mpjpe_does_not():
    gt = RNG.normal(size=(10, 21, 3)) * 0.05
    pred = np.stack([1.2 * f @ ROT.T for f in gt])
    assert pt.pa_mpjpe(pred, gt) == pytest.approx(0.0, abs=1e-9)
    assert pt.mpjpe(pred, gt) > 10.0


def test_mpjpe_zero_on_identical_and_in_mm():
    gt = RNG.normal(size=(5, 21, 3))
    assert pt.mpjpe(gt, gt) == 0.0
    shifted = gt.copy()
    shifted[:, 1:] += np.array([0.01, 0, 0])  # every non-root joint 1 cm off
    assert pt.mpjpe(shifted, gt) == pytest.approx(10.0 * 20 / 21)


def test_ate_zero_after_rigid_transform():
    gt = np.cumsum(RNG.normal(size=(200, 3)) * 0.01, axis=0)
    est = gt @ ROT.T + 5.0
    assert pt.ate(est, gt, align="se3")["rmse"] == pytest.approx(0.0, abs=1e-9)
    assert pt.ate(est, gt, align="none")["rmse"] > 1.0


def test_ate_sim3_handles_monocular_scale():
    gt = np.cumsum(RNG.normal(size=(200, 3)) * 0.01, axis=0)
    est = 0.4 * gt @ ROT.T
    assert pt.ate(est, gt, align="se3")["rmse"] > 0.01
    res = pt.ate(est, gt, align="sim3")
    assert res["rmse"] == pytest.approx(0.0, abs=1e-9)
    assert res["scale"] == pytest.approx(2.5)


def test_rpe_zero_for_globally_moved_trajectory():
    n = 100
    gp = np.cumsum(RNG.normal(size=(n, 3)) * 0.01, axis=0)
    gq = Rotation.from_euler("z", np.linspace(0, 90, n)[:, None], degrees=True).as_quat()
    g = Rotation.from_euler("x", 40, degrees=True)
    ep = g.apply(gp) + 3.0
    eq = (g * Rotation.from_quat(gq)).as_quat()
    r = pt.rpe(ep, eq, gp, gq)
    assert r["trans_rmse"] == pytest.approx(0.0, abs=1e-9)
    assert r["rot_rmse_deg"] == pytest.approx(0.0, abs=1e-5)


def test_associate_drops_far_timestamps():
    tg = np.arange(0, 1, 0.1)
    te = np.array([0.001, 0.2005, 0.35, 0.9])
    ie, ig = pt.associate(te, tg, max_diff=0.01)
    assert ie.tolist() == [0, 1, 3]
    assert ig.tolist() == [0, 2, 9]


def test_tracking_gaps():
    t = np.r_[np.arange(0, 1, 1 / 30), np.arange(1.5, 2, 1 / 30)]
    gaps = pt.tracking_gaps(t, expected_hz=30)
    assert len(gaps) == 1 and gaps[0][1] == pytest.approx(1.5 - (29 / 30), abs=1e-6)


def test_swap_detector_finds_planted_swap():
    n = 50
    left = np.zeros((n, 21, 3)) + np.array([-0.2, 0, 0])
    right = np.zeros((n, 21, 3)) + np.array([0.2, 0, 0])
    left[20:25], right[20:25] = right[20:25].copy(), left[20:25].copy()
    assert pt.left_right_swaps(left, right) == [20, 25]


def test_speed_spikes_and_hand_size():
    seq = np.zeros((30, 21, 3))
    seq[:, :, 1] = np.linspace(0, 0.1, 21)  # a straight 10 cm "hand"
    seq[10, 5] += 0.2                       # one keypoint jumps 20 cm
    assert pt.speed_spikes(seq, fps=30, max_speed=3.0) == [10, 11]
    grow = seq.copy()
    grow[:] = np.zeros((21, 3))
    grow[:, :, 1] = np.linspace(0, 0.1, 21) * np.linspace(0.8, 1.2, 30)[:, None]
    cv, _ = pt.checks.hand_size_drift(grow)
    assert cv > 5.0


def test_cluster_ci_wider_than_naive_for_clustered_data():
    clusters = np.repeat(np.arange(10), 200)
    values = np.repeat(RNG.normal(0, 1, 10), 200) + RNG.normal(0, 0.1, 2000)
    _, lo, hi, n = pt.cluster_bootstrap_ci(values, clusters)
    _, nlo, nhi = pt.stats.naive_ci(values)
    assert n == 10
    assert (hi - lo) > 5 * (nhi - nlo)


EVO_DATA = os.environ.get("EVO_TEST_DATA")


@pytest.mark.skipif(not EVO_DATA, reason="set EVO_TEST_DATA to evo/test/data to run")
def test_matches_evo_on_real_tum_data():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
    from validate_against_evo import main
    assert main(EVO_DATA) < 1e-6
