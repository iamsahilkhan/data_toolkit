# payment-timing-check

When a lender's ACH debit bounces for insufficient funds, a lot of the time
the borrower isn't out of money. The paycheck just hadn't landed yet. I wanted
to see how much of that you can find from a lender's own debit history,
without any bank data.

You give it a CSV of debit attempts and it tells you:

- return rates vs Nacha's limits (15% overall, 3% admin, 0.5% unauthorized), for the whole period and the worst 60-day window
- how many R01/R09 failures cleared on a retry within 10 days (the "timing-fixable" ones)
- how many payments had two returns in a row (relevant under the CFPB payment rule for covered loans)
- first-try success rate by weekday and by part of the month
- a rough value: fees borrowers didn't need to pay, cash collected late, and the return rate if those had cleared first time

## Trying it

I don't have real lender data, so `simulate.py` makes a fake lender: 2,000
borrowers on weekly, biweekly or 1st/15th pay, a monthly due date, retries 3
business days apart, and about 12% of borrowers hitting hardship partway
through.

```
pip install pandas pytest
python simulate.py --out attempts.csv
python payment_timing.py attempts.csv --out report.md
python validate.py
pytest -q
```

On that fake lender:

| | |
| --- | ---: |
| Debit attempts | 14,767 |
| Overall return rate (whole period / worst 60 days) | 22.71% / 28.34% |
| Returns that were insufficient funds | 98% |
| First tries that failed for insufficient funds | 1,846 |
| Timing-fixable (cleared within 10 days) | 1,315 ($241,272) |
| Borrower fees avoided at $16.82 each | $22,118 |
| Return rate if those cleared first time | 12.62% |

## Does the estimate hold up?

Since the simulator knows every balance, I could check which failures really
would have cleared on the borrower's next payday. Every payment the report
called timing-fixable really was (precision 100%), and it found 1,315 of the
1,628 that truly were (recall 81%).

So the number is a minimum. The ones it misses are payments that failed and
were never retried in time, so the history can't show when the money came in.
You'd need balance data to see those.

## Caveats

- The demo numbers are from fake data, not a real portfolio.
- $16.82 is Bankrate's 2025 average NSF fee. A lot of big banks don't charge one anymore, so real savings depend on where borrowers bank.
- The two-in-a-row count shows exposure to the CFPB rule, not a violation. Whether the rule applies depends on the loan type.

## Next

- break results out by pay cycle once I can infer it from settled dates
- suggest a better due date per borrower segment
- per-lender cost of a return as an input instead of a flag

## References

- [Nacha return rate levels](https://www.nacha.org/system/files/2025-07/Unauth-Return-Rate-Infographics-2025.pdf)
- [CFPB payment rule, effective March 30, 2025](https://www.consumerfinance.gov/about-us/blog/new-protections-for-payday-and-installment-loans-take-effect-march-30)
- [Bankrate on NSF fees](https://www.bankrate.com/banking/how-bank-fees-are-squeezing-your-budget/)
