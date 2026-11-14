"""Room level: setpoint recommendation (A1) and simulated coworkers (A2).  Owner: Tuan Anh (T4.3, T4.4).

Input: only the hub's pseudonymous summaries (spec C8): band_now, band_with_fix, present.
No names, votes or models ever reach this module.

A1 RECOMMENDATION
  - A person is OK at setpoint T if T is in band_now, or in band_with_fix when a feasible
    fix exists (band_with_fix present). A person whose fix works now is not assumed fine
    at every setpoint: the bands decide.
  - Heating: the LOWEST candidate where every present person is OK. Cooling: the HIGHEST.
    Unknown: no recommendation (no energy claim).
  - Nobody fits at any setpoint: the setpoint that suits the most people (ties: the energy
    direction), and everyone left out is listed so discomfort stays visible.
  - Proposal only if it differs from the current setpoint by >= 0.5 degC. After an
    agreement, no new proposal for RECHECK_S (90 min) unless people arrive or leave.
    Nothing changes without "Agree"; the hub never touches a thermostat.

A2 SIMULATED COWORKERS
  Three synthetic summaries, flagged sim=True and labelled SIMULATED in the UI.
"""
from __future__ import annotations

import threading

CANDIDATES = [round(18.0 + 0.5 * i, 1) for i in range(19)]      # 18.0 .. 27.0 degC
MIN_CHANGE = 0.5
RECHECK_S = 90 * 60
DEMO_RECHECK_S = 60
DEFAULT_SETPOINT = 21.5

SIMS = [
    {"pid": "p-5a01", "name": "Coworker A", "note": "runs warm, already without a layer",
     "band_now": [20.0, 23.0], "band_with_fix": None},
    {"pid": "p-5b02", "name": "Coworker B", "note": "runs cold, has a jacket at hand",
     "band_now": [22.0, 25.5], "band_with_fix": [19.5, 23.5]},
    {"pid": "p-5c03", "name": "Coworker C", "note": "average",
     "band_now": [21.0, 24.5], "band_with_fix": [19.0, 23.0]},
]


def _in(band, t):
    return band is not None and band[0] <= t <= band[1]


def ok_at(person: dict, t: float) -> str | None:
    """'as_is', 'with_fix' or None (not OK at t)."""
    if _in(person.get("band_now"), t):
        return "as_is"
    if _in(person.get("band_with_fix"), t):
        return "with_fix"
    return None


def class_at(person: dict, t: float) -> int:
    """-1 / 0 / +1 at temperature t, as the person is now (no fix)."""
    b = person.get("band_now")
    if b is None:
        return 0
    return -1 if t < b[0] else 1 if t > b[1] else 0


def recommend(people: list[dict], mode: str, current: float) -> dict:
    present = [p for p in people if p.get("present")]
    base = {"mode": mode, "current": current, "setpoint": None, "change": None, "everyone_ok": None,
            "needs_fix": [], "left_out": [], "present": len(present)}
    if mode not in ("heating", "cooling"):
        return {**base, "reason": "unknown_mode"}
    if not present:
        return {**base, "reason": "nobody_present"}
    lower_is_saving = mode == "heating"
    scored = []
    for t in CANDIDATES:
        fits = [ok_at(p, t) for p in present]
        scored.append((sum(f is not None for f in fits), t, fits))
    best_n = max(n for n, _, _ in scored)
    options = [s for s in scored if s[0] == best_n]
    n, t, fits = (min if lower_is_saving else max)(options, key=lambda s: s[1])
    change = round(t - current, 1)
    return {**base, "setpoint": t, "change": change, "everyone_ok": n == len(present),
            "needs_fix": [p["pid"] for p, f in zip(present, fits) if f == "with_fix"],
            "left_out": [p["pid"] for p, f in zip(present, fits) if f is None],
            "saves_energy": (change < 0) if lower_is_saving else (change > 0),
            "reason": "propose" if abs(change) >= MIN_CHANGE else "keep_current"}


