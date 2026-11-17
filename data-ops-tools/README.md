# Data Ops Tools

![tests](https://github.com/YOUR-USERNAME/data-ops-tools/actions/workflows/tests.yml/badge.svg)

Tools I've built for data ops work: QA for human labels and checking data before it's used. Each folder has the code, a script that generates synthetic test data with planted problems, tests, and a README.

[Sahil Khan](https://linkedin.com/in/iamsahilkhan)

| Tool | What it does | Result on synthetic test data |
|---|---|---|
| [segment-check](segment-check/) | QA for time-stamped subtask labels on two-hand manipulation episodes: rule checks, per-annotator comparison to gold, inconsistent boundaries | 18/18 planted rule breaks and 3/3 problem annotators caught, 0 false flags |
| [census-checker](census-checker/) | Cleans an employee benefits census for quoting: removes PII, checks 11 rules, writes a fix list | 30/30 planted row problems flagged, 0 false alarms, no PII in outputs |

## Running

Standard library only, plus pytest.

```
pip install -r requirements.txt
cd segment-check
python make_test_data.py
python segment_check.py --out out
pytest -q
```

Tests run on every push via GitHub Actions.

All test data is synthetic. See each README for limitations.
