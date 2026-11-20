"""Reads a CSV of debit attempts and reports how many failed payments were
really a timing problem (money showed up a few days later).

    python payment_timing.py attempts.csv --out report.md

Columns: payment_id, loan_id, attempt_date, amount, attempt_number,
result (settled/returned), return_code
"""
import argparse
from pathlib import Path

import pandas as pd

NSF_CODES = {"R01", "R09"}
ADMIN_CODES = {"R02", "R03", "R04"}
UNAUTH_CODES = {"R05", "R07", "R10", "R11", "R29", "R51"}
LEVELS = {"overall": 0.15, "administrative": 0.03, "unauthorized": 0.005}
REQUIRED = ["payment_id", "loan_id", "attempt_date", "amount", "attempt_number", "result", "return_code"]


def load(path):
    df = pd.read_csv(path, dtype={"return_code": "string", "payment_id": "string", "loan_id": "string"})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    df["attempt_date"] = pd.to_datetime(df["attempt_date"])
    df["return_code"] = df["return_code"].fillna("").str.strip().str.upper()
    df["result"] = df["result"].str.strip().str.lower()
    bad = set(df["result"]) - {"settled", "returned"}
    if bad:
        raise ValueError(f"result must be 'settled' or 'returned', found {bad}")
    if ((df["result"] == "returned") & (df["return_code"] == "")).any():
        raise ValueError("every returned attempt needs a return_code")
    return df.sort_values(["payment_id", "attempt_number"]).reset_index(drop=True)


def return_rates(df):
    # Nacha looks at 60-day windows, so report the worst one too
    ret = df["result"] == "returned"
    flags = pd.DataFrame({
        "date": df["attempt_date"],
        "overall": ret,
        "administrative": ret & df["return_code"].isin(ADMIN_CODES),
        "unauthorized": ret & df["return_code"].isin(UNAUTH_CODES),
        "nsf": ret & df["return_code"].isin(NSF_CODES),
    })
    daily = flags.groupby("date").agg(["sum", "count"])
    out = {}
    for k in ["overall", "administrative", "unauthorized", "nsf"]:
        s = daily[(k, "sum")].resample("D").sum()
        n = daily[(k, "count")].resample("D").sum()
        roll = s.rolling(60, min_periods=60).sum() / n.rolling(60, min_periods=60).sum()
        out[k] = {
            "rate": float(flags[k].mean()),
            "worst_60d": float(roll.max()) if roll.notna().any() else None,
            "count": int(flags[k].sum()),
            "level": LEVELS.get(k),
        }
    out["nsf"]["share_of_returns"] = out["nsf"]["count"] / max(out["overall"]["count"], 1)
    return out


def timing_fixable(df, window=10):
    # first try came back R01/R09 but a retry cleared within `window` days
    first = df[df["attempt_number"] == df.groupby("payment_id")["attempt_number"].transform("min")]
    nsf_first = first[(first["result"] == "returned") & first["return_code"].isin(NSF_CODES)]
    settled = df[df["result"] == "settled"].groupby("payment_id")["attempt_date"].min()
    m = nsf_first.set_index("payment_id").join(settled.rename("settled_date"), how="left")
    m["days_to_clear"] = (m["settled_date"] - m["attempt_date"]).dt.days
    fix = m[m["days_to_clear"].notna() & (m["days_to_clear"] <= window)]
    never = m[m["settled_date"].isna()]
    return {
        "nsf_first_attempts": int(len(m)),
        "fixable_count": int(len(fix)),
        "fixable_amount": float(fix["amount"].sum()),
        "median_days_to_clear": float(fix["days_to_clear"].median()) if len(fix) else None,
        "never_collected": int(len(never)),
        "fixable_ids": set(fix.index),
    }


def two_strikes(df):
    # two returns in a row on the same payment
    hits = 0
    for _, g in df.groupby("payment_id"):
        r = (g.sort_values("attempt_number")["result"] == "returned").tolist()
        if any(a and b for a, b in zip(r, r[1:])):
            hits += 1
    return hits


def when_debits_clear(df):
    # success rate of first tries by weekday / part of the month
    first = df[df["attempt_number"] == df.groupby("payment_id")["attempt_number"].transform("min")].copy()
    first["ok"] = first["result"] == "settled"
    first["weekday"] = first["attempt_date"].dt.day_name()
    dom = first["attempt_date"].dt.day
    first["day_band"] = pd.cut(dom, [0, 5, 10, 15, 20, 25, 31],
                               labels=["1 to 5", "6 to 10", "11 to 15", "16 to 20", "21 to 25", "26 to 31"])
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    wd = first.groupby("weekday")["ok"].agg(["mean", "count"]).reindex(order).dropna()
    db = first.groupby("day_band", observed=True)["ok"].agg(["mean", "count"])
    return wd, db


