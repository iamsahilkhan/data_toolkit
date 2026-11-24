# Reference labels

|File|What it is|
|-|-|
|`reference\_labels.csv`|Labels under `policy/POLICY.md` (v1), with a severity grade (1 to 3) on every Breaks and Borderline verdict|
|`reference\_labels\_v2.csv`|The same conversations labelled under `policy/POLICY\_v2.md`|
|`PRECEDENTS.md`|The 15 decision rules used for cases v1 leaves open|
|`ADJUDICATION.md`|The debatable calls and the final decision on each|
|`report.md`, `report\_v2.md`|`scripts/analyze.py` output for each version|
|`v1\_vs\_v2.md`|`scripts/compare.py` output: what changed between policy versions|

## Headline

||v1 policy|v2 policy|
|-|-:|-:|
|Breaks|24|50|
|Borderline|35|2|
|Doesn't break|41|48|
|Agreement with attackers (kappa)|0.15|0.20|
|Harmlessness score check (AUROC)|0.83|0.80|

Under v1, a third of the conversations land in Borderline because the
wording doesn't settle them. v2 writes the precedents into the policy and
Borderline falls to 2 of 100. The two that remain (c080, c100) are the next
cases for the policy to settle. Agreement with the attackers rises a little;
the harmlessness check dips slightly because v2 also catches milder cases,
such as offers to help with petty theft.

The 20 of 20 on the hidden repeats is not a consistency score: the repeats
were recognized during the pass. Severity uses the scale in `policy/POLICY\_v2.md`.

## Score your own labels against it

The app uses policy v2, so score against the v2 labels:

```
python scripts/analyze.py labels.csv --gold reference/reference\_labels\_v2.csv --out report.md
```

