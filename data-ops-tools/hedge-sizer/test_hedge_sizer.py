import json
import math
from pathlib import Path

import pytest

from hedge_sizer import implied_from_fractional, ladder, main, size_hedge, taker_fee

HERE = Path(__file__).parent


def test_fee_matches_published_examples():
    # Examples from Kalshi's fee table: 100 contracts at 50c and at 10c,
    # and a 20-contract order at 60c that rounds up.
    assert taker_fee(100, 0.50) == 1.75
    assert taker_fee(100, 0.10) == 0.63
    assert taker_fee(20, 0.60) == 0.34


def test_fee_is_symmetric_in_price():
    assert taker_fee(1000, 0.2) == taker_fee(1000, 0.8)


def test_full_hedge_gives_same_result_either_way():
    h = size_hedge(10_000_000, 1.33, 0.063, coverage=1.0)
    # Rounding up to whole contracts can only add a fraction of a pound.
    assert h.result_event_gbp == pytest.approx(h.result_no_event_gbp, abs=1.0)


def test_zero_coverage_is_unhedged():
    h = size_hedge(10_000_000, 1.33, 0.063, coverage=0.0)
    assert h.contracts == 0 and h.cost_gbp == 0
    assert h.result_event_gbp == -10_000_000


def test_contracts_round_up():
    h = size_hedge(1_000.4, 1.0, 0.5)
    assert h.contracts == 1001


def test_breakeven_is_all_in_cost_per_contract():
    h = size_hedge(5_000_000, 1.25, 0.10)
    assert h.breakeven_prob == pytest.approx(h.cost_usd / h.contracts)
    assert h.breakeven_prob > 0.10  # fees push it above the price


def test_expected_value_sign_follows_view():
    cheap = size_hedge(10_000_000, 1.33, 0.063, view_prob=0.209)
    rich = size_hedge(10_000_000, 1.33, 0.063, view_prob=0.03)
    assert cheap.expected_net_gbp > 0 > rich.expected_net_gbp


def test_block_trade_flag():
    assert size_hedge(10_000_000, 1.33, 0.063, venue_volume_usd=28_829).needs_block_trade
    assert not size_hedge(10_000, 1.33, 0.063, venue_volume_usd=28_829_000).needs_block_trade


def test_ladder_size():
    rows = ladder(1_000_000, 1.3, [0.05, 0.1, 0.2], [0.5, 1.0])
    assert len(rows) == 6
    assert all(math.isfinite(r.cost_gbp) for r in rows)


def test_bookmaker_odds():
    assert implied_from_fractional(14, 1) == pytest.approx(1 / 15)
    assert implied_from_fractional(16, 1) == pytest.approx(1 / 17)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.2])
def test_rejects_bad_price(bad):
    with pytest.raises(ValueError):
        size_hedge(1_000, 1.3, bad)


def test_cli_runs(capsys):
    assert main([str(HERE / "scenario.json")]) == 0
    out = capsys.readouterr().out
    assert "block trade needed" in out
    assert main([str(HERE / "scenario.json"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["contracts"] == 13_300_000
