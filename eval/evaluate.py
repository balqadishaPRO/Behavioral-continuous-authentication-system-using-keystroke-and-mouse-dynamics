"""Offline evaluation on the windows collected by the app.

For every enrolled user: train on their enrollment windows only, then score
  genuine  = the user's own 'live' windows
  impostor = every other user's windows + windows labelled 'impostor' in this user's sessions.
Reports FAR / FRR at the app's threshold, EER, and detection delay of the 3-in-a-row lock rule,
for IsolationForest, One-Class SVM and LOF, using typing only, mouse only, and both combined.

Run from the repo root:  python -m eval.evaluate
"""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from backend import db, features, model
from backend.app import STREAK, THRESHOLD

OUT = Path(__file__).resolve().parent
GRID = np.linspace(0, 1, 201)
SETUPS = {"keys": ("keys",), "mouse": ("mouse",), "both": features.MODALITIES}


def load():
    data = defaultdict(lambda: defaultdict(list))  # user -> label -> [raw windows] in time order
    con = db.connect()
    for r in con.execute("SELECT u.username, s.label, s.raw FROM samples s JOIN users u ON u.id = s.user_id ORDER BY s.t"):
        w = json.loads(r["raw"])
        if features.extract(w):
            data[r["username"]][r["label"]].append(w)
    return data


def windows_to_lock(risks):
    """Index (1-based) of the window where the lock rule fires, or None."""
    streak = 0
    for i, r in enumerate(risks, 1):
        streak = streak + 1 if r > THRESHOLD else 0
        if streak >= STREAK:
            return i
    return None


def evaluate(data, algo, mods=features.MODALITIES):
    def score(models, windows):
        """Score a sequence of raw windows the way the app does (pooled per modality)."""
        risks = (model.window_risk(models, {m: d[m] for m in mods if m in d})[0] for d in features.rolling(windows))
        return [r for r in risks if r is not None]

    gen, imp, delays, missed, false_locks, n_users = [], [], [], 0, 0, 0
    for user, by_label in data.items():
        enroll = by_label["enroll"]
        if any(sum(m in features.extract(w) for w in enroll) < model.MIN_ENROLL[m] for m in mods):
            continue
        models = model.train_user(enroll, algo, mods)
        g = score(models, by_label["live"])
        if not g:
            continue
        n_users += 1
        gen += g
        false_locks += windows_to_lock(g) is not None
        attackers = [by_label["impostor"]] + [d["enroll"] + d["live"] for u, d in data.items() if u != user]
        for seq in attackers:
            r = score(models, seq)
            if not r:
                continue
            imp += r
            k = windows_to_lock(r)
            if k is None:
                missed += 1
            else:
                delays.append(k * features.WINDOW_S)
    if not n_users or not imp:
        return None
    gen, imp = np.array(gen), np.array(imp)
    frr = np.array([(gen > t).mean() for t in GRID])   # owner flagged
    far = np.array([(imp <= t).mean() for t in GRID])  # impostor accepted
    i = np.argmin(np.abs(far - frr))
    return {"users": n_users, "genuine_windows": len(gen), "impostor_windows": len(imp),
            "FAR@thr": float((imp <= THRESHOLD).mean()), "FRR@thr": float((gen > THRESHOLD).mean()),
            "EER": float((far[i] + frr[i]) / 2),
            "detect_rate": len(delays) / (len(delays) + missed),
            "mean_delay_s": float(np.mean(delays)) if delays else float("nan"),
            "owner_sessions_falsely_locked": false_locks,
            "_far": far, "_frr": frr}


def main():
    data = load()
    results = {(a, s): evaluate(data, a, mods) for s, mods in SETUPS.items() for a in model.ALGOS}
    if not any(results.values()):
        print("Not enough data: need >=2 users, each enrolled with some 'live' windows.")
        return
    cols = ["users", "genuine_windows", "impostor_windows", "FAR@thr", "FRR@thr", "EER",
            "detect_rate", "mean_delay_s", "owner_sessions_falsely_locked"]
    lines = ["| data | model | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 2)]
    for (a, s), r in results.items():
        if r:
            lines.append(f"| {s} | {a} | " + " | ".join(f"{r[c]:.3f}" if isinstance(r[c], float) else str(r[c]) for c in cols) + " |")
    table = "\n".join(lines)
    print(table)
    (OUT / "results.md").write_text(
        f"Threshold {THRESHOLD}, lock after {STREAK} suspicious windows of {features.WINDOW_S} s.\n\n{table}\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=True)
    for ax, s in zip(axes, SETUPS):
        for a in model.ALGOS:
            if r := results[(a, s)]:
                ax.plot(r["_far"], 1 - r["_frr"], label=f"{a} (EER {r['EER']:.2f})")
        ax.plot([0, 1], [0, 1], "k:", lw=1)
        ax.set(xlabel="False acceptance rate", title={"keys": "Typing only", "mouse": "Mouse only", "both": "Combined"}[s])
        ax.legend()
    axes[0].set_ylabel("True acceptance rate (1 - FRR)")
    fig.tight_layout()
    fig.savefig(OUT / "roc.png", dpi=150)
    print(f"Saved {OUT / 'results.md'} and {OUT / 'roc.png'}")


if __name__ == "__main__":
    main()
