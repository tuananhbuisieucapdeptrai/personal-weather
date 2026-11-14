"""Physical-shutter detection for vision.py.  Owner: Minh (M2.4); written at kickoff.

Rule (docs/interfaces.md 0.2.2, docs/kickoff-guide.md item 4):
  every frame darker than DARK_THRESHOLD for HOLD_SECONDS  ->  shutter closed.
vision.py then releases the camera and reports camera "shutter". It does NOT watch for
the shutter reopening; capture restarts only via POST /control {"camera": "on"}.

Pure logic, no camera or numpy needed, so it is testable on the laptop.
Set DARK_THRESHOLD from tools/kickoff/shutter_calibrate.py.
"""
from __future__ import annotations

DARK_THRESHOLD = 12.0   # mean grey level 0..255; REPLACE with the calibrated value
HOLD_SECONDS = 3.0


def brightness(frame) -> float:
    """Mean grey level 0..255 of a numpy frame (grey or BGR)."""
    return float(frame.mean())


class ShutterDetector:
    def __init__(self, threshold: float = DARK_THRESHOLD, hold_s: float = HOLD_SECONDS):
        self.threshold = threshold
        self.hold_s = hold_s
        self._dark_since: float | None = None

    def reset(self):
        self._dark_since = None

    def update(self, level: float, now: float) -> bool:
        """Feed one frame's brightness and a monotonic timestamp. True = shutter closed."""
        if level >= self.threshold:
            self._dark_since = None          # one bright frame resets the timer
            return False
        if self._dark_since is None:
            self._dark_since = now
        return now - self._dark_since >= self.hold_s


def _selftest():
    d = ShutterDetector(threshold=10, hold_s=3)
    assert not d.update(80, 0.0)
    assert not d.update(3, 1.0)                  # dark starts
    assert not d.update(3, 3.5)                  # 2.5 s dark
    assert d.update(3, 4.0)                      # 3.0 s dark -> closed
    d.reset()
    assert not d.update(3, 10.0)
    assert not d.update(50, 12.0)                # bright frame resets
    assert not d.update(3, 13.0)
    assert not d.update(3, 15.9)
    assert d.update(3, 16.0)
    print("shutter OK")


if __name__ == "__main__":
    _selftest()
