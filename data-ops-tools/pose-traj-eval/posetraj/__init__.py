"""posetraj: pose and trajectory quality checks for egocentric data.

Metrics: MPJPE, PA-MPJPE, per-joint error (pose); ATE, RPE (trajectory).
Checks: bone-length drift, speed spikes, left/right swaps, tracking gaps.
Stats: session-clustered bootstrap confidence intervals.
"""
from .pose import mpjpe, pa_mpjpe, joint_errors, pa_joint_errors, summarize, per_joint_mean
from .trajectory import read_tum, associate, ate, rpe, tracking_gaps
from .checks import bone_length_drift, speed_spikes, left_right_swaps
from .stats import cluster_bootstrap_ci

__version__ = "0.1.0"
