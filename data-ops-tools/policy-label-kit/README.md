# policy-label-kit

A kit for labeling AI conversations against a written safety policy, and for
measuring the quality of the labels, not just the count.

> \*\*Content warning:\*\* the conversations come from a public red-teaming
> dataset. They include slurs, violent requests and self-harm content.

## Results at a glance

A reference labeling of all 120 conversations under the first policy put
**35 of 100 in Borderline**: the wording didn't settle them. Writing the
decisions behind those cases into `policy/POLICY\_v2.md` and relabelling
brought Borderline down to **2 of 100**.

||Policy v1|Policy v2|
|-|-:|-:|
|Breaks|24|50|
|Borderline|35|2|
|Doesn't break|41|48|
|Severity 3 (serious harm) among flagged|14|14|
|Harmlessness score check (AUROC)|0.83|0.80|

!\[The labeling app](docs/app.png)

## What's inside

```
policy-label-kit/
├── policy/       the safety policy, v1 and v2
├── app/          the labeling app
├── data/         the 120 conversations and the scoring signals
├── scripts/      scoring, comparison and rebuild scripts
├── reference/    a full reference labeling, its decision rules and reports
├── examples/     random demo labels: the report format and a chance-level floor
├── tests/        unit tests
├── docs/         screenshot for this README
├── README.md
├── LICENSE
└── .gitignore
```

### `policy/`: what counts as a violation

|File|What it is|
|-|-|
|`POLICY.md`|Version 1: six plain-language rules (P1 violence and weapons, P2 crime and fraud, P3 hate and harassment, P4 sexual content, P5 privacy, P6 self-harm and drugs). Borderline needs a note naming the words that didn't settle the case.|
|`POLICY\_v2.md`|Version 2, written from the cases v1 couldn't settle: three general rules (offering is helping, accuracy doesn't matter, judge with context), a new P7 for other serious harm, a protected-groups list and a 1 to 3 severity scale. The app uses this version.|

### `app/`: where labeling happens

|File|What it is|
|-|-|
|`label.html`|The labeling app. Open it in any browser; no install or internet needed. Shows one conversation at a time, takes verdict, rule, severity, confidence and a note by keyboard, times each conversation, saves progress in the browser and exports `labels.csv`.|
|`label\_template.html`|The app's source without the conversations. `scripts/build\_app.py` fills it in to produce `label.html`.|

### `data/`: the conversations and the scoring signals

|File|What it is|
|-|-|
|`items.json`|The 120 conversations to label, as ID and transcript only: 100 drawn from the public red-team data (20 at each attacker success rating, 0 to 4) plus 20 hidden repeats of earlier items, which measure consistency.|
|`answer\_key.json`|For each ID: the attacker's own 0 to 4 rating, the dataset's harmlessness score, topic tags, and which earlier item a repeat copies. Used for scoring. Don't open it before labeling.|

### `scripts/`: scoring and rebuilding

|File|What it does|
|-|-|
|`analyze.py`|Scores a labels CSV and writes a report: consistency on the hidden repeats, agreement with the attackers, the harmlessness score check (AUROC), speed, severity counts and every Borderline note. `--gold` adds agreement with a reference labeling, with kappa and every disagreement listed.|
|`compare.py`|Compares two label files on the same conversations: verdict counts, a before/after grid and each changed verdict with its note. For policy versions, or one labeler before and after calibration.|
|`make\_sample.py`|Rebuilds `data/items.json` and `data/answer\_key.json` from the public source data, with a fixed seed so the sample comes out identical.|
|`build\_app.py`|Rebuilds `app/label.html` from the template and `data/items.json`.|

### `reference/`: a complete labeling to learn from and score against

Made with model assistance as a second-rater baseline, not ground truth.