class Room:
    """Room state on the hub: current setpoint, agreements, simulated coworkers."""

    def __init__(self, clock, demo: bool = False, setpoint: float = DEFAULT_SETPOINT):
        self.clock = clock
        self.demo = demo
        self.recheck_s = DEMO_RECHECK_S if demo else RECHECK_S
        self.setpoint = setpoint
        self.sims_on = False
        self.agreements: list[dict] = []
        self._agreed_with: frozenset | None = None
        self._lock = threading.Lock()

    def people(self, real: list[dict]) -> list[dict]:
        """real: hub summaries view. Returns room people (pseudonyms only) + sims."""
        out = [{"pid": r["pid"], "present": r["present_effective"], "band_now": r["band_now"],
                "band_with_fix": r.get("band_with_fix"), "unresolved": r["unresolved"] and r["present_effective"],
                "sim": False, "stale": r["stale"]} for r in real]
        if self.sims_on:
            for s in SIMS:
                cls = class_at(s, self.setpoint)
                fixable = cls != 0 and _in(s["band_with_fix"], self.setpoint)
                out.append({**s, "present": True, "sim": True, "stale": False,
                            "unresolved": cls != 0 and not fixable})
        return out

    def view(self, real: list[dict], mode: str) -> dict:
        with self._lock:
            people = self.people(real)
            rec = recommend(people, mode, self.setpoint)
            present = frozenset(p["pid"] for p in people if p["present"])
            last = self.agreements[-1] if self.agreements else None
            waiting = (last is not None and self.clock() - last["at"] < self.recheck_s
                       and present == self._agreed_with)
            if rec["reason"] == "propose" and waiting:
                rec = {**rec, "reason": "recently_agreed",
                       "next_check_in_s": round(self.recheck_s - (self.clock() - last["at"]))}
            labels = (["SIMULATED"] if self.sims_on else []) + (["ACCELERATED"] if self.demo else [])
            return {"setpoint": self.setpoint, "recommendation": rec, "people": people,
                    "sims_on": self.sims_on, "agreements": self.agreements[-5:], "labels": labels,
                    "candidates": [CANDIDATES[0], CANDIDATES[-1]]}

    def agree(self, setpoint: float, real: list[dict], mode: str) -> dict:
        with self._lock:
            people = self.people(real)
            rec = recommend(people, mode, self.setpoint)
            if rec["setpoint"] is None or abs(rec["setpoint"] - setpoint) > 1e-6:
                raise ValueError("that is not the current recommendation")
            entry = {"at": self.clock(), "from": self.setpoint, "to": setpoint, "mode": mode,
                     "people": rec["present"], "simulated": self.sims_on}
            self.agreements.append(entry)
            self.setpoint = setpoint
            self._agreed_with = frozenset(p["pid"] for p in people if p["present"])
            return entry

    def set_sims(self, on: bool):
        with self._lock:
            self.sims_on = bool(on)

    def set_setpoint(self, value: float):
        """The thermostat's actual setting, entered by a person (not an agreement)."""
        if not (CANDIDATES[0] <= value <= CANDIDATES[-1]):
            raise ValueError(f"setpoint must be {CANDIDATES[0]}..{CANDIDATES[-1]} degC")
        with self._lock:
            self.setpoint = round(float(value), 1)


def _selftest():
    ta_layer = {"pid": "p-0001", "present": True, "band_now": [22.6, 26.1], "band_with_fix": [19.6, 24.1]}
    ta_no_fix = {**ta_layer, "band_with_fix": None}                    # said "not possible"
    sims = [{**s, "present": True} for s in SIMS]

    # Demo story: the cold person solved with a layer lets the room stay lower.
    r = recommend([ta_layer] + sims, "heating", 21.5)
    assert r["setpoint"] == 20.0 and r["everyone_ok"] and r["reason"] == "propose" and r["saves_energy"], r
    assert set(r["needs_fix"]) == {"p-0001", "p-5b02", "p-5c03"}      # at 20.0 they wear their layer
    r2 = recommend([ta_no_fix] + sims, "heating", 21.5)
    assert r2["setpoint"] == 23.0 and r2["everyone_ok"] and not r2["saves_energy"], r2   # no fix -> warmer room
    # Cooling: the highest setpoint everyone accepts.
    r = recommend([ta_layer] + sims, "cooling", 24.0)
    assert r["setpoint"] == 23.0 and r["reason"] == "propose" and r["saves_energy"] is False, r
    # Unknown mode / nobody present: no recommendation.
    assert recommend(sims, "unknown", 21.5)["setpoint"] is None
    assert recommend([{**ta_layer, "present": False}], "heating", 21.5)["reason"] == "nobody_present"
    # Nobody fits everywhere: most people OK, the rest listed (stays visible).
    hot = {"pid": "p-0002", "present": True, "band_now": [18.0, 19.0], "band_with_fix": None}
    cold = {"pid": "p-0003", "present": True, "band_now": [25.0, 27.0], "band_with_fix": None}
    r = recommend([hot, cold, sims[2]], "heating", 21.5)
    assert not r["everyone_ok"] and len(r["left_out"]) == 1, r
    # Small change -> keep.
    assert recommend([{"pid": "p-9", "present": True, "band_now": [21.5, 24], "band_with_fix": None}],
                     "heating", 21.5)["reason"] == "keep_current"

    # Cadence: agree -> no new proposal within the window unless people change.
    now = [1000.0]
    room = Room(lambda: now[0], demo=True)
    real = [{"pid": "p-0001", "present_effective": True, "band_now": [22.6, 26.1],
             "band_with_fix": [19.6, 24.1], "unresolved": False, "stale": False}]
    room.set_sims(True)
    v = room.view(real, "heating")
    assert v["recommendation"]["reason"] == "propose" and v["labels"] == ["SIMULATED", "ACCELERATED"]
    room.agree(v["recommendation"]["setpoint"], real, "heating")
    assert room.setpoint == 20.0
    try:
        room.agree(25.0, real, "heating")
        raise AssertionError("agreed to a non-recommendation")
    except ValueError:
        pass
    real[0]["band_with_fix"] = None                                   # now "not possible"
    v = room.view(real, "heating")
    assert v["recommendation"]["reason"] == "recently_agreed", v["recommendation"]
    real.append({**real[0], "pid": "p-0009"})                         # someone arrives -> re-check
    assert room.view(real, "heating")["recommendation"]["reason"] == "propose"
    real.pop()
    now[0] += DEMO_RECHECK_S + 1
    assert room.view(real, "heating")["recommendation"]["reason"] == "propose"
    # Sims' state follows the setpoint; unresolved when outside band with no fix.
    room.set_setpoint(26.0)
    a = next(p for p in room.view(real, "heating")["people"] if p["pid"] == "p-5a01")
    assert a["unresolved"] and a["sim"]
    print("room OK: A1 heating/cooling/unknown, fixes, left-out, 0.5 degC, agree + cadence; A2 sims")


if __name__ == "__main__":
    _selftest()
