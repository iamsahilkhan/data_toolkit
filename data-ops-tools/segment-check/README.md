# segment-check

QA for time-stamped subtask labels on manipulation episodes (reach, grasp, transport, place, release). Left and right hands are labeled as separate tracks, so both hands acting at once isn't treated as an overlap.

It does three things:

- Flags rule breaks: labels not in the ontology, overlaps within a track, segments out of bounds or under 0.15s, label orders the ontology doesn't allow (e.g. reach -> transport with no grasp), and a missing hand.
- Compares each annotator to gold episodes: average boundary offset (late/early) and which labels they confuse. Timing is corrected before checking labels, otherwise a late annotator also looks like they confuse short segments.
- Ranks boundary types by how much annotators disagree on them after removing each person's offset. If everyone is inconsistent on the same boundary, the guideline probably needs work.

Episodes where unflagged annotators still disagree go to `adjudicate`; episodes with fewer than two unflagged annotators go to `relabel`.

## Usage

```
python make_test_data.py
python segment_check.py --out out
pytest -q
```

Inputs:
- `episodes.csv`: episode_id, duration, hands
- `annotations.csv`: episode_id, annotator_id, hand, start, end, label
- `gold.csv`: episode_id, hand, start, end, label, object
- `ontology.json`: labels with start/end rules, allowed transitions, min duration

If there's no `hand` column, everything is read as one track.

Outputs in `out/`: `issues.csv`, `annotator_report.md`, `guideline_gaps.md`, `adjudication.csv`, `summary.json`.

## Test data

`make_test_data.py` generates 160 two-hand episodes (40 with gold), each labeled by 3 of 8 simulated annotators. That's 480 annotation sets and 10,694 segments. Planted problems:

- A3 marks boundaries 0.35s late
- A5 labels place as release 40% of the time
- A7 merges grasp into reach 60% of the time
- the transport -> place boundary for wine glasses is loose for everyone
- 18 rule breaks (3 of each type) on the clean annotators

Current results (default seed):

- all 18 rule breaks caught, nothing flagged on clean annotators' other work
- 4,102 cases of both hands active at once, none flagged as overlap
- A3: 0.35s late (timing only). A5: place -> release 35%. A7: grasp -> reach 70%
- no notes for A1, A2, A4, A6, A8
- wine glass transport -> place ranked as the top guideline gap

7 tests, passing on seeds 1 to 8 and the default.

## Limitations

- Test data is synthetic and the planted problems were written alongside the checks, so this shows the logic works, not how it does on real data.
- It only looks at labels, not video. If every annotator agrees on a wrong label, it won't catch it.
- Thresholds (0.2s offset, 20% confusion, 0.85 agreement) are guesses and should be tuned on real gold data.
- The same checks would work for pass/fail or quality labels with a different ontology.
