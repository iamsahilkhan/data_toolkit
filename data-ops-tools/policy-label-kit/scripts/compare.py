"""Compares two label files on the same conversations, for example the
same labels under two policy versions, or one labeler before and after
calibration.

Usage: python scripts/compare.py before.csv after.csv [--out compare.md]
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

NAMES = {"yes": "breaks", "borderline": "borderline", "no": "doesn't"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--key", default=str(Path(__file__).resolve().parents[1] / "data" / "answer_key.json"))
    ap.add_argument("--out")
    a = ap.parse_args()

    key = json.load(open(a.key))
    b = {r["id"]: r for r in csv.DictReader(open(a.before, newline="", encoding="utf-8"))}
    c = {r["id"]: r for r in csv.DictReader(open(a.after, newline="", encoding="utf-8"))}
    ids = sorted(i for i in b if i in c and key[i]["repeat_of"] is None)
    cats = ["yes", "borderline", "no"]
    vb, vc = Counter(b[i]["verdict"] for i in ids), Counter(c[i]["verdict"] for i in ids)
    grid = Counter((b[i]["verdict"], c[i]["verdict"]) for i in ids)
    changed = [i for i in ids if b[i]["verdict"] != c[i]["verdict"]]

    L = [f"# {Path(a.before).name} vs {Path(a.after).name}", "",
         f"{len(ids)} conversations (hidden repeats left out). {len(changed)} changed verdict.", "",
         "| Verdict | Before | After |", "| --- | ---: | ---: |"]
    L += [f"| {NAMES[v]} | {vb[v]} | {vc[v]} |" for v in cats]
    L += ["", "| Before \\\\ After | breaks | borderline | doesn't |", "| --- | ---: | ---: | ---: |"]
    L += [f"| {NAMES[x]} | " + " | ".join(str(grid[(x, y)]) for y in cats) + " |" for x in cats]
    L += ["", "| ID | Before | After | Note after |", "| --- | --- | --- | --- |"]
    L += [f"| {i} | {NAMES[b[i]['verdict']]} | {NAMES[c[i]['verdict']]} {c[i]['rule']} | {c[i]['note']} |" for i in changed]
    text = "\n".join(L) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
