# ATE and RPE on two planted failures

Synthetic camera path, 60 s at 30 Hz. ATE after a rigid (SE3) alignment; RPE over one frame.

| Estimate | ATE RMSE (mm) | RPE RMSE (mm per frame) |
| --- | ---: | ---: |
| Slow drift, no jitter | 20.1 | 0.04 |
| Jitter, no drift | 4.0 | 5.66 |

Drift dominates ATE while barely moving RPE; jitter does the opposite. Either metric alone would pass one of these failures.

## Real data: TUM RGB-D benchmark

Real SLAM estimates against motion-capture ground truth, files from evo's test data. ATE after SE3 alignment, RPE over one frame. Gaps = estimate timestamps more than 50 ms apart (1.5 frames at 30 Hz).

| Sequence and estimate | Poses matched | ATE RMSE (mm) | RPE RMSE (mm per frame) | Gaps |
| --- | ---: | ---: | ---: | ---: |
| freiburg1_xyz-rgbdslam.txt | 785 | 13.5 | 5.76 | 9 |
| fr2_desk_ORB.txt | 2174 | 8.1 | 3.49 | 72 |
