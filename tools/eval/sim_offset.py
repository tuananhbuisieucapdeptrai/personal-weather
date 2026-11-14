"""SIMULATED sanity check of the personal-offset rule (not evidence about real people).

Synthetic people have a hidden true offset; each vote is the class of
(baseline PMV + true offset + noise). Votes arrive at random office conditions.
The prospective evaluation (pre-update predictions) compares baseline vs personal,
exactly as on the device. Output is labelled SIMULATED.

    python3 tools/eval/sim_offset.py
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "device", "python"))
import comfort  # noqa: E402
import evaluation  # noqa: E402

PEOPLE = {"runs cold (-0.7)": -0.7, "average (0.0)": 0.0, "runs warm (+0.6)": 0.6}
NOISE_SD = 0.35
VOTES = 15
RUNS = 200


def simulate(true_offset, rng):
    log, m = evaluation.FeedbackLog(), comfort.PersonalModel()
    for i in range(VOTES):
        t = rng.uniform(19.5, 25.0)
        rh = rng.uniform(30, 50)
        clothing = rng.choice(["none", "outer"])
        base = comfort.baseline_pmv(t, rh, clothing)
        vote = comfort.classify(base + true_offset + rng.gauss(0, NOISE_SD))
        log.append("p", m.observe(vote, base), "feedback", at=i, labels=["SIMULATED"])
    return log.report(), m.offset


def main():
    rng = random.Random(7)
    print(f"SIMULATED: {RUNS} runs x {VOTES} votes per person, vote noise sd {NOISE_SD} PMV\n")
    print(f"{'person':18} {'base acc':>8} {'pers acc':>8} {'base MAE':>8} {'pers MAE':>8} {'learned offset':>14}")
    for name, true in PEOPLE.items():
        rs = [simulate(true, rng) for _ in range(RUNS)]
        avg = lambda k: sum(r[0][k] for r in rs) / RUNS  # noqa: E731
        off = sum(r[1] for r in rs) / RUNS
        print(f"{name:18} {avg('baseline_accuracy'):8.2f} {avg('personal_accuracy'):8.2f} "
              f"{avg('baseline_mae'):8.2f} {avg('personal_mae'):8.2f} {off:+14.2f}")


if __name__ == "__main__":
    main()
