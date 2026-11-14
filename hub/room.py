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

A3 UNRESOLVED DISCOMFORT (no single fairness score)
  Per person: minutes present AND uncomfortable with no feasible fix (the summary's
  `unresolved`, which includes "not possible"). Kept after the person leaves, so it stays
  visible. When no setpoint suits everyone, people with more unresolved minutes weigh more
  (1 + minutes/30, at most 3). 20+ unresolved minutes since the last agreement also allow
  an early re-check (A1 cadence). With --demo, time counts 10x (labelled ACCELERATED).

A4 ENERGY IN THREE SEPARATE LAYERS
  measured  : what the hub saw (people present, comfortable, fix available, unresolved)
  proposed  : the recommendation / agreement (needs a person; thermostat not verified)
  modelled  : research context only, NO percentage claimed for this device:
              Hoyt, Arens & Zhang (2015), Building and Environment 88:89-96,
              doi:10.1016/j.buildenv.2014.09.010 (simulation; depends on climate and on
              the building's ventilation minimum airflow).
"""
from __future__ import annotations

import threading

CANDIDATES = [round(18.0 + 0.5 * i, 1) for i in range(19)]      # 18.0 .. 27.0 degC
MIN_CHANGE = 0.5
RECHECK_S = 90 * 60
DEMO_RECHECK_S = 60
DEFAULT_SETPOINT = 21.5
DEMO_TIME_FACTOR = 10            # --demo: unresolved minutes count 10x (ACCELERATED)
MAX_GAP_S = 120                  # a longer gap between observations is not counted
EARLY_RECHECK_MIN = 20
MODELLED = {
    "text": ("Building simulations suggest that a wider acceptable setpoint range can reduce "
             "heating and cooling energy; how much depends on the climate and the building. "
             "No saving is claimed for this device."),
    "source": ("Hoyt, Arens & Zhang (2015). Extending air temperature setpoints: simulated energy "
               "savings and design considerations for new and retrofit buildings. Building and "
               "Environment 88, 89-96. doi:10.1016/j.buildenv.2014.09.010"),
}

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


def weight_for(minutes: float) -> float:
    return 1.0 + min(minutes / 30.0, 2.0)


def recommend(people: list[dict], mode: str, current: float, weights: dict | None = None) -> dict:
    present = [p for p in people if p.get("present")]
    base = {"mode": mode, "current": current, "setpoint": None, "change": None, "everyone_ok": None,
            "needs_fix": [], "left_out": [], "present": len(present)}
    if mode not in ("heating", "cooling"):
        return {**base, "reason": "unknown_mode"}
    if not present:
        return {**base, "reason": "nobody_present"}
    lower_is_saving = mode == "heating"
    scored = []
    weights = weights or {}
    for t in CANDIDATES:
        fits = [ok_at(p, t) for p in present]
        score = sum(weights.get(p["pid"], 1.0) for p, f in zip(present, fits) if f is not None)
        scored.append((round(score, 6), t, fits))
    best = max(sc for sc, _, _ in scored)
    options = [x for x in scored if x[0] == best]
    _, t, fits = (min if lower_is_saving else max)(options, key=lambda x: x[1])
    n = sum(f is not None for f in fits)
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
        self.time_factor = DEMO_TIME_FACTOR if demo else 1
        self.unresolved_s: dict[str, float] = {}       # A3: since the hub started
        self.since_agree_s: dict[str, float] = {}      # A3: since the last agreement
        self.started_at = clock()
        self._last_obs: float | None = None
        self._lock = threading.Lock()

    def people(self, real: list[dict]) -> list[dict]:
        """real: hub summaries view. Returns room people (pseudonyms only) + sims."""
        out = [{"pid": r["pid"], "present": r["present_effective"], "band_now": r["band_now"],
                "band_with_fix": r.get("band_with_fix"), "unresolved": r["unresolved"] and r["present_effective"],
                "state": r["state"], "sim": False, "stale": r["stale"]} for r in real]
        if self.sims_on:
            for s in SIMS:
                cls = class_at(s, self.setpoint)
                fixable = cls != 0 and _in(s["band_with_fix"], self.setpoint)
                out.append({**s, "present": True, "sim": True, "stale": False, "state": cls,
                            "unresolved": cls != 0 and not fixable})
        return out

    # ---- A3 ----
    def _observe(self, people):
        now = self.clock()
        if self._last_obs is not None:
            dt = min(max(now - self._last_obs, 0.0), MAX_GAP_S) * self.time_factor
            for p in people:
                if p["present"] and p["unresolved"]:
                    self.unresolved_s[p["pid"]] = self.unresolved_s.get(p["pid"], 0.0) + dt
                    self.since_agree_s[p["pid"]] = self.since_agree_s.get(p["pid"], 0.0) + dt
        self._last_obs = now

    def observe(self, real: list[dict]):
        """Call on every summary receipt so minutes accrue even when nobody watches the page."""
        with self._lock:
            self._observe(self.people(real))

    # ---- A4 ----
    def _energy(self, people, rec):
        here = [p for p in people if p["present"]]
        last = self.agreements[-1] if self.agreements else None
        if rec["setpoint"] is None:
            status = "none"
        elif rec["reason"] in ("propose",):
            status = "proposed"
        else:
            status = "agreed" if last and abs(last["to"] - self.setpoint) < 1e-6 else "keep"
        return {
            "measured": {
                "people_present": len(here),
                "desks_present": sum(1 for p in here if not p["sim"]),
                "comfortable": sum(1 for p in here if p["state"] == 0),
                "fix_available": sum(1 for p in here if p["state"] != 0 and not p["unresolved"]),
                "unresolved": sum(1 for p in here if p["unresolved"]),
                "unresolved_minutes": round(sum(self.unresolved_s.values()) / 60.0, 1),
                "includes_simulated": any(p["sim"] for p in here),
            },
            "proposed": {"status": status, "mode": rec["mode"], "current": self.setpoint,
                         "recommended": rec["setpoint"], "change": rec["change"],
                         "last_agreement": last, "thermostat_verified": False},
            "modelled": MODELLED,
        }

    def view(self, real: list[dict], mode: str) -> dict:
        with self._lock:
            people = self.people(real)
            self._observe(people)
            for p in people:
                p["unresolved_min"] = round(self.unresolved_s.get(p["pid"], 0.0) / 60.0, 1)
                p["weight"] = round(weight_for(p["unresolved_min"]), 2)
            rec = recommend(people, mode, self.setpoint, {p["pid"]: p["weight"] for p in people})
            present = frozenset(p["pid"] for p in people if p["present"])
            last = self.agreements[-1] if self.agreements else None
            long_unresolved = [p["pid"] for p in people if p["present"]
                               and self.since_agree_s.get(p["pid"], 0.0) >= EARLY_RECHECK_MIN * 60]
            waiting = (last is not None and self.clock() - last["at"] < self.recheck_s
                       and present == self._agreed_with and not long_unresolved)
            if rec["reason"] == "propose" and waiting:
                rec = {**rec, "reason": "recently_agreed",
                       "next_check_in_s": round(self.recheck_s - (self.clock() - last["at"]))}
            labels = (["SIMULATED"] if self.sims_on else []) + (["ACCELERATED"] if self.demo else [])
            return {"setpoint": self.setpoint, "recommendation": rec, "people": people,
                    "sims_on": self.sims_on, "agreements": self.agreements[-5:], "labels": labels,
                    "candidates": [CANDIDATES[0], CANDIDATES[-1]], "since": self.started_at,
                    "energy": self._energy(people, rec)}

    def agree(self, setpoint: float, real: list[dict], mode: str) -> dict:
        with self._lock:
            people = self.people(real)
            weights = {pid: weight_for(sec / 60.0) for pid, sec in self.unresolved_s.items()}
            rec = recommend(people, mode, self.setpoint, weights)
            if rec["setpoint"] is None or abs(rec["setpoint"] - setpoint) > 1e-6:
                raise ValueError("that is not the current recommendation")
            entry = {"at": self.clock(), "from": self.setpoint, "to": setpoint, "mode": mode,
                     "people": rec["present"], "simulated": self.sims_on}
            self.agreements.append(entry)
            self.setpoint = setpoint
            self._agreed_with = frozenset(p["pid"] for p in people if p["present"])
            self.since_agree_s = {}
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
             "band_with_fix": [19.6, 24.1], "unresolved": False, "stale": False, "state": -1}]
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
    # A3: unresolved minutes accrue (10x in demo), stay after leaving, and weigh in the fallback.
    t = [0.0]
    rm = Room(lambda: t[0], demo=True)
    cold = {"pid": "p-0c01", "present_effective": True, "band_now": [24.0, 27.0], "band_with_fix": None,
            "unresolved": True, "stale": False, "state": -1}
    warm = {"pid": "p-0w01", "present_effective": True, "band_now": [18.0, 20.0], "band_with_fix": None,
            "unresolved": True, "stale": False, "state": 1}
    rm.view([cold, warm], "heating")
    for _ in range(6):                       # 6 x 60 s real = 60 min counted (demo 10x)
        t[0] += 60
        rm.observe([cold])                   # only the cold person is here meanwhile
    v = rm.view([cold, warm], "heating")
    mins = {p["pid"]: p["unresolved_min"] for p in v["people"]}
    assert mins["p-0c01"] == 60.0 and mins["p-0w01"] == 0.0, mins
    r = v["recommendation"]
    assert not r["everyone_ok"] and r["setpoint"] >= 24.0, r          # long-suffering person weighs more
    gone = rm.view([{**cold, "present_effective": False}], "heating")
    assert gone["people"][0]["unresolved_min"] == 60.0                # stays visible after leaving
    # Gaps longer than 2 min are not counted.
    t[0] += 3600
    rm.observe([cold])
    assert round(rm.unresolved_s["p-0c01"] / 60) == 80                # +MAX_GAP_S x 10 = +20 min
    # A4: three layers, no percentage claimed.
    e = v["energy"]
    assert set(e) == {"measured", "proposed", "modelled"}
    assert e["measured"]["unresolved"] == 2 and e["proposed"]["thermostat_verified"] is False
    assert "%" not in e["modelled"]["text"] and "doi:10.1016/j.buildenv.2014.09.010" in e["modelled"]["source"]
    # Early re-check after 20+ unresolved minutes since the agreement.
    rm2 = Room(lambda: t[0], demo=False)
    desk = {"pid": "p-0001", "present_effective": True, "band_now": [22.6, 26.1], "band_with_fix": [19.6, 24.1],
            "unresolved": False, "stale": False, "state": -1}
    rm2.view([desk], "heating")
    rm2.agree(20.0, [desk], "heating")
    stuck = {**desk, "band_with_fix": None, "unresolved": True}
    assert rm2.view([stuck], "heating")["recommendation"]["reason"] == "recently_agreed"
    for _ in range(11):
        t[0] += 110
        rm2.observe([stuck])
    assert rm2.view([stuck], "heating")["recommendation"]["reason"] == "propose"
    print("room OK: A1 heating/cooling/unknown, fixes, left-out, 0.5 degC, agree + cadence; A2 sims; "
          "A3 minutes, persistence, weighting, early re-check; A4 three layers")


if __name__ == "__main__":
    _selftest()
