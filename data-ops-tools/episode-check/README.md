# episode-check

QA for handheld demonstration data (glove or handheld gripper episodes), run before the data goes to annotation or training.

For each episode it reads the wrist pose and the hand opening and gives a verdict: accept, trim or reject, with the reason. Then it builds two reports from the reasons:

- a collector scorecard, to see who needs coaching
- a task report, to see which task instructions need rewriting

I added the task report because of a pattern I kept running into with annotation teams. If one person gets a task wrong, you coach that person. If most people get it wrong in the same way, the instructions are the problem, and coaching people one at a time doesn't fix it.

## Results

### Real recordings

I ran it on two motion capture sequences from the TUM RGB-D benchmark. In both, a person carries a sensor by hand.

| Sequence | Length | Missing | Longest gap | Other problems | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| freiburg1_xyz | 30.1 s | 0.11 s | 0.11 s | none | accept |
| fr2_desk | 99.4 s | 28.0 s in 135 gaps | 11.99 s | 1 duplicate timestamp, 4 position jumps (peak 9.7 m/s), a rotation jump (peak 55 rad/s) | reject |

fr2_desk is ground truth that other systems get scored against, and 28% of its time is missing.

### 160 test episodes with planted problems

I cut 160 episodes from the clean parts of the same real motion (6 to 12 s each, resampled to 50 Hz). The hand opening, collector IDs and the problems are simulated.

| Problem | Planted | Caught | False flags on clean episodes |
| --- | ---: | ---: | ---: |
| tracking_gap | 11 | 11 | 0 |
| frozen_pose | 3 | 3 | 0 |
| position_jump | 3 | 3 | 0 |
| rotation_jump | 3 | 3 | 0 |
| aperture_stuck | 3 | 3 | 0 |
| aperture_out_of_range | 3 | 3 | 0 |
| no_grasp | 16 | 16 | 0 |
| too_short_path | 3 | 3 | 0 |
| idle_head | 3 | 3 | 0 |
| idle_tail | 11 | 11 | 2 |

Every planted problem was caught on this seed and on seeds 1 to 5. The false flags are idle trims (0 to 2 per run). I checked them: each comes from a real pause of more than 2 s in the original recording, so the hand really was still. The 3 frozen pose episodes also get a position jump flag, because when a frozen tracker recovers, the hand jumps to where it actually is.

I planted three patterns for the reports to find:

| Planted | What the report said |
| --- | --- |
| C4 often forgets to stop recording | Scorecard: C4, 11 trims for idle_tail, "Stop recording as soon as the task ends" |
| C6 has a badly fitted glove | Scorecard: C6, 11 rejects for tracking_gap, a note about glove fit and re-pairing |
| The open drawer instructions let people push the drawer instead of gripping the handle | Task report: open_drawer, no_grasp on 33% of episodes from 7 of 8 collectors, spec problem |

## Checks

| Check | Flags | Action |
| --- | --- | --- |
| duplicate_timestamps | repeated or backward timestamps | reject |
| tracking_gap | a step longer than 3x the median, with one gap of 0.25 s or more | reject |
| frozen_pose | pose unchanged for 0.25 s or more while time keeps running | reject |
| position_jump | a step faster than 3 m/s | reject |
| rotation_jump | the wrist turning faster than 20 rad/s | reject |
| aperture_out_of_range | hand opening outside -2 mm to 10 cm | reject |
| aperture_stuck | hand opening changes by less than 2 mm over the whole episode | reject |
| no_grasp | the task needs a grasp but the hand never closes below 3 cm | reject |
| too_short_path | the hand moves less than the task minimum (0.2 m) | reject |
| idle_head / idle_tail | more than 2 s still at the start or end | trim, with cut points |

For the idle check I measure net movement over half a second. Adding up small steps doesn't work, because sensor jitter makes a still hand look like it's moving. Quaternions with flipped signs are treated as the same rotation, so they don't show up as rotation jumps.

## Usage

```
python make_test_data.py
python evaluate.py --out out
python episode_check.py data/manifest.csv --tasks data/tasks.json --out out
python -m pytest -q
```

`make_test_data.py` builds the 160 test episodes. `evaluate.py` checks them, scores the results against the planted problems and audits the two raw sequences. Use `episode_check.py` directly on your own data. Needs Python 3.8+ and numpy (pytest for the tests).

Input is one CSV per episode with columns `t, x, y, z, qx, qy, qz, qw` and optionally `aperture` in metres. There's also a `manifest.csv` (`episode_id, collector_id, task, file`) and a `tasks.json` that sets `requires_grasp`, `min_path_m`, `max_idle_head_s` and `max_idle_tail_s` for each task.

Output goes to `out/`:

- `verdicts.csv`: every episode with its verdict, reasons and details
- `collector_scorecard.md`: accept, trim and reject counts per collector, with a coaching note when someone stands out
- `task_report.md`: each problem by task, marked as a spec problem or a collector problem
- `summary.json`: totals and the share of usable episodes
- `evaluation.md`: planted problem scores and the audit of the raw sequences

## Limitations

- The hand opening, collectors, tasks and planted problems are simulated, and I wrote the planted problems alongside the checks. So the test results show the logic works. They don't say how often these problems happen in real collection.
- It only looks at the signals, not video. Someone who does the wrong task smoothly, with a normal grasp, will pass.
- All the thresholds are first guesses and should be tuned on a week of real episodes: gap length, 3 m/s, 20 rad/s, 3 cm, 2 s idle, and the 20% and 60% cut-offs for calling something a spec problem.
- The 160 episodes overlap, since they all come from about 130 s of motion, so they aren't independent samples.

## Data

`data/real/` has two ground truth trajectories from the [TUM RGB-D benchmark](https://cvg.cit.tum.de/data/datasets/rgbd-dataset) (Sturm et al., IROS 2012, CC BY 4.0), taken from the test data in the [evo](https://github.com/MichaelGrupp/evo) toolkit.
