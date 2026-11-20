"""Fake lender data so I could test payment_timing.py against a known answer.

Borrowers get paid weekly, biweekly or on the 1st/15th, spend most of it
before the next paycheck, and about 12% hit hardship partway through.
The lender debits on a fixed due date and retries R01s 3 business days later.
Since every balance is known here, I can check which failures really would
have cleared on payday. None of this is real data.
"""
import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd


def paydays(kind, start, end, rng):
    days = []
    if kind == "weekly":
        d = start + timedelta(days=int((4 - start.weekday()) % 7))  # Fridays
        step = 7
    elif kind == "biweekly":
        d = start + timedelta(days=int((4 - start.weekday()) % 7) + int(rng.integers(0, 2)) * 7)
        step = 14
    else:  # semimonthly: 1st and 15th
        d = start
        while d <= end:
            for day in (1, 15):
                x = d.replace(day=day)
                if start <= x <= end:
                    days.append(x)
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        return sorted(set(days))
    while d <= end:
        days.append(d)
        d += timedelta(days=step)
    return days


def business_add(d, n):
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def next_business(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def simulate(borrowers=2000, months=6, seed=11):
    rng = np.random.default_rng(seed)
    start = date(2026, 1, 1)
    end = start + timedelta(days=30 * months + 20)
    rows, truth = [], {}
    for b in range(borrowers):
        kind = rng.choice(["weekly", "biweekly", "semimonthly"], p=[0.25, 0.5, 0.25])
        pay = float(rng.uniform(600, 1800)) * {"weekly": 0.5, "biweekly": 1.0, "semimonthly": 1.05}[kind]
        spend = float(rng.uniform(0.88, 1.08))  # how much of each paycheck gets spent
        installment = round(float(rng.uniform(80, 260)), 2)
        due_day = int(rng.choice([1, 5, 10, 15, 20, 25]))
        pds = paydays(kind, start, end, rng)
        pd_set = set(pds)
        # hardship: income drops to 25% from some random day
        hardship = start + timedelta(days=int(rng.integers(20, 30 * months))) if rng.random() < 0.12 else None
        # daily balance
        bal, balance = float(rng.uniform(20, 300)), {}
        gap = {"weekly": 7, "biweekly": 14, "semimonthly": 15}[kind]
        d = start
        while d <= end:
            if d in pd_set:
                bal += pay * (0.25 if hardship and d >= hardship else 1.0)
            bal -= pay * spend / gap + float(rng.normal(0, 8))
            bal = max(bal, 0.0)
            balance[d] = bal
            d += timedelta(days=1)
        closed = rng.random() < 0.006
        unauth = rng.random() < 0.002
        for m in range(months):
            month = (start.replace(day=1) + timedelta(days=31 * m)).replace(day=1)
            due = next_business(month.replace(day=due_day))
            pid = f"P{b:05d}-{m}"
            attempt, when = 1, due
            # would it have cleared on the next payday?
            nxt = next((p for p in pds if p >= due), None)
            truth[pid] = bool(nxt and balance.get(next_business(nxt), 0) >= installment)
            while attempt <= 3:
                if closed and m >= 2:
                    code = rng.choice(["R02", "R03"])
                elif unauth and m == 3 and attempt == 1:
                    code = "R10"
                elif balance.get(when, 0) < installment:
                    code = "R01"
                else:
                    code = ""
                if code:
                    rows.append([pid, f"L{b:05d}", when.isoformat(), installment, attempt, "returned", code])
                    if code != "R01":
                        break
                    attempt += 1
                    when = business_add(when, 3)
                else:
                    rows.append([pid, f"L{b:05d}", when.isoformat(), installment, attempt, "settled", ""])
                    balance[when] -= installment
                    break
    df = pd.DataFrame(rows, columns=["payment_id", "loan_id", "attempt_date", "amount",
                                     "attempt_number", "result", "return_code"])
    return df, truth


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--borrowers", type=int, default=2000)
    p.add_argument("--months", type=int, default=6)
    p.add_argument("--out", default="attempts.csv")
    a = p.parse_args()
    df, _ = simulate(a.borrowers, a.months)
    df.to_csv(a.out, index=False)
    print(f"wrote {len(df):,} attempts to {a.out}")
