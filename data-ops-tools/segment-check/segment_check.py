"""Segment Check: QA for time-stamped subtask labels (reach, grasp, transport, ...).

Checks labels against ontology.json, compares each annotator to gold episodes, and ranks
boundaries that annotators place inconsistently. Left and right hands are separate tracks.
See README.md for inputs and outputs.
"""
import argparse, csv, json, os, statistics as st
from collections import Counter, defaultdict
from itertools import combinations

TOL = 0.05          # seconds of slack for bounds and overlaps
MATCH_WINDOW = 1.0  # max distance between a gold boundary and an annotator boundary
BIAS_FLAG = 0.2     # seconds of average lateness or earliness worth a coaching note
CONFUSION_FLAG = 0.2
MIN_N = 10
ADJUDICATE_BELOW = 0.85


HANDS = {"both": ["left", "right"], "left": ["left"], "right": ["right"]}


def hand_of(row):
    return (row.get("hand") or "right").strip().lower()


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def segments(rows):
    segs = sorted(({"start": float(r["start"]), "end": float(r["end"]), "label": r["label"].strip(),
                    "object": r.get("object", "").strip()} for r in rows), key=lambda s: s["start"])
    return segs


def boundaries(segs):
    """Each boundary: time, label before, label after, object of the interaction."""
    out = []
    for a, b in zip(segs, segs[1:]):
        out.append({"t": b["start"], "prev": a["label"], "next": b["label"],
                    "object": b["object"] if b["label"] != "idle" else a["object"]})
    return out


def check_rules(segs, duration, onto):
    issues = []
    labels, trans, min_d = onto["labels"], onto["transitions"], onto["min_duration_s"]
    for s in segs:
        if s["label"] not in labels:
            issues.append(("unknown_label", f"'{s['label']}' is not in ontology {onto['version']}."))
        if s["start"] < -TOL or s["end"] > duration + TOL:
            issues.append(("out_of_bounds", f"{s['label']} {s['start']:.2f}-{s['end']:.2f}s falls outside the {duration:.2f}s episode."))
        if s["end"] - s["start"] < min_d:
            issues.append(("too_short", f"{s['label']} lasts {s['end'] - s['start']:.2f}s, under the {min_d}s minimum."))
    for a, b in zip(segs, segs[1:]):
        if b["start"] < a["end"] - TOL:
            issues.append(("overlap", f"{b['label']} starts at {b['start']:.2f}s before {a['label']} ends at {a['end']:.2f}s."))
        if a["label"] in trans and b["label"] in labels and b["label"] not in trans[a["label"]]:
            issues.append(("bad_transition", f"{a['label']} is followed by {b['label']}, which the ontology does not allow."))
    return issues


def label_at(segs, t):
    for s in segs:
        if s["start"] <= t < s["end"]:
            return s["label"]
    return None


def agreement(a, b, duration, step=0.1):
    n = int(duration / step)
    same = sum(label_at(a, i * step) == label_at(b, i * step) for i in range(n))
    return same / n if n else 1.0


def pair_agreement(a, b, duration):
    """Average agreement over the hands both annotators labeled."""
    hands = sorted(set(a) & set(b))
    return st.mean(agreement(a[h], b[h], duration) for h in hands) if hands else 0.0


def shifted(segs, by):
    return [dict(s, start=s["start"] - by, end=s["end"] - by) for s in segs]


def compare_to_gold(gold, ann):
    """Returns (label pairs for each gold segment, boundary offsets)."""
    pairs = []
    for g in gold:
        if g["label"] == "idle":
            continue
        best = max(ann, key=lambda s: min(s["end"], g["end"]) - max(s["start"], g["start"]), default=None)
        pairs.append((g["label"], best["label"] if best else None))
    offsets = []
    ab = boundaries(ann)
    for gb in boundaries(gold):
        cands = [x for x in ab if x["prev"] == gb["prev"] and x["next"] == gb["next"]
                 and abs(x["t"] - gb["t"]) <= MATCH_WINDOW]
        if cands:
            near = min(cands, key=lambda x: abs(x["t"] - gb["t"]))
            offsets.append((gb, near["t"] - gb["t"]))
    return pairs, offsets


