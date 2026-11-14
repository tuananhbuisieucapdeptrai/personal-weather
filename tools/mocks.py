"""Fake sensors, knob and vision.  Owner: Tuan Anh (T1.1).

Same public API as the real modules, so main.py swaps one import:

    from mocks import bridge as bridge_io, vision        # laptop, MOCK INPUT
    import bridge_io, vision                              # UNO Q, LIVE

    bridge.start(on_message) / bridge.send(msg)           == device/python/bridge_io.py
    vision.start() / vision.stop() / vision.latest()      == device/python/vision.py

Every message produced or accepted here passes device/python/contracts.py, so code that
works against the mocks speaks the real contract. Anything from mocks must be shown as
"MOCK INPUT" on the dashboard (LABEL below); speed != 1 is also "ACCELERATED".

Two ways to drive time:
  - realtime=True (default): a daemon thread advances simulated time; speed=10 runs 10x.
  - realtime=False: call bridge.step(seconds) yourself; deterministic, for tests.

Try it:   python3 tools/mocks.py --scenario cold --speed 20 --seconds 5
Self-test: python3 tools/mocks.py --selftest
"""
from __future__ import annotations

import math
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device", "python"))
import contracts  # noqa: E402

LABEL = "MOCK INPUT"

# ---- Temperature / humidity scenarios: f(sim_seconds) -> (t degC, rh %) -------------
# Values are what a Modulino Thermo outside the case might plausibly report.


def _office(s):    # heated office: 21.5 degC with a slow 30-min heating cycle
    return 21.5 + 0.4 * math.sin(2 * math.pi * s / 1800), 38 + 2 * math.sin(2 * math.pi * s / 2400)


def _cold(s):      # desk near the entrance / window opened: 21.5 -> 19.0 over 10 min
    return 21.5 - 2.5 * min(s / 600, 1.0), 38 + 4 * min(s / 600, 1.0)


def _warm(s):      # sunny afternoon / heating too high: 21.5 -> 25.0 over 10 min
    return 21.5 + 3.5 * min(s / 600, 1.0), 38 - 4 * min(s / 600, 1.0)


def _steady(s):    # constant, for unit tests
    return 21.5, 40.0


SCENARIOS = {"office": _office, "cold": _cold, "warm": _warm, "steady": _steady}


class MockBridge:
    """Pretends to be the sketch: env at 1 Hz (simulated time), scripted knob, faces logged."""

    def __init__(self, scenario="office", knob_script=None, speed=1.0, noise=0.05,
                 seed=0, realtime=True, verbose=False):
        if scenario not in SCENARIOS:
            raise ValueError(f"scenario must be one of {sorted(SCENARIOS)}")
        self.scenario = scenario
        self.speed = speed
        self.noise = noise
        self.realtime = realtime
        self.verbose = verbose
        self.sim_time = 0.0
        self.sent: list[tuple[float, dict]] = []      # (sim_time, msg) sent to the "sketch"
        self.knob_script = sorted(knob_script or [], key=lambda e: e[0])  # [(sim_s, msg)]
        self._rng = random.Random(seed)
        self._next_env = 0.0
        self._on_message = None
        self._lock = threading.Lock()
        self._thread = None
        self._running = False

    @property
    def labels(self):
        return [LABEL] + (["ACCELERATED"] if self.speed != 1 else [])

    # ---- bridge_io API ----
    def start(self, on_message):
        self._on_message = on_message
        if self.realtime and not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def send(self, msg):
        contracts.check_to_sketch(msg)
        with self._lock:
            self.sent.append((self.sim_time, msg))
        if self.verbose:
            print(f"[mock sketch t={self.sim_time:6.1f}] <- {msg}", flush=True)

    # ---- test / demo controls ----
    def stop(self):
        self._running = False

    def step(self, seconds: float):
        """Advance simulated time, emitting every env/knob message that falls inside it."""
        end = self.sim_time + seconds
        while True:
            next_knob = self.knob_script[0][0] if self.knob_script else math.inf
            nxt = min(self._next_env, next_knob)
            if nxt > end:
                break
            self.sim_time = nxt
            if nxt == next_knob:
                self._deliver(self.knob_script.pop(0)[1])
            else:
                self._deliver(self._env_message())
                self._next_env += 1.0
        self.sim_time = end

    def inject(self, msg):
        """Deliver a sketch -> Linux message right now (e.g. a knob action from a test)."""
        self._deliver(msg)

    def turn(self, pos):
        self.inject({"knob": "turn", "pos": pos})

    def press(self):
        self.inject({"knob": "press"})

    def last_face(self):
        faces = [m for _, m in self.sent if "face" in m]
        return faces[-1] if faces else None

    # ---- internals ----
    def _env_message(self):
        t, rh = SCENARIOS[self.scenario](self.sim_time)
        t += self._rng.gauss(0, self.noise)
        rh += self._rng.gauss(0, self.noise * 4)
        return {"t": round(t, 1), "rh": round(min(max(rh, 0.0), 100.0), 1)}

    def _deliver(self, msg):
        contracts.check_from_sketch(msg)
        if self.verbose:
            print(f"[mock sketch t={self.sim_time:6.1f}] -> {msg}", flush=True)
        if self._on_message:
            self._on_message(msg)

    def _run(self):
        tick = 0.1
        while self._running:
            time.sleep(tick)
            self.step(tick * self.speed)


