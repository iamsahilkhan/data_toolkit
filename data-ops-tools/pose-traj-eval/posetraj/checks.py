"""Physical plausibility checks that need no ground truth.

They run on every frame of every session, so a delivery can be screened
before any human looks at it. Each returns the frames it flags.
"""
import numpy as np

# 21-joint hand: wrist 0, then 4 joints per finger (thumb, index,
# middle, ring, pinky), each finger running base to tip.
HAND_BONES = [(0, 1), (1, 2), (2, 3), (3, 4),
              (0, 5), (5, 6), (6, 7), (7, 8),
              (0, 9), (9, 10), (10, 11), (11, 12),
              (0, 13), (13, 14), (14, 15), (15, 16),
              (0, 17), (17, 18), (18, 19), (19, 20)]
FINGERTIPS = [4, 8, 12, 16, 20]
HAND_JOINT_NAMES = (["wrist"]
                    + [f"{f}_{p}" for f in ("thumb", "index", "middle", "ring", "pinky")
                       for p in ("1", "2", "3", "tip")])


def bone_lengths(seq, bones=HAND_BONES):
    """Bone lengths per frame: shape (frames, bones), in metres."""
    seq = np.asarray(seq, float)
    a = np.array([b[0] for b in bones])
    b = np.array([b[1] for b in bones])
    return np.linalg.norm(seq[:, a] - seq[:, b], axis=2)


def bone_length_drift(seq, bones=HAND_BONES, max_cv=0.05):
    """A real hand does not change size within a session.

    Returns (coefficient of variation per bone, list of bone indices whose
    variation exceeds max_cv). Catches scale drift in tracking and
    keypoints that wander between joints.
    """
    lengths = bone_lengths(seq, bones)
    cv = lengths.std(axis=0) / np.maximum(lengths.mean(axis=0), 1e-9)
    return cv, [i for i, c in enumerate(cv) if c > max_cv]


def hand_size_drift(seq, bones=HAND_BONES):
    """Variation of total skeleton size within a session, in percent.

    Summing all bone lengths per frame averages out per-joint noise, so
    this catches slow scale drift that per-bone variation misses.
    Returns (coefficient of variation in %, size per frame in metres).
    """
    size = bone_lengths(seq, bones).sum(axis=1)
    return float(size.std() / size.mean() * 100.0), size


def speed_spikes(seq, fps, max_speed=3.0):
    """Frames where any joint moves faster than max_speed (m/s).

    A keypoint that teleports between frames is almost always a tracking
    or labeling error. Returns sorted frame indices (the later frame of
    each bad step).
    """
    seq = np.asarray(seq, float)
    step = np.linalg.norm(np.diff(seq, axis=0), axis=2) * fps
    frames = np.nonzero((step > max_speed).any(axis=1))[0] + 1
    return frames.tolist()


def left_right_swaps(left, right):
    """Frames where the left and right hand labels look swapped.

    For each frame, compare how far each hand moved if labels are kept
    against how far they moved if labels are exchanged. If exchanging is
    much shorter, the labels most likely flipped at that frame.
    """
    left = np.asarray(left, float)
    right = np.asarray(right, float)
    lw = left[:, 0]
    rw = right[:, 0]
    keep = np.linalg.norm(lw[1:] - lw[:-1], axis=1) + np.linalg.norm(rw[1:] - rw[:-1], axis=1)
    swap = np.linalg.norm(lw[1:] - rw[:-1], axis=1) + np.linalg.norm(rw[1:] - lw[:-1], axis=1)
    return (np.nonzero(swap < 0.5 * keep)[0] + 1).tolist()
