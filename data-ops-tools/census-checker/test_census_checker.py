"""Score the checker against the planted problems. Run: python make_test_census.py && pytest -q"""
import csv, json, re, subprocess, sys
from collections import defaultdict

AS_OF = "2026-11-16"


def run():
    subprocess.run([sys.executable, "census_checker.py", "census.csv", "--dependents", "dependents.csv",
                    "--as-of", AS_OF, "--out", "out", "--draft-message"], check=True, capture_output=True)
    return json.load(open("out/summary.json")), open("out/issues.md").read()


def flagged_by_rule():
    sys.path.insert(0, ".")
    import census_checker as cc
    rows = list(csv.DictReader(open("census.csv")))
    deps = list(csv.DictReader(open("dependents.csv")))
    out = defaultdict(set)
    for sev, eid, rule, _ in cc.check(rows, deps, cc.parse_date(AS_OF)):
        out[rule].add(eid)
    return out


def test_every_planted_problem_is_caught():
    run()
    planted = json.load(open("planted.json"))
    got = flagged_by_rule()
    for rule, ids in planted.items():
        if rule == "ssn_in_notes":
            continue  # handled by redaction, checked below
        assert set(ids) <= got[rule], f"missed {rule}: {set(ids) - got[rule]}"


def test_no_false_alarms_on_clean_rows():
    planted = json.load(open("planted.json"))
    touched = {eid for ids in planted.values() for eid in ids}
    # a duplicate pair flags only the copy; the original row is clean
    got = flagged_by_rule()
    flagged = {eid for ids in got.values() for eid in ids}
    assert flagged <= touched, f"false alarms: {flagged - touched}"


def test_no_personal_identifiers_leave_the_machine():
    run()
    ssn = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    for path in ["out/census_clean.csv", "out/issues.md", "out/summary.json", "out/llm_prompt.txt"]:
        text = open(path).read()
        assert not ssn.search(text), f"SSN found in {path}"
        assert "@example.com" not in text, f"email found in {path}"
        assert "Market St" not in text, f"street address found in {path}"
        assert not re.search(r"\b555-01\d\d\b", text), f"phone number found in {path}"