class MockVision:
    """Pretends to be vision.py. Script person/clothing changes or set them directly."""

    def __init__(self, clock=None, script=None, present=True, clothing="none", conf=0.9):
        self._clock = clock or (lambda: 0.0)
        self._script = sorted(script or [], key=lambda e: e[0])   # [(sim_s, {fields})]
        self._lock = threading.Lock()
        self._state = {"present": present, "clothing": clothing, "conf": conf}
        self.camera = "on"
        self._apply(self._state)

    def attach_clock(self, bridge: MockBridge):
        """Use the bridge's simulated time for scripted changes."""
        self._clock = lambda: bridge.sim_time

    # ---- vision API ----
    def start(self):
        with self._lock:
            self.camera = "on"

    def stop(self):
        with self._lock:
            self.camera = "off"

    def latest(self) -> dict:
        now = self._clock()
        with self._lock:
            while self._script and self._script[0][0] <= now:
                self._apply(self._script.pop(0)[1])
            if self.camera != "on":
                msg = {"present": None, "clothing": "uncertain", "conf": None, "camera": self.camera}
            else:
                msg = {**self._state, "camera": "on"}
        return contracts.check_vision(msg)

    # ---- test / demo controls ----
    def set_person(self, present=True, clothing="none", conf=0.9):
        with self._lock:
            self._apply({"present": present, "clothing": clothing, "conf": conf})

    def close_shutter(self):
        """Like the real thing: capture stops and stays stopped until start()."""
        with self._lock:
            self.camera = "shutter"

    def _apply(self, fields):
        s = {**self._state, **fields}
        if not s["present"]:
            s.update(clothing="uncertain", conf=None)
        elif s["clothing"] in ("outer", "none") and s["conf"] is None:
            s["conf"] = 0.9
        contracts.check_vision({**s, "camera": "on"})
        self._state = s


# Module-level instances so `from mocks import bridge, vision` just works.
bridge = MockBridge()
vision = MockVision()
vision.attach_clock(bridge)


def _selftest():
    got = []
    b = MockBridge(scenario="cold", realtime=False, seed=1, knob_script=[
        (2.5, {"knob": "turn", "pos": -1}), (3.0, {"knob": "press"})])
    b.start(got.append)
    b.step(10)
    env = [m for m in got if "t" in m]
    knob = [m for m in got if "knob" in m]
    assert len(env) == 11, len(env)                       # t = 0..10 inclusive
    assert knob == [{"knob": "turn", "pos": -1}, {"knob": "press"}]
    assert got.index(knob[0]) == 3                        # after env at t=0,1,2
    b.step(600)
    assert 18.7 < got[-1]["t"] < 19.3, got[-1]            # cold scenario reached ~19 degC
    b.send({"face": "snow"})
    b.send({"face": "text", "text": "DO"})
    assert b.last_face() == {"face": "text", "text": "DO"}
    try:
        b.send({"face": "frown"})
        raise AssertionError("invalid face accepted")
    except contracts.ContractError:
        pass

    v = MockVision(script=[(5, {"clothing": "outer", "conf": 0.86})])
    v.attach_clock(b)
    b.sim_time = 0
    assert v.latest()["clothing"] == "none"
    b.sim_time = 5
    assert v.latest() == {"present": True, "clothing": "outer", "conf": 0.86, "camera": "on"}
    v.set_person(present=False)
    assert v.latest() == {"present": False, "clothing": "uncertain", "conf": None, "camera": "on"}
    v.close_shutter()
    assert v.latest()["camera"] == "shutter" and v.latest()["present"] is None
    v.start()
    assert v.latest()["camera"] == "on"
    v.stop()
    assert v.latest()["camera"] == "off"

    rb = MockBridge(scenario="steady", speed=50, realtime=True)
    seen = []
    rb.start(seen.append)
    time.sleep(0.3)
    rb.stop()
    assert len(seen) >= 5 and rb.labels == [LABEL, "ACCELERATED"]
    print("mocks OK")


def _demo(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="office", choices=sorted(SCENARIOS))
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--seconds", type=float, default=5.0)
    args = ap.parse_args(argv)
    b = MockBridge(scenario=args.scenario, speed=args.speed, verbose=True,
                   knob_script=[(3, {"knob": "turn", "pos": -1}), (4, {"knob": "press"})])
    print(f"{' / '.join(b.labels)}: scenario={args.scenario}", flush=True)
    b.start(lambda m: None)
    time.sleep(args.seconds)
    b.stop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        _demo(sys.argv[1:])
