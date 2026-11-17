"""Make a synthetic census with known, planted errors so the checker can be scored honestly.
All names, SSNs and addresses are fake. Writes census.csv, dependents.csv and planted.json."""
import csv, json, random
from datetime import date, timedelta

random.seed(7)
AS_OF = date(2026, 11, 16)
FIRST = "Ava Ben Cara Dev Eli Fay Gus Hana Ivan Jo Kai Lena Max Nia Omar Pia Quin Rui Sara Tom Uma Vik Wen Yara Zed".split()
LAST = "Patel Garcia Kim Novak Silva Okafor Rossi Chen Haddad Weber Ito Ali Moreau Berg Costa".split()
STATE_ZIP = [("CA", "94107"), ("NY", "10013"), ("TX", "78701"), ("WA", "98101"), ("MA", "02139"), ("NJ", "07302")]


def fake_ssn():
    return f"{random.randint(100, 665):03d}-{random.randint(10, 99):02d}-{random.randint(1000, 9999):04d}"


def dob_for_age(age):
    return (AS_OF - timedelta(days=int(age * 365.25) + random.randint(0, 300))).isoformat()


rows, deps = [], []
for i in range(1, 151):
    st, z = random.choice(STATE_ZIP)
    tier = random.choices(["EE", "ES", "EC", "FAM", "WAIVE"], [50, 15, 12, 13, 10])[0]
    eid = f"E{i:03d}"
    rows.append({"employee_id": eid, "first_name": random.choice(FIRST), "last_name": random.choice(LAST),
                 "ssn": fake_ssn(), "email": f"user{i}@example.com", "phone": f"555-01{i:02d}",
                 "street_address": f"{random.randint(1, 999)} Market St", "dob": dob_for_age(random.randint(22, 62)),
                 "sex": random.choice("MF"), "zip": z, "state": st,
                 "hire_date": (AS_OF - timedelta(days=random.randint(30, 1500))).isoformat(),
                 "employment_type": "FT", "coverage_tier": tier, "notes": ""})
    if tier in ("ES", "FAM"):
        deps.append({"employee_id": eid, "relationship": "spouse", "dob": dob_for_age(random.randint(24, 60))})
    if tier in ("EC", "FAM"):
        for _ in range(random.randint(1, 3)):
            deps.append({"employee_id": eid, "relationship": "child", "dob": dob_for_age(random.randint(0, 22))})

# make names unique so only planted duplicates count as duplicates
for r in rows:
    r["last_name"] = f"{r['last_name']}{r['employee_id'][1:]}"

planted = {}
pick = iter(random.sample(range(len(rows)), 60))


def plant(rule, fn, n=3):
    for _ in range(n):
        r = rows[next(pick)]
        fn(r)
        planted.setdefault(rule, []).append(r["employee_id"])


plant("missing_field", lambda r: r.update(dob=""))
plant("bad_zip", lambda r: r.update(zip="2139"))                      # lost leading zero
plant("bad_state", lambda r: r.update(state="CF"))
plant("bad_tier", lambda r: r.update(coverage_tier="EE+1"))
plant("implausible_age", lambda r: r.update(dob="1890-01-01"))
plant("future_hire", lambda r: r.update(hire_date=(AS_OF + timedelta(days=40)).isoformat()))
def make_pt_enrolled(r):
    r.update(employment_type="PT", coverage_tier="EE")
    deps[:] = [d for d in deps if d["employee_id"] != r["employee_id"]]


plant("pt_enrolled", make_pt_enrolled)


def make_fam_without_spouse(r):
    r["coverage_tier"] = "FAM"
    deps[:] = [d for d in deps if d["employee_id"] != r["employee_id"]]
    deps.append({"employee_id": r["employee_id"], "relationship": "child", "dob": dob_for_age(5)})


plant("tier_mismatch", make_fam_without_spouse)
plant("ssn_in_notes", lambda r: r.update(notes=f"Called about plan, SSN {r['ssn']} confirmed"))


def make_child_over_26(r):
    r["coverage_tier"] = "EC"
    deps[:] = [d for d in deps if d["employee_id"] != r["employee_id"]]
    deps.append({"employee_id": r["employee_id"], "relationship": "child", "dob": dob_for_age(27)})


plant("child_over_26", make_child_over_26)

# duplicates: copy 3 clean rows under new IDs
for k in range(3):
    src = rows[next(pick)]
    dup = dict(src, employee_id=f"E{151 + k:03d}", ssn=fake_ssn())
    rows.append(dup)
    planted.setdefault("duplicate", []).append(dup["employee_id"])
    for d in [d for d in deps if d["employee_id"] == src["employee_id"]]:
        deps.append(dict(d, employee_id=dup["employee_id"]))

with open("census.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
with open("dependents.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["employee_id", "relationship", "dob"]); w.writeheader(); w.writerows(deps)
json.dump(planted, open("planted.json", "w"), indent=2)
print(len(rows), "employees,", len(deps), "dependents,", sum(len(v) for v in planted.values()), "planted problems")
