"""Command line.

  python -m posetraj traj --gt gt.txt --est est.txt [--align se3|sim3|none] [--hz 30]
  python -m posetraj pose --gt gt.npy --pred pred.npy [--fps 30]

Trajectory files use the TUM format. Pose files are .npy arrays of shape
(frames, 21, 3) in metres, joints in the order in posetraj/checks.py.
"""
import argparse

import numpy as np

from . import pose, trajectory, checks


def run_traj(a):
    tg, pg, qg = trajectory.read_tum(a.gt)
    te, pe, qe = trajectory.read_tum(a.est)
    ie, ig = trajectory.associate(te, tg, max_diff=a.max_diff)
    if len(ie) < 3:
        raise SystemExit("fewer than 3 matched poses; check timestamps and --max-diff")
    res = trajectory.ate(pe[ie], pg[ig], align=a.align)
    rp = trajectory.rpe(pe[ie], qe[ie], pg[ig], qg[ig], delta=a.delta)
    gaps = trajectory.tracking_gaps(te, a.hz)
    print(f"matched poses      {len(ie)} of {len(te)} estimates")
    print(f"{'ATE (' + a.align + ')':<19}rmse {res['rmse'] * 1000:.2f} mm, median {res['median'] * 1000:.2f} mm, "
          f"max {res['max'] * 1000:.2f} mm")
    if a.align == "sim3":
        print(f"scale correction   {res['scale']:.4f}")
    print(f"{'RPE (delta ' + str(a.delta) + ')':<19}trans rmse {rp['trans_rmse'] * 1000:.2f} mm, "
          f"rot rmse {rp['rot_rmse_deg']:.3f} deg")
    print(f"tracking gaps      {len(gaps)} longer than 1.5 frames at {a.hz} Hz")


def run_pose(a):
    gt = np.load(a.gt)
    pred = np.load(a.pred)
    e = pose.joint_errors(pred, gt)
    s = pose.summarize(e)
    print(f"MPJPE              mean {s['mean']:.2f} mm, median {s['median']:.2f}, p95 {s['p95']:.2f}, "
          f"max {s['max']:.2f}")
    print(f"PA-MPJPE           mean {pose.pa_mpjpe(pred, gt):.2f} mm")
    print("worst joints       " + ", ".join(f"{n} {v:.1f}" for n, v in
                                        pose.per_joint_mean(e, checks.HAND_JOINT_NAMES)[:5]))
    cv, _ = checks.hand_size_drift(pred)
    print(f"hand size drift    {cv:.2f}% variation within the sequence")
    print(f"speed spikes       {len(checks.speed_spikes(pred, a.fps))} frames over 3 m/s")


def main():
    p = argparse.ArgumentParser(prog="posetraj")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("traj", help="ATE and RPE for a TUM trajectory pair")
    t.add_argument("--gt", required=True)
    t.add_argument("--est", required=True)
    t.add_argument("--align", default="se3", choices=["se3", "sim3", "none"])
    t.add_argument("--delta", type=int, default=1)
    t.add_argument("--hz", type=float, default=30.0)
    t.add_argument("--max-diff", type=float, default=0.01)
    t.set_defaults(fn=run_traj)
    q = sub.add_parser("pose", help="MPJPE, PA-MPJPE and checks for a hand sequence")
    q.add_argument("--gt", required=True)
    q.add_argument("--pred", required=True)
    q.add_argument("--fps", type=float, default=30.0)
    q.set_defaults(fn=run_pose)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
