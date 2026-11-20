# Payment timing report

14,767 debit attempts on 12,000 payments over 184 days.

## 1. Return rates against Nacha levels

| Return type | Count | Rate, whole period | Worst 60-day window | Nacha level |
| --- | ---: | ---: | ---: | ---: |
| Overall (all codes) | 3,354 | 22.71% | 28.34% | 15.00% |
| Administrative (R02, R03, R04) | 52 | 0.35% | 0.59% | 3.00% |
| Unauthorized (R05, R07, R10, R11, R29, R51) | 4 | 0.03% | 0.09% | 0.50% |
| Insufficient funds (R01, R09) | 3,298 | 22.33% | 27.86% | not separately monitored |

Insufficient funds caused 98% of all returns.

## 2. Timing-fixable failures

- First attempts returned for insufficient funds: **1,846**
- Of those, settled on a later attempt within 10 days: **1,315** ($241,272), a median of 5.0 days after the first try
- Never collected in this data: **531**

For these, the money came in a few days later. The first debit just went out too early. Note: this is a minimum. Payments that failed and were never retried can't show when the money came in.

## 3. Two-strike exposure

**921** payments had two consecutive returned attempts. Under the CFPB payment rule (in effect since March 30, 2025), a covered lender needs new borrower authorization before a third try.

## 4. When first attempts clear

| Weekday | Success rate | Attempts |
| --- | ---: | ---: |
| Monday | 89.6% | 4,990 |
| Tuesday | 85.1% | 1,356 |
| Wednesday | 75.8% | 2,005 |
| Thursday | 63.3% | 1,652 |
| Friday | 95.6% | 1,997 |

| Day of month | Success rate | Attempts |
| --- | ---: | ---: |
| 1 to 5 | 79.4% | 3,485 |
| 6 to 10 | 86.7% | 1,715 |
| 11 to 15 | 84.3% | 2,088 |
| 16 to 20 | 90.9% | 2,363 |
| 21 to 25 | 79.1% | 1,677 |
| 26 to 31 | 90.3% | 672 |

## 5. What fixing the timing is worth

- Borrower fees avoided: 1,315 failed debits x $16.82 average NSF fee = **$22,118** (using Bankrate's 2025 average NSF fee, actual fees vary by bank)
- Cash collected on the first try instead of 5.0 days later: **$241,272**
- Lender cost per return not given; pass --lender-cost-per-return to include it
- Overall return rate if those debits had cleared first time: **12.62%** (from 22.71%), with 1,705 returned attempts never sent
