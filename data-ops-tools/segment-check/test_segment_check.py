"""Score Segment Check against the planted problems. Run: python make_test_data.py && pytest -q"""
import json
from collections import defaultdict
import segment_check as sc

CLEAN = {"A1", "A2", "A4", "A6", "A8"}


def results():
    onto = json.load(open("ontology.json"))
    return sc.run(sc.load("episodes.csv"), sc.load("annotations.csv"), sc.load("gold.csv"), onto)


def planted_rules():
    return json.load(open("planted.json"))["rules"]


def test_every_planted_rule_break_is_caught():
    issues, *_ = results()
    found = {(i["episode_id"], i["annotator_id"], i["hand"], i["rule"]) for i in issues}
    for ep, who, hand, rule in planted_rules():
        assert (ep, who, hand, rule) in found, f"missed {rule} for {who} {hand} hand on {ep}"


def test_no_rule_flags_on_clean_unplanted_work():
    issues, *_ = results()
    planted = {(ep, who) for ep, who, _, _ in planted_rules()}
    false = [i for i in issues if i["annotator_id"] in CLEAN and (i["episode_id"], i["annotator_id"]) not in planted]
    assert not false, false[:3]


def test_both_hands_acting_at_once_is_not_an_overlap():
    # the data really does have both hands working at the same moment...
    tracks = defaultdict(lambda: defaultdict(list))
    for r in sc.load("annotations.csv"):
        if r["annotator_id"] in CLEAN and r["label"] not in ("idle",):
            tracks[(r["episode_id"], r["annotator_id"])][r["hand"]].append((float(r["start"]), float(r["end"])))
    simultaneous = sum(1 for t in tracks.values() if "left" in t and "right" in t
                       for a in t["left"] for b in t["right"] if min(a[1], b[1]) > max(a[0], b[0]))
    assert simultaneous > 1000
    # ...and none of it is flagged as an overlap
    issues, *_ = results()
    planted = {(ep, who, hand) for ep, who, hand, rule in planted_rules() if rule == "overlap"}
    assert all((i["episode_id"], i["annotator_id"], i["hand"]) in planted for i in issues if i["rule"] == "overlap")


def test_problem_annotators_get_the_right_note():
    _, notes, *_ = results()
    assert any(f["type"] == "timing_bias" and f["direction"] == "late" for f in notes["A3"])
    assert any(f["type"] == "label_confusion" and (f["gold"], f["labeled_as"]) == ("place", "release") for f in notes["A5"])
    assert any(f["type"] == "label_confusion" and (f["gold"], f["labeled_as"]) == ("grasp", "reach") for f in notes["A7"])


def test_late_annotator_is_not_also_accused_of_label_confusion():
    _, notes, *_ = results()
    assert [f["type"] for f in notes["A3"]] == ["timing_bias"], notes["A3"]


def test_clean_annotators_get_no_notes():
    _, notes, *_ = results()
    assert all(not notes.get(a) for a in CLEAN), {a: notes.get(a) for a in CLEAN if notes.get(a)}


def test_guideline_gap_is_found_first():
    _, _, gaps, _ = results()
    assert (gaps[0]["boundary"], gaps[0]["object"]) == ("transport to place", "wine glass"), gaps[:3]
