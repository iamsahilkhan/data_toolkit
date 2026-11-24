"""Writes randomly generated labels so the report can be seen before any
real labeling is done. These are not real judgments.

Usage: python examples/make_demo_labels.py
"""
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
random.seed(7)
items = json.load(open(ROOT / "data" / "items.json"))
key = json.load(open(ROOT / "data" / "answer_key.json"))

rows = {}
for it in items:
    i = it["id"]
    orig = key[i]["repeat_of"]
    if orig and orig in rows and random.random() < 0.85:
        v, r = rows[orig][1], rows[orig][2]
    else:
        v = random.choices(["yes", "no", "borderline"], [3, 5, 2])[0]
        r = random.choice(["P1", "P2", "P3", "P4", "P5", "P6", "P7"]) if v != "no" else ""
    note = "demo note: random label" if v == "borderline" else ""
    rows[i] = [i, v, r, str(random.randint(1, 3)) if v != "no" else "", random.choice(["low", "medium", "high"]), note,
               random.randint(20, 120), "demo"]

out = Path(__file__).with_name("demo_labels.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "verdict", "rule", "severity", "confidence", "note", "seconds", "labelled_at"])
    w.writerows(rows[it["id"]] for it in items)
print(f"wrote {out.name} with {len(rows)} random labels")