def run(episodes, annotations, gold_rows, onto):
    dur = {e["episode_id"]: float(e["duration"]) for e in episodes}
    expected = {e["episode_id"]: HANDS.get(e.get("hands", "right"), ["right"]) for e in episodes}
    # one track per hand, hands can overlap in time
    by_ep = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in annotations:
        by_ep[r["episode_id"]][r["annotator_id"]][hand_of(r)].append(r)
    gold = defaultdict(list)
    for r in gold_rows:
        gold[(r["episode_id"], hand_of(r))].append(r)
    gold = {k: segments(v) for k, v in gold.items()}

    issues, adjud = [], []
    confusion = defaultdict(lambda: defaultdict(Counter))
    offsets = defaultdict(list)       # annotator -> [(gold boundary, offset)]
    gold_sets = []
    all_segs = {}
    for ep, anns in by_ep.items():
        segs = {a: {h: segments(rows) for h, rows in tracks.items()} for a, tracks in anns.items()}
        for a, tracks in segs.items():
            for h in expected[ep]:
                if h not in tracks:
                    issues.append({"episode_id": ep, "annotator_id": a, "hand": h, "rule": "missing_track",
                                   "detail": f"No labels for the {h} hand in a two-hand episode."})
            for h, s in tracks.items():
                for rule, msg in check_rules(s, dur[ep], onto):
                    issues.append({"episode_id": ep, "annotator_id": a, "hand": h, "rule": rule, "detail": msg})
                if (ep, h) in gold:
                    offsets[a].extend(compare_to_gold(gold[(ep, h)], s)[1])
                    gold_sets.append(((ep, h), a, s))
        all_segs[ep] = segs

    # shift by each annotator's avg offset first, otherwise a late annotator
    # also shows up as confusing short segments
    bias = {a: st.mean([o for _, o in v]) for a, v in offsets.items() if v}
    for ep, a, s in gold_sets:
        for gl, al in compare_to_gold(gold[ep], shifted(s, bias.get(a, 0.0)))[0]:
            confusion[a][gl][al] += 1

    notes = {}
    for a in sorted(set(confusion) | set(offsets)):
        flags = []
        offs = [o for _, o in offsets[a]]
        if len(offs) >= MIN_N and abs(st.mean(offs)) >= BIAS_FLAG:
            m = st.mean(offs)
            flags.append({"type": "timing_bias", "direction": "late" if m > 0 else "early",
                          "seconds": round(abs(m), 2), "n": len(offs),
                          "note": f"Marks boundaries {abs(m):.2f}s {'late' if m > 0 else 'early'} on average ({len(offs)} boundaries)."})
        for gl, c in confusion[a].items():
            n = sum(c.values())
            for al, k in c.items():
                if al != gl and n >= MIN_N and k / n >= CONFUSION_FLAG:
                    flags.append({"type": "label_confusion", "gold": gl, "labeled_as": al, "share": round(k / n, 2), "n": n,
                                  "note": f"Labels '{gl}' as '{al}' in {k / n:.0%} of cases ({k} of {n})."})
        notes[a] = flags

    # adjudicate using unflagged annotators only; flagged work goes to relabel
    flagged = {a for a, f in notes.items() if f}
    for ep, segs in all_segs.items():
        good = sorted(a for a in segs if a not in flagged)
        if len(good) < 2:
            adjud.append({"episode_id": ep, "action": "relabel", "lowest_agreement": "",
                          "annotators": "fewer than 2 annotators in good standing"})
            continue
        worst = min((pair_agreement(segs[x], segs[y], dur[ep]), x, y) for x, y in combinations(good, 2))
        if worst[0] < ADJUDICATE_BELOW:
            adjud.append({"episode_id": ep, "action": "adjudicate", "lowest_agreement": round(worst[0], 3),
                          "annotators": f"{worst[1]} vs {worst[2]}"})

    # guideline gaps
    spread = defaultdict(list)
    for a, v in offsets.items():
        for gb, o in v:
            spread[(gb["prev"], gb["next"], gb["object"])].append(o - bias[a])
    gaps = sorted(({"boundary": f"{p} to {n}", "object": obj, "n": len(v), "spread_s": round(st.pstdev(v), 3)}
                   for (p, n, obj), v in spread.items() if len(v) >= MIN_N), key=lambda g: -g["spread_s"])
    adjud.sort(key=lambda x: (x["action"], str(x["lowest_agreement"])))
    return issues, notes, gaps, adjud


def write_outputs(out, issues, notes, gaps, adjud, n_eps, n_ann, onto):
    os.makedirs(out, exist_ok=True)
    with open(f"{out}/issues.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["episode_id", "annotator_id", "hand", "rule", "detail"]); w.writeheader(); w.writerows(issues)
    with open(f"{out}/adjudication.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["episode_id", "action", "lowest_agreement", "annotators"]); w.writeheader(); w.writerows(adjud)
    lines = [f"# Annotator report ({onto['version']})", "",
             "Compared against gold episodes.", ""]
    for a, flags in notes.items():
        lines.append(f"## {a}")
        lines += [f"- {x['note']}" for x in flags] or ["- No issues found against gold."]
        lines.append("")
    open(f"{out}/annotator_report.md", "w", encoding="utf-8").write("\n".join(lines))
    g = ["# Possible guideline gaps", "",
         "Spread of boundary placement across annotators, after removing each annotator's average offset.", "",
         "| Boundary | Object | Boundaries | Spread (s) |", "|---|---|---|---|"]
    g += [f"| {x['boundary']} | {x['object'] or '(none)'} | {x['n']} | {x['spread_s']} |" for x in gaps[:10]]
    open(f"{out}/guideline_gaps.md", "w", encoding="utf-8").write("\n".join(g) + "\n")
    summary = {"episodes": n_eps, "annotation_sets": n_ann,
               "rule_issues": dict(Counter(i["rule"] for i in issues)),
               "annotators_flagged": {a: [x["type"] for x in f] for a, f in notes.items() if f},
               "top_guideline_gap": gaps[0] if gaps else None,
               "episodes_to_adjudicate": sum(x["action"] == "adjudicate" for x in adjud),
               "episodes_to_relabel": sum(x["action"] == "relabel" for x in adjud)}
    json.dump(summary, open(f"{out}/summary.json", "w"), indent=2)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--episodes", default="episodes.csv"); ap.add_argument("--annotations", default="annotations.csv")
    ap.add_argument("--gold", default="gold.csv"); ap.add_argument("--ontology", default="ontology.json")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    onto = json.load(open(a.ontology))
    eps, anns, gold = load(a.episodes), load(a.annotations), load(a.gold)
    issues, notes, gaps, adjud = run(eps, anns, gold, onto)
    n_ann = len({(r["episode_id"], r["annotator_id"]) for r in anns})
    s = write_outputs(a.out, issues, notes, gaps, adjud, len(eps), n_ann, onto)
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
