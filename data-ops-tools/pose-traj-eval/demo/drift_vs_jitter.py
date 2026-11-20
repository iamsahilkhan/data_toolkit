"""Why ATE and RPE are reported as a pair.

Two planted failures on one synthetic camera path (60 s at 30 Hz):
  slow drift  - the estimate wanders off by about 1 mm per second
  jitter      - the estimate shakes by 4 mm every frame, with no drift
ATE (global) and RPE (frame to frame) rank them in opposite order.

If a folder of TUM files is given (for example evo's test data), the
same pair is also computed on real RGB-D SLAM estimates.

Usage: python demo/drift_vs_jitter.py [evo/test/data]
"""
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import posetraj as pt  # noqa: E402

HZ = 30
N = 60 * HZ


def ground_truth():
    t = np.arange(N) / HZ
    pos = np.stack([1.5 * np.sin(0.2 * t), 1.0 * np.sin(0.3 * t), 0.1 * np.sin(0.5 * t)], axis=1)
    quat = Rotation.from_euler("zyx", np.stack([30 * np.sin(0.2 * t), 10 * np.sin(0.4 * t),
                                                5 * np.sin(0.1 * t)], axis=1), degrees=True).as_quat()
    return t, pos, quat


def row(name, est_pos, est_quat, gt_pos, gt_quat):
    a = pt.ate(est_pos, gt_pos, align="se3")
    r = pt.rpe(est_pos, est_quat, gt_pos, gt_quat, delta=1)
    return f"| {name} | {a['rmse'] * 1000:.1f} | {r['trans_rmse'] * 1000:.2f} |"


def main(folder=None):
    rng = np.random.default_rng(3)
    t, gp, gq = ground_truth()
    direction = np.array([1.0, 0.6, 0.2]) / np.linalg.norm([1.0, 0.6, 0.2])
    # drift grows along a curved path so alignment cannot cancel it
    drift = (0.001 * t)[:, None] * direction + 0.002 * np.sin(0.05 * t)[:, None] * t[:, None] / 10
    jitter = rng.normal(0, 0.004 / np.sqrt(3), (N, 3))
    lines = ["# ATE and RPE on two planted failures", "",
             "Synthetic camera path, 60 s at 30 Hz. ATE after a rigid (SE3) alignment; "
             "RPE over one frame.", "",
             "| Estimate | ATE RMSE (mm) | RPE RMSE (mm per frame) |", "| --- | ---: | ---: |",
             row("Slow drift, no jitter", gp + drift, gq, gp, gq),
             row("Jitter, no drift", gp + jitter, gq, gp, gq), "",
             "Drift dominates ATE while barely moving RPE; jitter does the opposite. "
             "Either metric alone would pass one of these failures.", ""]

    if folder:
        f = Path(folder)
        lines += ["## Real data: TUM RGB-D benchmark", "",
                  "Real SLAM estimates against motion-capture ground truth, files from evo's test data. "
                  "ATE after SE3 alignment, RPE over one frame. Gaps = estimate timestamps more than "
                  "50 ms apart (1.5 frames at 30 Hz).", "",
                  "| Sequence and estimate | Poses matched | ATE RMSE (mm) | RPE RMSE (mm per frame) | Gaps |",
                  "| --- | ---: | ---: | ---: | ---: |"]
        for gt_name, est_name in (("freiburg1_xyz-groundtruth.txt", "freiburg1_xyz-rgbdslam.txt"),
                                  ("fr2_desk_groundtruth.txt", "fr2_desk_ORB.txt")):
            tg, pg, qg = pt.read_tum(f / gt_name)
            te, pe, qe = pt.read_tum(f / est_name)
            ie, ig = pt.associate(te, tg)
            a = pt.ate(pe[ie], pg[ig])
            r = pt.rpe(pe[ie], qe[ie], pg[ig], qg[ig])
            gaps = pt.tracking_gaps(te, expected_hz=HZ)
            lines.append(f"| {est_name} | {len(ie)} | {a['rmse'] * 1000:.1f} | "
                         f"{r['trans_rmse'] * 1000:.2f} | {len(gaps)} |")

    out = ROOT / "results" / "drift_vs_jitter.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
