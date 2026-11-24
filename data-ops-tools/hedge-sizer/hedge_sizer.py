"""Hedge Sizer: sizes and prices a hedge on a binary event contract.

A binary contract pays $1 if the event happens and $0 if not. A business that
loses money when the event happens can buy enough contracts for the payout to
cover the loss. Given the loss, the FX rate and the contract price, this works
out the number of contracts, the all-in cost, the result with and without the
event, the break-even probability, and whether the order is too big for the
screen and needs a block trade.

Usage:
    python hedge_sizer.py scenario.json
    python hedge_sizer.py scenario.json --json

The fee defaults to Kalshi's published taker formula,
round_up(0.07 x C x P x (1 - P)) to the next cent. Block trades can be
negotiated on different terms, so there's a fee multiplier input.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass

TAKER_RATE = 0.07
BLOCK_TRADE_SHARE = 0.10  # premium above 10% of venue volume needs a block trade


def taker_fee(contracts: int, price: float, multiplier: float = 1.0) -> float:
    """Kalshi general taker fee in dollars, rounded up to the next cent."""
    raw_cents = multiplier * TAKER_RATE * contracts * price * (1 - price) * 100
    return math.ceil(round(raw_cents, 6)) / 100


@dataclass
class Hedge:
    coverage: float
    price: float
    contracts: int
    premium_usd: float
    fee_usd: float
    cost_usd: float
    cost_gbp: float
    payout_gbp: float
    result_no_event_gbp: float
    result_event_gbp: float
    unhedged_event_gbp: float
    cost_pct_of_loss: float
    breakeven_prob: float
    expected_net_gbp: float | None
    needs_block_trade: bool | None


def size_hedge(loss_gbp: float, fx_usd_per_gbp: float, price: float,
               coverage: float = 1.0, fee_multiplier: float = 1.0,
               view_prob: float | None = None,
               venue_volume_usd: float | None = None) -> Hedge:
    """Size a hedge that covers `coverage` of `loss_gbp` if the event happens."""
    if not 0 < price < 1:
        raise ValueError("price must be between 0 and 1 dollars")
    if not 0 <= coverage <= 1.5:
        raise ValueError("coverage should be between 0 and 1.5")
    if loss_gbp < 0 or fx_usd_per_gbp <= 0:
        raise ValueError("loss must be >= 0 and fx must be > 0")

    contracts = math.ceil(round(coverage * loss_gbp * fx_usd_per_gbp, 6))
    premium = contracts * price
    fee = taker_fee(contracts, price, fee_multiplier)
    cost_usd = premium + fee
    cost_gbp = cost_usd / fx_usd_per_gbp
    payout_gbp = contracts / fx_usd_per_gbp

    breakeven = cost_usd / contracts if contracts else 0.0
    expected = None if view_prob is None else view_prob * payout_gbp - cost_gbp
    block = None if venue_volume_usd is None else premium > BLOCK_TRADE_SHARE * venue_volume_usd

    return Hedge(
        coverage=coverage,
        price=price,
        contracts=contracts,
        premium_usd=premium,
        fee_usd=fee,
        cost_usd=cost_usd,
        cost_gbp=cost_gbp,
        payout_gbp=payout_gbp,
        result_no_event_gbp=-cost_gbp,
        result_event_gbp=-loss_gbp + payout_gbp - cost_gbp,
        unhedged_event_gbp=-loss_gbp,
        cost_pct_of_loss=cost_gbp / loss_gbp if loss_gbp else 0.0,
        breakeven_prob=breakeven,
        expected_net_gbp=expected,
        needs_block_trade=block,
    )


def ladder(loss_gbp, fx, prices, coverages, fee_multiplier=1.0, view_prob=None):
    """Every price x coverage combination, for the options table."""
    return [size_hedge(loss_gbp, fx, p, c, fee_multiplier, view_prob)
            for p in prices for c in coverages]


def implied_from_fractional(num: float, den: float) -> float:
    """Bookmaker fractional odds (e.g. 14/1) to implied probability, margin included."""
    return den / (num + den)


def _m(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}£{abs(x) / 1e6:,.2f}m"


def report(s: dict) -> str:
    loss, fx, price = s["loss_gbp"], s["fx_usd_per_gbp"], s["price"]
    view = s.get("view_prob")
    out = [f"Event: {s['event']}",
           f"Loss if it happens: {_m(loss)}   FX: {fx} USD per GBP",
           f"Screen price: {price * 100:.1f}c  (implied {price:.1%})"]
    for name, (n, d) in s.get("bookmaker_odds", {}).items():
        out.append(f"Bookmaker {name} {n:g}/{d:g}: implied {implied_from_fractional(n, d):.1%}")
    if view is not None:
        out.append(f"Model view: {view:.1%}  ({s.get('view_source', 'own view')})")

    main = size_hedge(loss, fx, price, s.get("coverage", 1.0),
                      s.get("fee_multiplier", 1.0), view, s.get("venue_volume_usd"))
    out += ["", f"Hedge at {main.coverage:.0%} coverage",
            f"  Contracts:            {main.contracts:,}",
            f"  Premium + fee:        ${main.premium_usd:,.0f} + ${main.fee_usd:,.0f}"
            f" = {_m(main.cost_gbp)}  ({main.cost_pct_of_loss:.1%} of the loss)",
            f"  If it does not happen: {_m(main.result_no_event_gbp)}",
            f"  If it happens:         {_m(main.result_event_gbp)}"
            f"  (unhedged {_m(main.unhedged_event_gbp)})",
            f"  Break-even probability: {main.breakeven_prob:.1%}"]
    if main.expected_net_gbp is not None:
        out.append(f"  Expected value at model view: {_m(main.expected_net_gbp)}")
    if main.needs_block_trade is not None:
        vol = s["venue_volume_usd"]
        verdict = "block trade needed" if main.needs_block_trade else "screen can absorb it"
        out.append(f"  Premium vs venue volume: ${main.premium_usd:,.0f} vs ${vol:,.0f}: {verdict}")

    prices = s.get("ladder_prices", [price])
    covs = s.get("ladder_coverages", [0.5, 1.0])
    out += ["", "Options (cost / result if it happens / break-even)"]
    head = "  price  " + "".join(f"{c:>34.0%}" for c in covs)
    out.append(head)
    for p in prices:
        cells = []
        for c in covs:
            h = size_hedge(loss, fx, p, c, s.get("fee_multiplier", 1.0))
            cells.append(f"{_m(h.cost_gbp):>10} / {_m(h.result_event_gbp):>9} / {h.breakeven_prob:5.1%}")
        out.append(f"  {p * 100:4.1f}c  " + "".join(f"{x:>34}" for x in cells))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("scenario", help="scenario JSON file")
    ap.add_argument("--json", action="store_true", help="print the main hedge as JSON")
    args = ap.parse_args(argv)
    with open(args.scenario, encoding="utf-8") as f:
        s = json.load(f)
    if args.json:
        h = size_hedge(s["loss_gbp"], s["fx_usd_per_gbp"], s["price"], s.get("coverage", 1.0),
                       s.get("fee_multiplier", 1.0), s.get("view_prob"), s.get("venue_volume_usd"))
        print(json.dumps(asdict(h), indent=2))
    else:
        print(report(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
