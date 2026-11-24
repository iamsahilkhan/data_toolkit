"""Scores episode_check against the planted problems in data/truth.json, and
audits the two raw real sequences in data/real/ as recorded.

Usage: python evaluate.py [--out out]   (run make_test_data.py first)
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from episode_check import check_episode, run, verdict

ROOT = Path(__file__).resolve().parent


def score(results, truth):
    kinds = sorted({k for v in truth.values() for k in v})
    found = {r["episode_id"]: {i["code"] for i in r["issues"]} for r in results}
    rows = []
    for k in kinds:
        planted = [e for e, v in truth.items() if k in v]
        caught = [e for e in planted if k in found[e]]
        flagged = [e for e, codes in found.items() if k in codes]
        wrong = [e for e in flagged if not truth[e]]
        side = [e for e in flagged if truth[e] and k not in truth[e]]
        rows.append({"problem": k, "planted": len(planted), "caught": len(caught), "false_flags": len(wrong),
                     "side": len(side), "side_of": sorted({p for e in side for p in truth[e]})})
    clean = [e for e, v in truth.items() if not v]
    clean_flagged = [e for e in clean if found[e]]
    return rows, len(clean), clean_flagged


def audit_real():
    rows = []
    for name in ("freiburg1_xyz-groundtruth.txt", "fr2_desk_groundtruth.txt"):
        a = np.loadtxt(ROOT / "data" / "real" / name, comments="#")
        t, pos, quat = a[:, 0], a[:, 1:4], a[:, 4:8]
        issues = check_episode(t, pos, quat, None, {"min_path_m": 0.2, "max_idle_head_s": 2.0, "max_idle_tail_s": 2.0})
        dt = np.diff(t)
        med = float(np.median(dt[dt > 0]))
        gaps = dt > max(3 * med, 0.02)
        rows.append({"sequence": name, "seconds": round(float(t[-1] - t[0]), 1), "samples": len(t),
                     "verdict": verdict(issues), "issues": issues,
                     "gaps": int(gaps.sum()), "missing_s": round(float(dt[gaps].sum()), 2),
                     "longest_gap_s": round(float(dt.max()), 2), "duplicates": int((dt <= 0).sum())})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    out = Path(a.out)
    results, summary = run(ROOT / "data" / "manifest.csv", ROOT / "data" / "tasks.json", out)
    truth = json.loads((ROOT / "data" / "truth.json").read_text())
    rows, n_clean, clean_flagged = score(results, truth)
    real = audit_real()

    L = ["# Evaluation", "", "## Planted problems", "",
         f"{len(results)} episodes cut from real handheld motion; {sum(1 for v in truth.values() if v)} carry planted problems.", "",
         "| Problem | Planted | Caught | False flags on clean episodes | Also flagged as a knock-on effect |",
         "| --- | ---: | ---: | ---: | --- |"]
    L += [f"| {r['problem']} | {r['planted']} | {r['caught']} | {r['false_flags']} | "
          + (f"{r['side']} ({', '.join(r['side_of'])})" if r["side"] else "") + " |" for r in rows]
    L += ["", f"Clean episodes flagged for anything: {len(clean_flagged)} of {n_clean}"
          + (f" ({', '.join(clean_flagged)})" if clean_flagged else "") + ".", "",
          "## Raw real sequences, as recorded", "",
          "| Sequence | Seconds | Samples | Gaps | Missing | Longest gap | Duplicate timestamps | Verdict |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for r in real:
        L.append(f"| {r['sequence']} | {r['seconds']} | {r['samples']} | {r['gaps']} | {r['missing_s']} s | "
                 f"{r['longest_gap_s']} s | {r['duplicates']} | {r['verdict']} |")
    L += [""]
    for r in real:
        for i in r["issues"]:
            L.append(f"- {r['sequence']}: {i['code']}, {i['detail']}")
    text = "\n".join(L) + "\n"
    (out / "evaluation.md").write_text(text)
    print(text)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