def report(df, window=10, nsf_fee=16.82, lender_cost=0.0):
    rr = return_rates(df)
    tf = timing_fixable(df, window)
    ts = two_strikes(df)
    wd, db = when_debits_clear(df)
    payments = df["payment_id"].nunique()
    days = (df["attempt_date"].max() - df["attempt_date"].min()).days + 1

    def pct(x):
        return "n/a" if x is None else f"{x * 100:.2f}%"

    lines = [
        "# Payment timing report", "",
        f"{len(df):,} debit attempts on {payments:,} payments over {days} days.", "",
        "## 1. Return rates against Nacha levels", "",
        "| Return type | Count | Rate, whole period | Worst 60-day window | Nacha level |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    names = {"overall": "Overall (all codes)", "administrative": "Administrative (R02, R03, R04)",
             "unauthorized": "Unauthorized (R05, R07, R10, R11, R29, R51)", "nsf": "Insufficient funds (R01, R09)"}
    for k in ["overall", "administrative", "unauthorized", "nsf"]:
        r = rr[k]
        level = "not separately monitored" if r["level"] is None else pct(r["level"])
        lines.append(f"| {names[k]} | {r['count']:,} | {pct(r['rate'])} | {pct(r['worst_60d'])} | {level} |")
    lines += ["", f"Insufficient funds caused {rr['nsf']['share_of_returns'] * 100:.0f}% of all returns.", ""]

    lines += [
        "## 2. Timing-fixable failures", "",
        f"- First attempts returned for insufficient funds: **{tf['nsf_first_attempts']:,}**",
        f"- Of those, settled on a later attempt within {window} days: **{tf['fixable_count']:,}** "
        f"(${tf['fixable_amount']:,.0f}), a median of {tf['median_days_to_clear']} days after the first try",
        f"- Never collected in this data: **{tf['never_collected']:,}**",
        "",
        "For these, the money came in a few days later. The first debit just went out too early. "
        "Note: this is a minimum. Payments that failed and were never retried can't show when the money came in.", "",
        "## 3. Two-strike exposure", "",
        f"**{ts:,}** payments had two consecutive returned attempts. Under the CFPB payment rule (in effect "
        "since March 30, 2025), a covered lender needs new borrower authorization before a third try.", "",
        "## 4. When first attempts clear", "",
        "| Weekday | Success rate | Attempts |", "| --- | ---: | ---: |",
    ]
    lines += [f"| {d} | {r['mean'] * 100:.1f}% | {int(r['count']):,} |" for d, r in wd.iterrows()]
    lines += ["", "| Day of month | Success rate | Attempts |", "| --- | ---: | ---: |"]
    lines += [f"| {d} | {r['mean'] * 100:.1f}% | {int(r['count']):,} |" for d, r in db.iterrows()]

    fees = tf["fixable_count"] * nsf_fee
    lines += ["", "## 5. What fixing the timing is worth", "",
              f"- Borrower fees avoided: {tf['fixable_count']:,} failed debits x ${nsf_fee:.2f} average NSF fee "
              f"= **${fees:,.0f}** (using Bankrate's 2025 average NSF fee, actual fees vary by bank)",
              f"- Cash collected on the first try instead of {tf['median_days_to_clear']} days later: "
              f"**${tf['fixable_amount']:,.0f}**"]
    if lender_cost:
        lines.append(f"- Lender cost avoided at ${lender_cost:.2f} per return: "
                     f"**${tf['fixable_count'] * lender_cost:,.0f}**")
    else:
        lines.append("- Lender cost per return not given; pass --lender-cost-per-return to include it")
    fixed = df[df["payment_id"].isin(tf["fixable_ids"])]
    removed_returns = int((fixed["result"] == "returned").sum())
    new_rate = (rr["overall"]["count"] - removed_returns) / (len(df) - removed_returns)
    lines.append(f"- Overall return rate if those debits had cleared first time: "
                 f"**{pct(new_rate)}** (from {pct(rr['overall']['rate'])}), "
                 f"with {removed_returns:,} returned attempts never sent")
    return "\n".join(lines) + "\n", {"rates": rr, "fixable": tf, "two_strikes": ts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--window", type=int, default=10)
    p.add_argument("--nsf-fee", type=float, default=16.82)
    p.add_argument("--lender-cost-per-return", type=float, default=0.0)
    p.add_argument("--out")
    a = p.parse_args()
    text, _ = report(load(a.csv), a.window, a.nsf_fee, a.lender_cost_per_return)
    if a.out:
        Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
