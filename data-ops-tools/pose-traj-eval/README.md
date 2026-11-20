# pose-traj-eval

Quality checks for 3D hand pose and camera trajectory data: the metrics
used to score it against ground truth (MPJPE, PA-MPJPE, ATE, RPE), the
checks that screen every frame without ground truth, and confidence
intervals that respect sessions.

The point of the project is that **every metric hides some kind of error**.
I planted seven known defects and measured which metric or check catches
each one.

## Findings

**1. PA-MPJPE missed 3 of the 6 planted pose defects.** Procrustes alignment
removes rotation, translation and scale before measuring, so a hand rotated
15 degrees, a hand 15% too large and a hand whose size drifts all score the
same as clean data (3.0 mm). Raw MPJPE catches all three.

**2. Mean MPJPE missed keypoints that jump 15 cm on 3% of frames.** The mean
moved from 4.3 to 4.6 mm. The speed check flagged 156 frames, without any
ground truth.

**3. ATE and RPE rank drift and jitter in opposite order.** A slowly drifting
estimate scored 20.1 mm ATE but 0.04 mm RPE. A jittery one scored 4.0 mm ATE
but 5.66 mm RPE. Report either alone and one failure passes.

**4. Treating frames as independent made the confidence interval 3x too
narrow.** Resampling whole sessions gives the honest interval.

### Pose: planted defects (synthetic data)

12 two-hand sessions x 300 frames at 30 fps per experiment, clean tracker
noise 2 mm. Bold = caught (past 1.5x the clean value, or any flags where
clean data has none). The first three columns need ground truth; the last
three do not.

| Planted defect | MPJPE mean (mm) | PA-MPJPE mean (mm) | Fingertip p95 (mm) | Hand size variation (%) | Speed spike frames | L/R swap flags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Clean (no defect) | 4.3 | 3.0 | 7.9 | 1.3 | 0 | 0 |
| Whole hand rotated 15 degrees | **28.9** | 3.0 | **49.8** | 1.3 | 0 | 0 |
| Hand 15% too large | **17.4** | 3.0 | **30.8** | 1.3 | 0 | 0 |
| Hand size drifts 0.90 to 1.15 | **8.9** | 3.0 | **22.8** | **7.1** | 0 | 0 |
| Fingertip noise, 20 mm | **10.9** | **11.3** | **56.6** | **4.0** | **112** | 0 |
| Keypoints jump 15 cm on 3% of frames | 4.6 | 3.4 | 7.9 | **5.1** | **156** | 0 |
| Left and right labels swapped, 30 frames | **8.9** | **5.2** | **63.4** | **2.1** | **72** | **72** |

Only the swap check names the cause of the last row; the other columns see
large errors but cannot say why.

### Trajectory: drift versus jitter (synthetic), and real TUM RGB-D data

| Estimate | ATE RMSE (mm) | RPE RMSE (mm per frame) |
| --- | ---: | ---: |
| Slow drift, no jitter | 20.1 | 0.04 |
| Jitter, no drift | 4.0 | 5.66 |

On real SLAM output from the TUM RGB-D benchmark:

| Sequence and estimate | Poses matched | ATE RMSE (mm) | RPE RMSE (mm per frame) | Gaps over 50 ms |
| --- | ---: | ---: | ---: | ---: |
| freiburg1_xyz, RGBD-SLAM | 785 | 13.5 | 5.76 | 9 |
| fr2_desk, ORB-SLAM | 2174 | 8.1 | 3.49 | 72 |

## Validated against evo

[evo](https://github.com/MichaelGrupp/evo) is the standard open-source
trajectory evaluation tool. On three real TUM RGB-D estimates (two RGB-D
with SE3 alignment, one monocular with Sim3), ATE and RPE match evo to within
3e-17 m, which is floating-point rounding.

```
estimate                   align  poses  ATE evo (m)  ATE ours  RPE evo (m)  RPE ours  max diff
freiburg1_xyz-rgbdslam     se3      785     0.013470  0.013470     0.005764  0.005764  2.78e-17
fr2_desk_ORB               se3     2174     0.008119  0.008119     0.003490  0.003490  1.08e-17
fr2_desk_ORB_kf_mono       sim3     118     0.007729  0.007729     0.007069  0.007069  2.08e-17
```

## What is in it

| File | Contents |
| --- | --- |
| `posetraj/align.py` | Umeyama least-squares alignment (rigid or with scale), reflection-safe |
| `posetraj/pose.py` | MPJPE (root-aligned), PA-MPJPE, per-joint error, mean / median / p95 / max |
| `posetraj/trajectory.py` | TUM reader, timestamp association, ATE (SE3, Sim3 or none), RPE, tracking gaps |
| `posetraj/checks.py` | No-ground-truth checks: hand size drift, per-bone variation, speed spikes, left/right swaps |
| `posetraj/stats.py` | Session-clustered bootstrap CI, and the naive CI it replaces |
| `demo/seeded_defects.py` | The planted-defect experiment above |
| `demo/drift_vs_jitter.py` | The ATE versus RPE experiment above |
| `validation/validate_against_evo.py` | The evo comparison |
| `tests/` | 13 tests: alignment, metric invariances, association, checks, CIs, evo match |

## Run it

```bash
pip install numpy scipy pytest          # add evo to run the validation
python demo/seeded_defects.py
python -m posetraj traj --gt gt.txt --est est.txt --align se3
python -m posetraj pose --gt gt.npy --pred pred.npy

# real-data validation (evo's repo ships the TUM test files)
git clone --depth 1 https://github.com/MichaelGrupp/evo.git
pip install evo
python validation/validate_against_evo.py evo/test/data
python demo/drift_vs_jitter.py evo/test/data
EVO_TEST_DATA=evo/test/data pytest -q tests
```

## Limits

- The pose results use synthetic hands, on purpose: only planted defects
  give a known answer to score each detector against. The numbers show how
  the metrics behave, not how any real tracker performs.
- The trajectory metrics are checked on real data, against evo.
- Check thresholds (3 m/s, 1.5 frame gaps, 1.5x clean level) are starting
  points; on real data they are calibrated on clean sessions first.
- The hand layout is the common 21-joint order (wrist, then four joints per
  finger). Other skeletons need their own bone list.

## References

- Sturm et al., [A Benchmark for the Evaluation of RGB-D SLAM Systems](https://cvai.cit.tum.de/_media/spezial/bib/sturm12iros.pdf), IROS 2012 (ATE and RPE)
- [Limitations of (Procrustes) Alignment in Assessing Multi-Person Human Pose and Shape Estimation](https://arxiv.org/abs/2409.16861), 2024
- Miller, [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640), 2024 (clustered errors)
- Umeyama, Least-squares estimation of transformation parameters between two point patterns, IEEE TPAMI, 1991
- Grupp, [evo](https://github.com/MichaelGrupp/evo)
