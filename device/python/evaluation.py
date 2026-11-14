"""Prospective evaluation of the comfort model (spec C3).  Owner: Tuan Anh (T2.3).

Declared metric: on each new feedback vote (-1 cold, 0 OK, +1 warm), BEFORE updating,
record the baseline and the personal prediction, both as one of the three classes
(comfort.PersonalModel.observe() returns exactly that record). Report:
  - prospective 3-class accuracy, baseline vs personal
  - mean absolute error on the -1/0/+1 scale, baseline vs personal
  - sample count; and say so plainly if the personal model is not better.

Storage: append-only JSON lines on the device (state/feedback_log.jsonl). Stored on the
device only; never sent to the hub (privacy receipt). Each entry carries labels
(e.g. "MOCK INPUT") so mock or simulated votes are never mixed into LIVE results.
"""
from __future__ import annotations

import json
import os
import threading

import comfort

MIN_N_FOR_VERDICT = 5
NON_LIVE_LABELS = {"MOCK INPUT", "SIMULATED"}


class FeedbackLog:
    def __init__(self, path: str | None = None):
        self.path = path
        self._lock = threading.Lock()
        self._entries: list[dict] = []
        if path and os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._entries.append(json.loads(line))
                        except ValueError:
                            pass          # a torn last line after a power cut: skip it

    def append(self, profile: str, record: dict, source: str, at: float,
               labels: list[str] | None = None, clothing: str | None = None) -> dict:
        """record: the dict returned by PersonalModel.observe() (pre-update predictions)."""
        entry = {"at": at, "profile": profile, "source": source, "clothing": clothing,
                 "labels": list(labels or []), **record}
        with self._lock:
            self._entries.append(entry)
            if self.path:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
        return entry

    def entries(self, profile: str | None = None, live_only: bool = False) -> list[dict]:
        with self._lock:
            out = list(self._entries)
        if profile:
            out = [e for e in out if e["profile"] == profile]
        if live_only:
            out = [e for e in out if not NON_LIVE_LABELS & set(e.get("labels", []))]
        return out

    def report(self, profile: str | None = None, live_only: bool = False) -> dict:
        es = self.entries(profile, live_only)
        r = comfort.score(es)
        r["by_source"] = {s: sum(1 for e in es if e["source"] == s) for s in {e["source"] for e in es}}
        r["labels"] = sorted({lab for e in es for lab in e.get("labels", [])}) or ["LIVE"]
        r["verdict"] = verdict(r)
        return r


def verdict(r: dict) -> str:
    n = r.get("n", 0)
    if n == 0:
        return "no feedback yet"
    if n < MIN_N_FOR_VERDICT:
        return f"too few samples to compare (n={n}; need {MIN_N_FOR_VERDICT})"
    db = r["personal_accuracy"] - r["baseline_accuracy"]
    dm = r["baseline_mae"] - r["personal_mae"]
    if db > 0 or (db == 0 and dm > 0):
        return f"personal model better than baseline so far (n={n})"
    if db == 0 and dm == 0:
        return f"no difference between personal model and baseline (n={n})"
    return f"personal model is NOT better than the baseline (n={n})"


def _selftest():
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "state", "feedback_log.jsonl")
    log = FeedbackLog(path)
    assert log.report()["verdict"] == "no feedback yet"
    m = comfort.PersonalModel()
    base = comfort.baseline_pmv(21.5, 40, "none")          # baseline says cold
    for i in range(6):                                     # this person keeps saying OK
        log.append("minh", m.observe(comfort.OK, base), "feedback", at=i, clothing="none")
    log.append("tuananh", comfort.PersonalModel().observe(comfort.COLD, base), "feedback", at=9,
               labels=["MOCK INPUT"], clothing="none")
    r = log.report("minh")
    assert r["n"] == 6 and r["baseline_accuracy"] == 0.0 and r["personal_accuracy"] > 0.5, r
    assert r["verdict"].startswith("personal model better"), r
    assert log.report(live_only=True)["n"] == 6 and log.report()["n"] == 7
    assert log.report("tuananh")["labels"] == ["MOCK INPUT"]
    assert FeedbackLog(path).report()["n"] == 7                      # persisted
    with open(path, "a") as f:
        f.write('{"torn": ')                                         # power cut mid-write
    assert FeedbackLog(path).report()["n"] == 7
    assert verdict({"n": 3}).startswith("too few")
    assert verdict({"n": 9, "baseline_accuracy": 0.6, "personal_accuracy": 0.5,
                    "baseline_mae": 0.4, "personal_mae": 0.5}).startswith("personal model is NOT")
    print("evaluation OK: prospective log, accuracy/MAE, honest verdict, live/mock split, persistence")


if __name__ == "__main__":
    _selftest()
