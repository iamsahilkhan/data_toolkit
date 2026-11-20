"""Checks the report's timing-fixable count against the simulator's truth."""
import pandas as pd

from payment_timing import timing_fixable
from simulate import simulate

df, truth = simulate()
df["attempt_date"] = pd.to_datetime(df["attempt_date"])
df["return_code"] = df["return_code"].fillna("")
tf = timing_fixable(df, window=10)
first = df[df["attempt_number"] == 1]
nsf = set(first[(first["result"] == "returned") & (first["return_code"] == "R01")]["payment_id"])
true_fix = {p for p in nsf if truth[p]}
est = tf["fixable_ids"]
tp = len(est & true_fix)
print(f"First debits failed for insufficient funds: {len(nsf)}")
print(f"Truly timing-fixable (cleared on next payday): {len(true_fix)}")
print(f"Report's estimate from attempts alone: {len(est)}")
print(f"Precision: {tp / max(len(est), 1):.1%}  (estimated fixable that truly were)")
print(f"Recall: {tp / max(len(true_fix), 1):.1%}  (truly fixable that the report found)")