|File|What it is|
|-|-|
|`README.md`|What the reference labels are, the v1 vs v2 headline and how to score against them.|
|`reference\_labels\_v2.csv`|All 120 conversations under policy v2: verdict, rule, severity, confidence and a note for each. Score against this one, since the app uses v2.|
|`reference\_labels.csv`|The same 120 under policy v1.|
|`PRECEDENTS.md`|The 15 decision rules used for cases v1 left open, each with example conversations. These became the general rules in v2.|
|`ADJUDICATION.md`|The calls a review flagged as debatable, with the final decision and the reason for each.|
|`report\_v2.md`, `report.md`|`scripts/analyze.py` output for each version.|
|`v1\_vs\_v2.md`|`scripts/compare.py` output: the 33 conversations whose verdict changed between policy versions, and why.|

### `examples/`: what a report looks like

|File|What it is|
|-|-|
|`make\_demo\_labels.py`|Writes 120 random labels so the report can be seen before any real labeling.|
|`demo\_labels.csv`|Those random labels. Not real judgments.|
|`demo\_report.md`|The report for the random labels. It sets a floor: random verdicts score a kappa near 0 against the attackers and an AUROC near 0.5.|

### `tests/`, `docs/` and the root files

|File|What it is|
|-|-|
|`tests/test\_analyze.py`|10 unit tests: the kappa and AUROC maths, the full report, scoring against a reference, policy-version comparison, severity on every flagged label, and the app build.|
|`docs/app.png`|Screenshot of the labeling app used in this README.|
|`README.md`|This file.|
|`LICENSE`|MIT licence for the code.|
|`.gitignore`|Keeps Python caches and a local copy of the source data out of git.|

## How to use it

1. Read `policy/POLICY\_v2.md`.
2. Open `app/label.html` in a browser and label all 120 conversations:

|Key|Action|
|-|-|
|`Y` / `N` / `B`|Breaks / Doesn't / Borderline|
|`1` to `7`|Rule|
|`A` / `S` / `D`|Severity 1 / 2 / 3 (Breaks and Borderline)|
|`Q` / `W` / `E`|Confidence low / medium / high|
|`Enter` / `←`|Save and next / back|

3. Click **Export CSV** to download `labels.csv`.
4. Score it, against the reference labels as a second rater:

```
python scripts/analyze.py labels.csv --gold reference/reference\_labels\_v2.csv --out report.md
```

Python 3.8+ with the standard library only. Every script runs from any
directory.

## What the report measures

* **Consistency:** same verdict on the 20 hidden repeats, with Cohen's kappa.
Aim for 0.8 or more.
* **Agreement with a reference (`--gold`):** verdict agreement with kappa,
rule agreement, and every disagreement with the reference note beside it.
* **Agreement with the attackers:** each attacker rated their own attack
from 0 to 4; 3 or 4 counts as "worked". Expect a low kappa: attackers rate
perceived success, not policy breaches.
* **Harmlessness score check (AUROC):** whether the dataset's
preference-model harmlessness score separates the "breaks" verdicts.
0.5 is chance, 1.0 is perfect.
* **Speed:** median seconds per conversation and conversations per hour.
* **Severity** of Breaks and Borderline verdicts, and every **Borderline
note**: the material for the next policy revision.

None of the reference signals is ground truth. The disagreements are where
the policy needs work.

## Demo and baseline

`examples/demo\_report.md` is the report for 120 randomly generated labels
(`python examples/make\_demo\_labels.py`). Random verdicts score a kappa near
0 against the attackers and an AUROC near 0.5. Real labels should clear
both by a wide margin.

## Rebuilding from source

```
git clone --depth 1 https://github.com/anthropics/hh-rlhf.git
python scripts/make\_sample.py hh-rlhf/red-team-attempts/red\_team\_attempts.jsonl.gz
python scripts/build\_app.py
```

## Tests

```
python -m unittest discover tests
```

## Data and licence

Conversations are from the red-team release of
[hh-rlhf](https://github.com/anthropics/hh-rlhf) (MIT licence, copyright
Anthropic). The code in this repo is MIT licensed; see `LICENSE`.

