import io

import pandas as pd
import pytest

import payment_timing as pt
from simulate import simulate

CSV = """payment_id,loan_id,attempt_date,amount,attempt_number,result,return_code
A,L1,2026-01-05,100,1,returned,R01
A,L1,2026-01-08,100,2,settled,
B,L2,2026-01-05,50,1,settled,
C,L3,2026-01-06,80,1,returned,R01
C,L3,2026-01-09,80,2,returned,R01
D,L4,2026-01-07,60,1,returned,R03
E,L5,2026-01-05,70,1,returned,R01
E,L5,2026-01-25,70,2,settled,
"""


def frame(text=CSV):
    return pt.load(io.StringIO(text))


def test_rates_count_each_category():
    rr = pt.return_rates(frame())
    assert rr["overall"]["count"] == 5
    assert rr["administrative"]["count"] == 1
    assert rr["unauthorized"]["count"] == 0
    assert rr["nsf"]["count"] == 4
    assert rr["overall"]["rate"] == pytest.approx(5 / 8)


def test_timing_fixable_respects_window():
    tf = pt.timing_fixable(frame(), window=10)
    assert tf["fixable_ids"] == {"A"}           # E cleared after 20 days, outside the window
    assert tf["nsf_first_attempts"] == 3        # A, C, E
    assert tf["never_collected"] == 1           # C
    assert pt.timing_fixable(frame(), window=30)["fixable_ids"] == {"A", "E"}


def test_two_strikes_needs_consecutive_returns():
    assert pt.two_strikes(frame()) == 1          # only C


def test_load_rejects_bad_rows():
    with pytest.raises(ValueError):
        frame(CSV.replace("returned,R03", "returned,"))
    with pytest.raises(ValueError):
        frame(CSV.replace("settled,\nC", "bounced,\nC"))


def test_report_mentions_fee_source_and_minimum():
    text, _ = pt.report(frame())
    assert "Bankrate" in text and "minimum" in text


def test_estimate_is_a_conservative_floor_on_simulated_lender():
    df, truth = simulate(borrowers=400, months=4, seed=5)
    df["attempt_date"] = pd.to_datetime(df["attempt_date"])
    df["return_code"] = df["return_code"].fillna("")
    est = pt.timing_fixable(df)["fixable_ids"]
    true_fix = {p for p, ok in truth.items() if ok}
    assert est, "simulation should produce some fixable failures"
    precision = len(est & true_fix) / len(est)
    assert precision > 0.95
