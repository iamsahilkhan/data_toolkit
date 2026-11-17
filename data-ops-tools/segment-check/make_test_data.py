"""Generate synthetic two-hand episodes + simulated annotators with planted problems.

Planted: A3 is 0.35s late, A5 labels place as release (40%), A7 merges grasp into reach (60%),
wine glass transport->place boundary is loose for everyone (+/-0.4s), plus 18 rule breaks
(3 x 6 types) on clean annotators in non-gold episodes. Set SEED to change the data.
"""
import csv, json, os, random

random.seed(int(os.environ.get("SEED", 11)))
N_EPISODES, N_GOLD = 160, 40
ANNOTATORS = [f"A{i}" for i in range(1, 9)]
CLEAN = ["A1", "A2", "A4", "A6", "A8"]
HANDS = ["left", "right"]
OBJECTS = ["plate", "cup", "bowl", "fork", "wine glass"]
DUR = {"reach": (0.6, 1.2), "grasp": (0.8, 1.4), "transport": (1.0, 2.0), "place": (1.0, 1.5), "release": (0.6, 0.9)}


def make_track(n_objects):
    segs, t = [], 0.0
    d = random.uniform(0.6, 1.0); segs.append(["idle", t, t + d, ""]); t += d
    for _ in range(n_objects):
        obj = random.choice(OBJECTS)
        for lab in ["reach", "grasp", "transport", "place", "release"]:
            d = random.uniform(*DUR[lab]); segs.append([lab, t, t + d, obj]); t += d
    d = random.uniform(0.8, 1.2); segs.append(["idle", t, t + d, ""]); t += d
    return segs, t


def make_episode():
    tracks = {"left": make_track(random.choice([1, 2])), "right": make_track(random.choice([2, 2, 3]))}
    duration = round(max(t for _, t in tracks.values()), 3)
    out = {}
    for h, (segs, t) in tracks.items():
        segs[-1][2] = duration  # pad shorter track with idle
        out[h] = segs
    return out, duration


def annotate(gold, duration, who):
    cuts = []
    for a, b in zip(gold, gold[1:]):
        t = b[1] + random.gauss(0, 0.08)
        if who == "A3":
            t += 0.35
        if a[0] == "transport" and b[0] == "place" and b[3] == "wine glass":
            t += random.uniform(-0.4, 0.4)
        cuts.append(t)
    for i in range(len(cuts)):  # keep boundaries ordered, min 0.2s apart
        cuts[i] = max(cuts[i], (cuts[i - 1] if i else 0) + 0.2)
    cuts = [min(c, duration - 0.2) for c in cuts]
    edges = [0.0] + cuts + [duration]
    labels = []
    for g in gold:
        lab = g[0]
        if who == "A5" and lab == "place" and random.random() < 0.4:
            lab = "release"
        if who == "A7" and lab == "grasp" and random.random() < 0.6:
            lab = "reach"
        labels.append(lab)
    segs = []
    for lab, s, e in zip(labels, edges, edges[1:]):
        if segs and segs[-1][0] == lab:
            segs[-1][2] = e
        else:
            segs.append([lab, s, e])
    return segs


episodes, ann_rows, gold_rows, sets = [], [], [], {}
for i in range(N_EPISODES):
    ep = f"ep{i:03d}"
    g, dur = make_episode()
    episodes.append({"episode_id": ep, "duration": dur, "hands": "both"})
    if i < N_GOLD:
        for h in HANDS:
            gold_rows += [{"episode_id": ep, "hand": h, "start": round(s, 3), "end": round(e, 3), "label": l, "object": o}
                          for l, s, e, o in g[h]]
    for who in random.sample(ANNOTATORS, 3):
        sets[(ep, who)] = {h: annotate(g[h], dur, who) for h in HANDS}

planted = {"timing_bias": ["A3"], "label_confusion": {"A5": ["place", "release"], "A7": ["grasp", "reach"]},
           "guideline_gap": ["transport to place", "wine glass"], "rules": []}
targets = [k for k in sets if k[1] in CLEAN and int(k[0][2:]) >= N_GOLD]
random.shuffle(targets)
it = iter(targets)


def plant(rule, fn):
    for _ in range(3):
        key = next(it)
        hand = random.choice(HANDS)
        fn(sets[key], hand)
        planted["rules"].append([key[0], key[1], hand, rule])


def unknown(tr, h):
    s = tr[h]; k = next(i for i, x in enumerate(s) if x[0] == "grasp"); s[k][0] = "grab"


def overlap(tr, h):
    s = tr[h]; k = next(i for i, x in enumerate(s) if x[0] == "transport"); s[k][1] -= 0.3


def out_of_bounds(tr, h):
    tr[h][-1][2] += 2.0


def too_short(tr, h):
    s = tr[h]; k = next(i for i, x in enumerate(s) if x[0] == "transport"); s[k][2] = s[k][1] + 0.1; s[k + 1][1] = s[k][2]


def bad_transition(tr, h):
    s = tr[h]; k = next(i for i, x in enumerate(s) if x[0] == "place"); s[k][0] = "reach"


def missing_track(tr, h):
    del tr[h]


for rule, fn in [("unknown_label", unknown), ("overlap", overlap), ("out_of_bounds", out_of_bounds),
                 ("too_short", too_short), ("bad_transition", bad_transition), ("missing_track", missing_track)]:
    plant(rule, fn)

for (ep, who), tracks in sets.items():
    for h, segs in tracks.items():
        ann_rows += [{"episode_id": ep, "annotator_id": who, "hand": h, "start": round(s, 3), "end": round(e, 3), "label": l}
                     for l, s, e in segs]

for name, rows in [("episodes.csv", episodes), ("annotations.csv", ann_rows), ("gold.csv", gold_rows)]:
    with open(name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
json.dump(planted, open("planted.json", "w"), indent=2)
print(f"{N_EPISODES} two-hand episodes ({N_GOLD} gold), {len(sets)} annotation sets, {len(ann_rows)} segments, "
      f"{len(planted['rules'])} planted rule breaks")
