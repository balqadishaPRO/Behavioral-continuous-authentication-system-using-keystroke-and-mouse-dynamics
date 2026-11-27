"""Turn raw 10 s windows of timing events into feature vectors, one per modality.

A window is {"keys": [[down_ms, up_ms], ...], "moves": [[t_ms, x, y], ...],
"clicks": [[down_ms, up_ms], ...], "scrolls": n}. Key identities are never collected.

Design choices (checked on real owner-vs-impostor data, see README):
- Typing and mouse are scored by separate models, so a typing-only window is never
  compared against mouse habits.
- Robust statistics (medians, quartiles) instead of mean/std: one long Shift hold
  must not reshape the whole profile.
- Each score pools the last POOL windows of that modality (~20 s of behaviour):
  one 10 s window has too few keystrokes for stable estimates.
- Intervals are computed inside each window, never across two windows, because
  timestamps restart on every page load.
"""
import math

import numpy as np

KEY_NAMES = ["dwell_p50", "flight_p50", "flight_p75", "flight_iqr", "pp_p50", "pp_p25", "overlap_rate"]
MOUSE_NAMES = ["speed_mean", "speed_std", "accel_mean", "straightness", "click_p50"]
MODALITIES = ("keys", "mouse")
WINDOW_S = 10        # must match setInterval in frontend/app.html
POOL = 2             # windows pooled per score
MIN_KEYS = 10        # fewer key presses in a window = not enough rhythm to judge
MIN_MOVES = 100      # mousemove fires ~60/s, so ~1.5 s of actual movement
STROKE_GAP_MS = 300  # mouse pause that ends one movement stroke


def _q(xs, p):
    return float(np.percentile(xs, p)) if xs else 0.0


def keyboard(windows):
    dwell, flight, press, overlap = [], [], [], []
    for w in windows:
        keys = sorted(w.get("keys", []))
        dwell += [u - d for d, u in keys if 0 < u - d < 500]  # longer = held modifier, not rhythm
        for (d1, u1), (d2, _) in zip(keys, keys[1:]):
            if -300 < d2 - u1 < 1000:        # longer gaps are pauses, not rhythm
                flight.append(d2 - u1)        # negative = next key pressed before release (rollover)
                overlap.append(d2 < u1)
            if 0 < d2 - d1 < 1000:
                press.append(d2 - d1)         # press-to-press interval
    if len(dwell) < MIN_KEYS:
        return None
    return [_q(dwell, 50), _q(flight, 50), _q(flight, 75), _q(flight, 75) - _q(flight, 25),
            _q(press, 50), _q(press, 25), float(np.mean(overlap)) if overlap else 0.0]


def mouse(windows):
    speeds, straightness, clicks, n_moves = [], [], [], 0
    for w in windows:
        moves = w.get("moves", [])
        n_moves += len(moves)
        prev = start = None
        path = 0.0
        for t, x, y in moves:
            if prev is None or t - prev[0] > STROKE_GAP_MS:
                if start is not None and path > 50:
                    straightness.append(math.dist(start[1:], prev[1:]) / path)
                start, path = (t, x, y), 0.0
            else:
                d = math.dist(prev[1:], (x, y))
                path += d
                if t > prev[0]:
                    speeds.append(d / (t - prev[0]))  # px per ms
            prev = (t, x, y)
        if start is not None and path > 50:
            straightness.append(math.dist(start[1:], prev[1:]) / path)
        clicks += [u - d for d, u in w.get("clicks", []) if 0 < u - d < 2000]
    if n_moves < MIN_MOVES:
        return None
    accel = float(np.mean(np.abs(np.diff(speeds)))) if len(speeds) > 1 else 0.0
    return [float(np.mean(speeds)) if speeds else 0.0, float(np.std(speeds)) if speeds else 0.0, accel,
            float(np.median(straightness)) if straightness else 1.0, _q(clicks, 50)]


EXTRACTORS = {"keys": keyboard, "mouse": mouse}


def extract(w):
    """Single window: {"keys": [...], "mouse": [...]} for modalities with enough activity; {} = idle."""
    out = {m: fn([w]) for m, fn in EXTRACTORS.items()}
    return {m: v for m, v in out.items() if v is not None}


def rolling(windows):
    """Pooled feature dict for each window in time order: each modality present in a window is
    computed over that window plus the previous POOL-1 windows that also had that modality."""
    hist = {m: [] for m in EXTRACTORS}
    out = []
    for w in windows:
        d = {}
        for m, fn in EXTRACTORS.items():
            if fn([w]) is not None:
                hist[m] = (hist[m] + [w])[-POOL:]
                d[m] = fn(hist[m])
        out.append(d)
    return out
