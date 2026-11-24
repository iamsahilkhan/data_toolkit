# Hedge Sizer

I wrote this to size and price a hedge on a binary event contract (pays $1 if the event happens, $0 if not), for a business that loses money if the event happens.

You give it the loss, the exchange rate and the contract price. It gives back:

- how many contracts to buy and the all-in cost (premium plus fee)
- the result if the event happens and if it doesn't, next to the unhedged loss
- the break-even probability, and the expected value if you give it a model's probability
- whether the premium is small enough for the screen or needs a block trade
- a table of options across prices and coverage levels

## Running it

```
python hedge_sizer.py scenario.json
python hedge_sizer.py scenario.json --json
python -m pytest -q
```

The first prints a readable report, the second prints the main hedge as JSON, and the third runs the 15 tests. It only needs the standard library (plus pytest for the tests).

## Example

`scenario.json` prices a hedge against Manchester United being relegated in 2026-27, using prices from 18 November 2026. The £10m loss is for a made-up client and should be swapped for a real number.

| | |
|---|---|
| Screen price | 6.3c (implied 6.3%) |
| Contracts for full cover | 13,300,000 |
| All-in cost | £0.67m, 6.7% of the loss |
| Result either way, fully hedged | minus £0.67m (unhedged: minus £10m) |
| Venue volume vs premium | $28,829 vs $837,900, so it needs a block trade |

## How the numbers work

- Contracts = coverage x loss x FX, rounded up. At 100% coverage you end up in the same place whether or not the event happens: you lose the cost and nothing else.
- Fee is Kalshi's published taker formula, round_up(0.07 x C x P x (1 - P)) to the next cent. A negotiated block trade can have different terms, so `fee_multiplier` lets you change it (0 means no fee).
- Break-even probability is the all-in cost per contract. If you think the event is more likely than that, the hedge is cheap on your own numbers.
- The block trade flag goes off when the premium is more than 10% of what the venue has traded.

## Limitations

- The loss is one number. Real exposures are ranges, so run it at the low and high end.
- It ignores the cost of tying up cash in the position until settlement, and any interest the venue pays.
- The payout is in dollars and the loss is in pounds. It converts at a single rate; hedging the currency as well is a separate decision.
- It prices off the screen. A block quote from a market maker will usually be wider, which is why the options table covers several prices.
