# Seeded-defect results

Synthetic data: 12 two-hand sessions x 300 frames at 30 fps per experiment, clean noise 2 mm. Bold = defect caught (past 1.5x the clean value, or any flags where clean data has none). Metrics need ground truth; checks do not.

| Planted defect | MPJPE mean (mm) | PA-MPJPE mean (mm) | Fingertip p95 (mm) | Hand size variation (%) | Speed spike frames | L/R swap flags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Clean (no defect) | 4.3 | 3.0 | 7.9 | 1.3 | 0 | 0 |
| Whole hand rotated 15 degrees | **28.9** | 3.0 | **49.8** | 1.3 | 0 | 0 |
| Hand 15% too large | **17.4** | 3.0 | **30.8** | 1.3 | 0 | 0 |
| Hand size drifts 0.90 to 1.15 | **8.9** | 3.0 | **22.8** | **7.1** | 0 | 0 |
| Fingertip noise, 20 mm | **10.9** | **11.3** | **56.6** | **4.0** | **112** | 0 |
| Keypoints jump 15 cm on 3% of frames | 4.6 | 3.4 | 7.9 | **5.1** | **156** | 0 |
| Left and right labels swapped, 30 frames | **8.9** | **5.2** | **63.4** | **2.1** | **72** | **72** |

## Confidence interval on clean MPJPE

- Treating every joint-frame as independent: 4.31 mm, 95% CI 4.30 to 4.33 (width 0.030 mm)
- Resampling whole sessions (12 clusters): 4.31 mm, 95% CI 4.27 to 4.35 (width 0.083 mm)
- The naive interval is 3x too narrow, because frames within a session share the same offset.
