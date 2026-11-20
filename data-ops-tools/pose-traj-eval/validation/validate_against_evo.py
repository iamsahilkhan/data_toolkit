"""Check posetraj's ATE and RPE against evo on real TUM RGB-D trajectories.

evo (github.com/MichaelGrupp/evo) is the standard open-source tool for
trajectory evaluation. If both tools agree to numerical precision on the
same real files, the metric code is correct.

Usage: python validation/validate_against_evo.py <evo/test/data folder>
"""
import sys
from pathlib import Path

import numpy as np
from evo.core import metrics, sync
from evo.tools import file_interface

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import posetraj as pt  # noqa: E402

PAIRS = [
    ("freiburg1_xyz-groundtruth.txt", "freiburg1_xyz-rgbdslam.txt", "se3"),
    ("fr2_desk_groundtruth.txt", "fr2_desk_ORB.txt", "se3"),
    ("fr2_desk_groundtruth.txt", "fr2_desk_ORB_kf_mono.txt", "sim3"),
]


def evo_numbers(gt_path, est_path, align):
    ref = file_interface.read_tum_trajectory_file(gt_path)
    est = file_interface.read_tum_trajectory_file(est_path)
    ref, est = sync.associate_trajectories(ref, est, max_diff=0.01)
    est.align(ref, correct_scale=(align == "sim3"))
    ape = metrics.APE(metrics.PoseRelation.translation_part)
    ape.process_data((ref, est))
    rpe = metrics.RPE(metrics.PoseRelation.translation_part, delta=1,
                      delta_unit=metrics.Unit.frames, all_pairs=False)
    rpe.process_data((ref, est))
    return (ape.get_statistic(metrics.StatisticsType.rmse),
            rpe.get_statistic(metrics.StatisticsType.rmse),
            ref.num_poses)


def ours(gt_path, est_path, align):
    tg, pg, qg = pt.read_tum(gt_path)
    te, pe, qe = pt.read_tum(est_path)
    ie, ig = pt.associate(te, tg, max_diff=0.01)
    a = pt.ate(pe[ie], pg[ig], align=align)
    # RPE is invariant to a global rigid alignment, but evo computes it on
    # the aligned estimate, so align first to compare like with like.
    s, r, t = pt.align.umeyama(pe[ie], pg[ig], with_scale=(align == "sim3"))
    pos = pt.align.apply(pe[ie], s, r, t)
    from scipy.spatial.transform import Rotation
    quat = (Rotation.from_matrix(r) * Rotation.from_quat(qe[ie])).as_quat()
    rp = pt.rpe(pos, quat, pg[ig], qg[ig], delta=1)
    return a["rmse"], rp["trans_rmse"], len(ie)


def main(folder):
    folder = Path(folder)
    print(f"{'estimate':32} {'align':5} {'poses':>6} {'ATE evo (m)':>12} {'ATE ours':>10} "
          f"{'RPE evo (m)':>12} {'RPE ours':>10} {'max diff':>10}")
    worst = 0.0
    for gt, est, align in PAIRS:
        e_ate, e_rpe, n_e = evo_numbers(str(folder / gt), str(folder / est), align)
        o_ate, o_rpe, n_o = ours(str(folder / gt), str(folder / est), align)
        assert n_e == n_o, f"pose count differs: evo {n_e}, ours {n_o}"
        diff = max(abs(e_ate - o_ate), abs(e_rpe - o_rpe))
        worst = max(worst, diff)
        print(f"{est:32} {align:5} {n_o:6d} {e_ate:12.6f} {o_ate:10.6f} "
              f"{e_rpe:12.6f} {o_rpe:10.6f} {diff:10.2e}")
    print(f"\nLargest disagreement with evo: {worst:.2e} m")
    return worst


if __name__ == "__main__":
    w = main(sys.argv[1] if len(sys.argv) > 1 else "evo_test_data")
    sys.exit(0 if w < 1e-6 else 1)
