"""Builds the labeling set from Anthropic's public red-team data (hh-rlhf).

100 conversations, 20 at each attacker success rating (0 to 4), short
enough to label quickly, plus 20 hidden repeats of earlier items to
measure my own consistency. The answer key stays out of the labeling app.

Usage: python scripts/make_sample.py path/to/red_team_attempts.jsonl.gz
"""
import gzip
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

random.seed(2026)
src = sys.argv[1]
raw = gzip.open(src).read().decode()
data = json.loads(raw) if raw.lstrip().startswith("[") else [json.loads(l) for l in raw.splitlines() if l.strip()]

pool = [d for d in data if 300 <= len(d["transcript"]) <= 1800]
items = []
for r in (0.0, 1.0, 2.0, 3.0, 4.0):
    group = [d for d in pool if d["rating"] == r]
    tagged = [d for d in group if d.get("tags")]
    pick = random.sample(tagged, min(10, len(tagged)))
    rest = [d for d in group if d not in pick]
    pick += random.sample(rest, 20 - len(pick))
    items += pick
random.shuffle(items)

queue, key = [], {}
for i, d in enumerate(items):
    iid = f"c{i + 1:03d}"
    queue.append({"id": iid, "transcript": d["transcript"].strip()})
    key[iid] = {"rating": d["rating"], "harmlessness": d["min_harmlessness_score_transcript"],
                "tags": d.get("tags") or [], "task": d["task_description"], "repeat_of": None}

# 20 hidden repeats of items 1 to 60, slotted into positions 61 to 120
repeats = random.sample(queue[:60], 20)
tail = queue[60:]
for j, orig in enumerate(repeats):
    rid = f"c{101 + j:03d}"
    key[rid] = dict(key[orig["id"]], repeat_of=orig["id"])
    tail.insert(random.randint(0, len(tail)), {"id": rid, "transcript": orig["transcript"]})
queue = queue[:60] + tail

json.dump(queue, open(ROOT / "data" / "items.json", "w"), indent=1)
json.dump(key, open(ROOT / "data" / "answer_key.json", "w"), indent=1)
print(f"{len(queue)} items to label ({len(repeats)} are hidden repeats)")
