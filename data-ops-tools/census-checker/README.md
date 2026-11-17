# Census Checker

Gets an employee benefits census ready for carrier quoting, and keeps personal data out of every output.

A bad census (a ZIP code that lost its leading zero, a Family tier with no spouse listed, a duplicate employee) is one of the most common reasons a benefits quote stalls. This tool catches those problems in one pass and writes a client-ready list of what to fix.

## What it does

1. **Strips identifiers first.** SSNs, emails, phone numbers and street addresses are dropped, and any SSN or email typed into a notes field is masked. Date of birth becomes age.
2. **Checks every row** against quoting rules: required fields, valid dates and ages, 5-digit ZIPs, real state codes, valid coverage tiers, tiers that match the listed dependents, children 26 or older, future hire dates, part-time employees enrolled, and duplicates.
3. **Writes three files:**
   - `census_clean.csv`: quote-ready, with no identifiers
   - `issues.md`: what to fix, grouped by priority, ready to paste into Slack
   - `summary.json`: counts for a dashboard or an automation step
4. **Optional:** `--draft-message` writes a prompt an LLM can turn into a friendly client follow-up. The prompt holds only the redacted issue list.

## Run it

```
python make_test_census.py          # synthetic census with planted problems
python census_checker.py census.csv --dependents dependents.csv --as-of 2026-11-16 --out out --draft-message
pytest -q
```

## Results on the synthetic test set

The test census has 153 employees and 116 dependents, with 33 problems planted across 11 types (all data is fake).

- All 30 row-level problems flagged, with no false alarms on clean rows.
- All 3 SSNs typed into notes masked.
- No SSNs, emails, phone numbers or street addresses in any output file, checked by the test suite.

## Where it fits in an automation

In n8n, Zapier or Make: a census arrives in Slack or Drive, this script runs as a code step, `issues.md` is posted back to the client's channel, and a specialist approves the message before it's sent. Personal data never reaches a language model.
