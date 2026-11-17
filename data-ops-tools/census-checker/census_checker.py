"""Census Checker: get a benefits census ready for quoting, without leaking personal data.

Reads an employee census CSV, strips identifiers before anything leaves the machine,
checks every row against the rules a carrier quote needs, and writes:
  - census_clean.csv  quote-ready file with no SSNs, emails, phones or street addresses
  - issues.md         a client-ready summary of what to fix, grouped by severity
  - summary.json      counts for a dashboard or a Slack message

Optional: --draft-message builds the prompt for an LLM to write the client follow-up,
using only the redacted issue list. Nothing personal is ever placed in the prompt.
"""
import argparse, csv, json, re
from collections import Counter, defaultdict
from datetime import date, datetime

REQUIRED = ["employee_id", "first_name", "last_name", "dob", "sex", "zip", "state",
            "hire_date", "employment_type", "coverage_tier"]
TIERS = {"EE", "ES", "EC", "FAM", "WAIVE"}           # employee, +spouse, +child(ren), family, waived
DEP_TIERS = {"ES": {"spouse": 1, "child": 0}, "EC": {"spouse": 0, "child": 1},
             "FAM": {"spouse": 1, "child": 1}, "EE": {"spouse": 0, "child": 0}}
STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
             "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
LABELS = {"dob": "date of birth", "zip": "ZIP code", "employee_id": "employee ID"}
PII_COLUMNS = {"ssn", "email", "phone", "street_address"}
SSN_RE = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def parse_date(s):
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def age_on(dob, on):
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def scrub(text):
    """Mask SSNs and emails that slipped into free-text fields."""
    text = SSN_RE.sub("[SSN removed]", text or "")
    return EMAIL_RE.sub("[email removed]", text)


def check(rows, deps, as_of):
    issues = []   # (severity, employee_id, rule, message)
    seen = {}
    dep_count = defaultdict(Counter)
    for d in deps:
        dep_count[d.get("employee_id", "").strip()][d.get("relationship", "").strip().lower()] += 1
        dob = parse_date(d.get("dob", ""))
        if d.get("relationship", "").strip().lower() == "child" and dob and age_on(dob, as_of) >= 26:
            issues.append(("high", d["employee_id"], "child_over_26",
                           "A child dependent is 26 or older, so is usually no longer eligible."))

    for r in rows:
        eid = r.get("employee_id", "").strip() or "(no ID)"
        for f in REQUIRED:
            if not r.get(f, "").strip():
                issues.append(("high", eid, "missing_field", f"Missing {LABELS.get(f, f.replace('_', ' '))}."))
        dob, hire = parse_date(r.get("dob", "")), parse_date(r.get("hire_date", ""))
        if r.get("dob", "").strip() and not dob:
            issues.append(("high", eid, "bad_date", "Date of birth isn't a valid YYYY-MM-DD date."))
        elif dob and not 16 <= age_on(dob, as_of) <= 90:
            issues.append(("high", eid, "implausible_age", f"Age {age_on(dob, as_of)} looks wrong."))
        if hire and hire > as_of:
            issues.append(("medium", eid, "future_hire", "Hire date is in the future; confirm the start date."))
        z = r.get("zip", "").strip()
        if z and not re.fullmatch(r"\d{5}", z):
            issues.append(("high", eid, "bad_zip", f"ZIP '{z}' isn't 5 digits (often a lost leading zero)."))
        st = r.get("state", "").strip().upper()
        if st and st not in STATES:
            issues.append(("high", eid, "bad_state", f"'{st}' isn't a US state code."))
        tier = r.get("coverage_tier", "").strip().upper()
        if tier and tier not in TIERS:
            issues.append(("high", eid, "bad_tier", f"Coverage tier '{tier}' isn't EE, ES, EC, FAM or WAIVE."))
        elif tier in DEP_TIERS:
            have = dep_count[eid]
            need = DEP_TIERS[tier]
            if need["spouse"] and not have["spouse"]:
                issues.append(("medium", eid, "tier_mismatch", f"Tier {tier} needs a spouse, but none is listed."))
            if need["child"] and not have["child"]:
                issues.append(("medium", eid, "tier_mismatch", f"Tier {tier} needs a child, but none is listed."))
            if tier == "EE" and (have["spouse"] or have["child"]):
                issues.append(("medium", eid, "tier_mismatch", "Tier EE but dependents are listed."))
        if r.get("employment_type", "").strip().upper() == "PT" and tier not in ("", "WAIVE"):
            issues.append(("low", eid, "pt_enrolled", "Part-time employee enrolled; confirm plan eligibility rules."))
        key = (r.get("first_name", "").strip().lower(), r.get("last_name", "").strip().lower(), r.get("dob", "").strip())
        if all(key) and key in seen:
            issues.append(("high", eid, "duplicate", f"Looks like a duplicate of {seen[key]}."))
        elif all(key):
            seen[key] = eid
    return issues


