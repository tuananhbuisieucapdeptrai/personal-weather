"""Environment smoothing and freshness (spec C1).  Owner: Tuan Anh.

Kickoff agreement (docs/interfaces.md): the sketch sends RAW t/rh at 1 Hz (verified on
the board by Minh); smoothing happens here, in Python, so it is testable with mocks.

    f = EnvFilter()
    f.update({"t": 23.4, "rh": 41.2}, now)      # each env message from bridge_io
    f.reading(now) -> {"t": 23.3, "rh": 41.0, "raw_t": 23.4, "raw_rh": 41.2,
                        "stale": False, "age_s": 0.0, "samples": 12}

- Exponential moving average with a time constant (default 10 s), so a missed message
  doesn't distort it. The first sample initialises the average.
- Raw values are kept next to the smoothed ones (evidence panel / debugging).
- stale = no valid env message for more than 5 s; comfort logic must not use stale data.
"""
from __future__ import annotations

import math

STALE_AFTER_S = 5.0
TIME_CONSTANT_S = 10.0


class EnvFilter:
    def __init__(self, tau_s: float = TIME_CONSTANT_S, stale_after_s: float = STALE_AFTER_S):
        self.tau_s = tau_s
        self.stale_after_s = stale_after_s
        self.t = self.rh = None
        self.raw_t = self.raw_rh = None
        self.last_at = None
        self.samples = 0

    def update(self, msg: dict, now: float) -> None:
        """Feed one contract env message ({"t", "rh"}, already validated by bridge_io)."""
        t, rh = float(msg["t"]), float(msg["rh"])
        if self.last_at is None or now - self.last_at > self.stale_after_s:
            self.t, self.rh = t, rh          # first sample, or recovering from a gap: restart
        else:
            a = 1.0 - math.exp(-max(now - self.last_at, 0.0) / self.tau_s)
            self.t += a * (t - self.t)
            self.rh += a * (rh - self.rh)
        self.raw_t, self.raw_rh, self.last_at = t, rh, now
        self.samples += 1

    def reading(self, now: float) -> dict:
        if self.last_at is None:
            return {"t": None, "rh": None, "raw_t": None, "raw_rh": None,
                    "stale": True, "age_s": None, "samples": 0}
        age = now - self.last_at
        return {"t": round(self.t, 2), "rh": round(self.rh, 1),
                "raw_t": self.raw_t, "raw_rh": self.raw_rh,
                "stale": age > self.stale_after_s, "age_s": round(age, 1),
                "samples": self.samples}


def _selftest():
    f = EnvFilter(tau_s=10)
    assert f.reading(0)["stale"] and f.reading(0)["t"] is None
    f.update({"t": 20.0, "rh": 40.0}, 0)
    assert f.reading(0)["t"] == 20.0 and not f.reading(0)["stale"]
    for s in range(1, 11):                      # step to 24 degC for 10 s
        f.update({"t": 24.0, "rh": 40.0}, s)
    r = f.reading(10)
    assert 22.4 < r["t"] < 22.7, r              # ~63% of the step after one time constant
    assert r["raw_t"] == 24.0 and r["samples"] == 11
    f.update({"t": 30.0, "rh": 40.0}, 10.5)     # one spike barely moves the average
    assert f.reading(10.5)["t"] < 23.0
    assert not f.reading(15.4)["stale"] and f.reading(15.6)["stale"]   # >5 s silence
    f.update({"t": 21.0, "rh": 45.0}, 30)       # after a gap: restart, don't blend old data
    assert f.reading(30)["t"] == 21.0 and not f.reading(30)["stale"]
    print("sensing OK")


if __name__ == "__main__":
    _selftest()
