"""Scores my labels: consistency, agreement with the attackers, speed,
and where the policy wording caused trouble.

Usage: python scripts/analyze.py labels.csv [--gold reference.csv] [--out report.md]

Reference signals (from Anthropic's public red-team data):
  rating        the attacker's own 0 to 4 score of how well the attack worked
  harmlessness  a preference model's harmlessness score for the transcript
                (lower = more harmful)
Neither is ground truth. Where I disagree with them is the interesting part.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def kappa(a, b):
    """Cohen's kappa for two equal-length lists of labels."""
    n = len(a)
    if n == 0:
        return float("nan")
    cats = set(a) | set(b)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] * cb[c] for c in cats) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def auroc(scores, positives):
    """Probability a random positive scores higher than a random negative."""
    pos = [s for s, p in zip(scores, positives) if p]
    neg = [s for s, p in zip(scores, positives) if not p]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def gold_section(rows, ids, gold_path):
    """Agreement with a reference labeling, verdict by verdict."""
    gold = {r["id"]: r for r in csv.DictReader(open(gold_path, newline="", encoding="utf-8"))}
    ids = [i for i in ids if i in gold]
    mine = [rows[i]["verdict"] for i in ids]
    ref = [gold[i]["verdict"] for i in ids]
    same = sum(x == y for x, y in zip(mine, ref))
    both_yes = [i for i in ids if rows[i]["verdict"] == "yes" and gold[i]["verdict"] == "yes"]
    rule_same = sum(rows[i]["rule"] == gold[i]["rule"] for i in both_yes)
    cats = ["yes", "borderline", "no"]
    grid = Counter(zip(mine, ref))
    L = ["", "## Agreement with the reference labels", "",
         "| Measure | Result |", "| --- | ---: |",
         f"| Same verdict | {same} of {len(ids)} ({100 * same / max(len(ids), 1):.0f}%), kappa {kappa(mine, ref):.2f} |",
         f"| Same rule, where both say breaks | {rule_same} of {len(both_yes)} |", "",
         "| Me \\ Reference | breaks | borderline | doesn't |", "| --- | ---: | ---: | ---: |"]
    names = {"yes": "breaks", "borderline": "borderline", "no": "doesn't"}
    L += [f"| {names[m]} | " + " | ".join(str(grid[(m, r)]) for r in cats) + " |" for m in cats]
    diff = [i for i in ids if rows[i]["verdict"] != gold[i]["verdict"]]
    if diff:
        L += ["", "| ID | Me | Reference | Reference note |", "| --- | --- | --- | --- |"]
        L += [f"| {i} | {rows[i]['verdict']} | {gold[i]['verdict']} | {gold[i]['note']} |" for i in diff]
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels")
    ap.add_argument("--key", default=str(Path(__file__).resolve().parents[1] / "data" / "answer_key.json"))
    ap.add_argument("--gold", help="reference labels CSV to score against")
    ap.add_argument("--out")
    a = ap.parse_args()

    key = json.load(open(a.key))
    rows = {r["id"]: r for r in csv.DictReader(open(a.labels, newline="", encoding="utf-8"))}
    firsts = [i for i in rows if key[i]["repeat_of"] is None]
    repeats = [i for i in rows if key[i]["repeat_of"] is not None and key[i]["repeat_of"] in rows]

    # 1. consistency on hidden repeats
    v1 = [rows[key[i]["repeat_of"]]["verdict"] for i in repeats]
    v2 = [rows[i]["verdict"] for i in repeats]
    same = sum(x == y for x, y in zip(v1, v2))

    # 2. agreement with attacker success (rating 3 or 4 = attacker says it worked)
    mine = ["yes" if rows[i]["verdict"] == "yes" else "no" for i in firsts]
    theirs = ["yes" if key[i]["rating"] >= 3 else "no" for i in firsts]
    agree = sum(x == y for x, y in zip(mine, theirs))
    conf = Counter(zip(mine, theirs))

    # 3. does the preference model's harmlessness score separate my verdicts?
    au = auroc([-key[i]["harmlessness"] for i in firsts], [rows[i]["verdict"] == "yes" for i in firsts])

    # 4. speed
    secs = sorted(int(rows[i]["seconds"]) for i in rows if rows[i].get("seconds", "").strip())
    med = secs[len(secs) // 2] if secs else None
    total_h = sum(secs) / 3600 if secs else None

    verdicts = Counter(rows[i]["verdict"] for i in firsts)
    rules = Counter(rows[i]["rule"] for i in firsts if rows[i]["rule"])
    borderline = [(i, rows[i]["rule"], rows[i]["note"]) for i in firsts if rows[i]["verdict"] == "borderline"]
    split = [(i, key[i]["rating"], rows[i]["verdict"], rows[i]["note"]) for i, m, t in zip(firsts, mine, theirs) if m != t]

    L = ["# Policy labeling results", "",
         f"{len(firsts)} conversations labelled once, {len(repeats)} hidden repeats"
         + (f", {total_h:.1f} hours in total." if total_h is not None else ", no timings recorded."), "",
         "## Headline numbers", "",
         "| Measure | Result |", "| --- | ---: |",
         f"| Same verdict on hidden repeats | {same} of {len(repeats)} ({100 * same / max(len(repeats), 1):.0f}%), kappa {kappa(v1, v2):.2f} |",
         f"| Agreement with attackers' own success rating | {agree} of {len(firsts)} ({100 * agree / len(firsts):.0f}%), kappa {kappa(mine, theirs):.2f} |",
         f"| Harmlessness score separating my 'breaks' verdicts (AUROC) | {au:.2f} |",
         f"| Median seconds per conversation | {med if med is not None else 'not timed'} |",
         f"| Conversations per hour at that pace | {f'{3600 / max(med, 1):.0f}' if med is not None else 'not timed'} |", "",
         "## My verdicts", "",
         "| Verdict | Count |", "| --- | ---: |"]
    L += [f"| {v} | {c} |" for v, c in verdicts.most_common()]
    L += ["", "| Rule | Times cited |", "| --- | ---: |"]
    L += [f"| {r} | {c} |" for r, c in sorted(rules.items())]
    L += ["", "## Where I and the attackers disagreed", "",
          f"| | Attacker: worked | Attacker: failed |", "| --- | ---: | ---: |",
          f"| Me: breaks | {conf[('yes', 'yes')]} | {conf[('yes', 'no')]} |",
          f"| Me: doesn't / borderline | {conf[('no', 'yes')]} | {conf[('no', 'no')]} |", "",
          "| ID | Attacker rating | My verdict | My note |", "| --- | ---: | --- | --- |"]
    L += [f"| {i} | {r:.0f} | {v} | {n} |" for i, r, v, n in split]
    L += ["", "## Borderline cases: what the policy wording didn't settle", "",
          "| ID | Rule | Note |", "| --- | --- | --- |"]
    L += [f"| {i} | {r} | {n} |" for i, r, n in borderline]
    sev = Counter(rows[i].get("severity", "") for i in firsts if rows[i]["verdict"] != "no")
    if any(k for k in sev):
        L += ["", "## Severity of Breaks and Borderline verdicts", "",
              "| Severity | Count |", "| --- | ---: |"]
        L += [f"| {k} | {sev[k]} |" for k in ("1", "2", "3")]
    if a.gold:
        L += gold_section(rows, firsts, a.gold)
    text = "\n".join(L) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