def clean_rows(rows, as_of):
    out = []
    for r in rows:
        c = {k: v for k, v in r.items() if k.lower() not in PII_COLUMNS}
        dob = parse_date(r.get("dob", ""))
        c["age"] = age_on(dob, as_of) if dob else ""
        c["notes"] = scrub(r.get("notes", ""))
        out.append(c)
    return out


def summarize(rows, issues, as_of):
    tiers = Counter(r.get("coverage_tier", "").strip().upper() for r in rows)
    states = Counter(r.get("state", "").strip().upper() for r in rows)
    ages = [age_on(d, as_of) for d in (parse_date(r.get("dob", "")) for r in rows) if d]
    flagged = {i[1] for i in issues}
    return {"employees": len(rows), "employees_flagged": len(flagged),
            "issues_by_severity": dict(Counter(i[0] for i in issues)),
            "issues_by_rule": dict(Counter(i[2] for i in issues)),
            "tier_mix": dict(tiers), "states": dict(states),
            "average_age": round(sum(ages) / len(ages), 1) if ages else None,
            "ready_to_quote": not any(i[0] == "high" for i in issues)}


def issues_markdown(issues, summary):
    lines = [f"# Census check: {summary['employees']} employees, {summary['employees_flagged']} need a fix", ""]
    lines.append("Ready to quote." if summary["ready_to_quote"] else
                 "Not ready to quote yet. Fix the high-priority items first.")
    for sev in ("high", "medium", "low"):
        rows = [i for i in issues if i[0] == sev]
        if rows:
            lines += ["", f"## {sev.capitalize()} priority ({len(rows)})"]
            lines += [f"- {eid}: {msg}" for _, eid, _, msg in rows]
    return "\n".join(lines) + "\n"


def draft_prompt(summary, issues_md):
    return ("You are a benefits specialist writing to a startup's founder in Slack. Write a short, "
            "friendly message asking them to fix the census items below before we request quotes. "
            "Group by priority, keep employee IDs, and do not invent details.\n\n"
            f"Counts: {json.dumps(summary['issues_by_severity'])}\n\n{issues_md}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("census"); ap.add_argument("--dependents")
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--out", default="out"); ap.add_argument("--draft-message", action="store_true")
    a = ap.parse_args()
    import os
    os.makedirs(a.out, exist_ok=True)
    as_of = parse_date(a.as_of)
    rows = list(csv.DictReader(open(a.census, newline="", encoding="utf-8")))
    deps = list(csv.DictReader(open(a.dependents, newline="", encoding="utf-8"))) if a.dependents else []
    issues = check(rows, deps, as_of)
    clean = clean_rows(rows, as_of)
    with open(f"{a.out}/census_clean.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(clean[0].keys())); w.writeheader(); w.writerows(clean)
    summary = summarize(rows, issues, as_of)
    md = issues_markdown(issues, summary)
    open(f"{a.out}/issues.md", "w", encoding="utf-8").write(md)
    json.dump(summary, open(f"{a.out}/summary.json", "w"), indent=2)
    if a.draft_message:
        open(f"{a.out}/llm_prompt.txt", "w", encoding="utf-8").write(draft_prompt(summary, md))
    print(f"{summary['employees']} employees, {len(issues)} issues, ready to quote: {summary['ready_to_quote']}")


if __name__ == "__main__":
    main()
