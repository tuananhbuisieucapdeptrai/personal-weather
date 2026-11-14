"""Suggestion engine (T2.1) and follow-up + fix experience (T2.2).  Owner: Tuan Anh.

T2.2 summary (spec C7; details above class FixExperience):
  after "Do it": wait 5 min (30 s in the demo, labelled ACCELERATED) -> check the clothing
  (camera / dashboard / not visible / contradicted) -> ask "how do you feel now?" ->
  vote updates the personal offset (prospective record) and, unless the camera contradicts
  the action, the Beta(1, 1) fix experience: OK = helped, still uncomfortable = didn't.
  No answer = unknown, nothing updated. "Not possible" never starts a follow-up.

Spec section 2 + C6. One SuggestionEngine per profile.

DECIDE (evaluate): offer a fix only when ALL hold
  present, env fresh, no follow-up running, no suggestion on screen,
  personal prediction is cold or warm, clothing known (vision or dashboard override),
  a fix exists for that clothing, the comfort model predicts the fix makes the person OK,
  the fix is not blocked by "Not possible", and nothing was offered in the last 15 min.
  Every outcome has a `reason`, so the dashboard can explain why nothing was offered.

FIXES: add_layer (wearing none -> outer), remove_layer (wearing outer -> none).

ENERGY ROLE by mode (what the energy panel may count; never more than this):
  heating + add_layer    -> "replaces_heat_request"     (counted: Measured layer)
  cooling + remove_layer -> "replaces_cooling_request"  (counted: Measured layer)
  any other fix / unknown mode -> "comfort_only"         (never counted as saving)
  room_signal: warm in heating -> "room_may_be_overheated"; cold in cooling ->
  "room_may_be_overcooled" (input for the room recommendation A1, via summary.state).

RESPONSES (knob: +1 DO, 0 LATER, -1 NO; see ResponsePicker):
  do_it        -> follow-up (T2.2), no other effect here
  not_possible -> constraint, NO penalty: this fix is not offered again in this mode
                  for NOT_POSSIBLE_HOLD_S (4 h), and band_with_fix is omitted meanwhile
  not_now      -> NO penalty: may be offered again after the 15-min gap
  no answer within RESPONSE_TIMEOUT_S -> recorded as no_response (unknown, no penalty)

SUMMARY FIELDS (C8):
  band_with_fix: band if the mode's energy-relevant fix were applied (heating: add a layer;
    cooling: remove one), unless not applicable or blocked -> None (summary omits the key).
  unresolved: personal prediction not OK and no known feasible, unblocked fix.
    Unknown clothing counts as unresolved: discomfort stays visible (principle 4).
"""
from __future__ import annotations

import comfort
from comfort import COLD, OK, WARM

MIN_GAP_S = 15 * 60
NOT_POSSIBLE_HOLD_S = 4 * 3600
RESPONSE_TIMEOUT_S = 120

DO_IT, NOT_NOW, NOT_POSSIBLE, NO_RESPONSE = "do_it", "not_now", "not_possible", "no_response"
RESPONSE_FOR_POS = {1: DO_IT, 0: NOT_NOW, -1: NOT_POSSIBLE}
TEXT_FOR_POS = {1: "DO", 0: "LATER", -1: "NO"}

FIXES = {
    "add_layer": {"from": "none", "to": "outer", "helps": COLD,
                  "face": "suggest_layer_on", "label": "Add a layer?"},
    "remove_layer": {"from": "outer", "to": "none", "helps": WARM,
                     "face": "suggest_layer_off", "label": "Remove a layer?"},
}
ENERGY_FIX = {"heating": "add_layer", "cooling": "remove_layer"}


def energy_role(mode: str, fix: str) -> str:
    if mode == "heating" and fix == "add_layer":
        return "replaces_heat_request"
    if mode == "cooling" and fix == "remove_layer":
        return "replaces_cooling_request"
    return "comfort_only"


def room_signal(mode: str, personal_class: int) -> str | None:
    if mode == "heating" and personal_class == WARM:
        return "room_may_be_overheated"
    if mode == "cooling" and personal_class == COLD:
        return "room_may_be_overcooled"
    return None


def fix_for(clothing: str, personal_class: int) -> str | None:
    for name, f in FIXES.items():
        if f["from"] == clothing and f["helps"] == personal_class:
            return name
    return None


class SuggestionEngine:
    def __init__(self):
        self.last_offered_at: float | None = None
        self.blocked: dict[str, float] = {}       # "fix|mode" -> blocked until (epoch s)
        self.active: dict | None = None            # suggestion on screen, awaiting a response
        self.log: list[dict] = []                  # offers and responses (Measured layer)

    # ---- constraints ----
    def is_blocked(self, fix: str, mode: str, now: float) -> bool:
        until = self.blocked.get(f"{fix}|{mode}")
        return until is not None and now < until

    # ---- decide ----
    def evaluate(self, now: float, t: float, rh: float, clothing: str, model: comfort.PersonalModel,
                 mode: str, present: bool = True, env_stale: bool = False,
                 follow_up_pending: bool = False, reported_class: int | None = None) -> dict:
        """Decide whether to offer a fix now. Pure: nothing changes until offer().
        reported_class: a fresh knob report (-1/0/+1) overrides the model's prediction."""
        self.expire(now)
        known = clothing in ("outer", "none")
        pcls = (reported_class if reported_class is not None
                else comfort.classify(model.predict(comfort.baseline_pmv(t, rh, clothing))))
        fix = fix_for(clothing, pcls) if known else None
        fix_ok = (fix is not None and comfort.classify(
            model.predict(comfort.baseline_pmv(t, rh, FIXES[fix]["to"]))) == OK)
        blocked = fix is not None and self.is_blocked(fix, mode, now)
        out = {
            "offer": None, "reason": None, "personal_class": pcls, "fix": fix,
            "fix_feasible": fix_ok and not blocked,
            "energy_role": energy_role(mode, fix) if fix else None,
            "room_signal": room_signal(mode, pcls),
            "band_with_fix": self.band_with_fix(now, rh, clothing, model, mode),
            "unresolved": bool(present and pcls != OK and not (fix_ok and not blocked)),
        }
        if not present:
            out["reason"] = "not_present"
        elif env_stale:
            out["reason"] = "env_stale"
        elif follow_up_pending:
            out["reason"] = "follow_up_pending"
        elif self.active is not None:
            out["reason"] = "suggestion_active"
        elif pcls == OK:
            out["reason"] = "comfortable"
        elif not known:
            out["reason"] = "clothing_uncertain"
        elif fix is None:
            out["reason"] = "no_fix_for_clothing"
        elif not fix_ok:
            out["reason"] = "fix_would_not_help"
        elif blocked:
            out["reason"] = "blocked_not_possible"
        elif self.last_offered_at is not None and now - self.last_offered_at < MIN_GAP_S:
            out["reason"] = "rate_limited"
        else:
            out["reason"] = "offer"
            out["offer"] = {"fix": fix, "mode": mode, "label": FIXES[fix]["label"],
                            "energy_role": out["energy_role"], "clothing_before": clothing}
        return out

    def band_with_fix(self, now, rh, clothing, model, mode) -> list[float] | None:
        fix = ENERGY_FIX.get(mode)
        if fix is None or FIXES[fix]["from"] != clothing or self.is_blocked(fix, mode, now):
            return None
        return comfort.comfort_band(rh, FIXES[fix]["to"], model.offset)

    # ---- show / respond ----
    def offer(self, now: float, offer: dict) -> list[dict]:
        """Put an offer from evaluate() on screen. Returns sketch messages to send."""
        self.active = {**offer, "offered_at": now}
        self.last_offered_at = now
        self.log.append({"event": "offered", "at": now, **offer})
        return [{"face": FIXES[offer["fix"]]["face"]}, {"beep": "chime"}]

    def respond(self, now: float, response: str) -> dict:
        """Record the person's answer to the active suggestion. Returns the log record."""
        if self.active is None:
            raise RuntimeError("no active suggestion")
        if response not in (DO_IT, NOT_NOW, NOT_POSSIBLE, NO_RESPONSE):
            raise ValueError(f"unknown response {response!r}")
        a, self.active = self.active, None
        rec = {"event": "response", "at": now, "response": response, "fix": a["fix"],
               "mode": a["mode"], "energy_role": a["energy_role"],
               "offered_at": a["offered_at"], "follow_up": response == DO_IT}
        if response == NOT_POSSIBLE:
            self.blocked[f"{a['fix']}|{a['mode']}"] = now + NOT_POSSIBLE_HOLD_S
        self.log.append(rec)
        return rec

    def expire(self, now: float) -> dict | None:
        if self.active and now - self.active["offered_at"] > RESPONSE_TIMEOUT_S:
            return self.respond(now, NO_RESPONSE)
        return None

    # ---- persistence (stored on the device) ----
    def to_dict(self) -> dict:
        return {"last_offered_at": self.last_offered_at, "blocked": dict(self.blocked),
                "log": list(self.log[-500:])}

    @classmethod
    def from_dict(cls, d: dict) -> "SuggestionEngine":
        e = cls()
        e.last_offered_at = d.get("last_offered_at")
        e.blocked = dict(d.get("blocked", {}))
        e.log = list(d.get("log", []))
        return e


class ResponsePicker:
    """Knob interaction while a suggestion is on screen (kickoff agreement).

    The sketch starts each interaction at 0 (LATER). A press only answers after a turn,
    or as a second press after a preview: one accidental bump never answers anything.
    """

    def __init__(self):
        self.pos, self.turned, self.previewed = 0, False, False

    def on_turn(self, pos: int) -> list[dict]:
        self.pos, self.turned = pos, True
        return [{"face": "text", "text": TEXT_FOR_POS[pos]}]

    def on_press(self) -> tuple[str | None, list[dict]]:
        if not self.turned and not self.previewed:
            self.previewed = True
            return None, [{"face": "text", "text": TEXT_FOR_POS[0]}]
        answer = RESPONSE_FOR_POS[self.pos]
        self.pos = 0                                  # the sketch resets silently too
        return answer, [{"face": "check"}, {"beep": "chirp"}]


# ======================================================================================
# T2.2: follow-up and fix experience (spec C7)
# ======================================================================================
FOLLOW_UP_WAIT_S = 5 * 60          # "a few minutes"
DEMO_WAIT_S = 30                   # demo only: shown as ACCELERATED
FEEDBACK_TIMEOUT_S = 5 * 60        # no answer -> unknown, no update

# What the camera/dashboard says about whether the accepted action happened.
CONFIRMED_CAMERA = "confirmed_camera"
CONFIRMED_DASHBOARD = "confirmed_dashboard"    # manual clothing: the person confirmed it
NOT_VISIBLE = "not_visible"                    # clothing unknown: rely on the "Do it"
CONTRADICTED = "contradicted"                  # camera still sees the old clothing


class FixExperience:
    """Beta(1, 1) per fix for one person: OK after the action = helped, else didn't."""

    def __init__(self, counts: dict | None = None):
        self.counts = {k: list(v) for k, v in (counts or {}).items()}   # fix -> [helped, didnt]

    def update(self, fix: str, helped: bool) -> None:
        c = self.counts.setdefault(fix, [0, 0])
        c[0 if helped else 1] += 1

    def estimate(self, fix: str) -> dict:
        s, f = self.counts.get(fix, [0, 0])
        a, b = 1 + s, 1 + f
        mean = a / (a + b)
        sd = (a * b / ((a + b) ** 2 * (a + b + 1))) ** 0.5
        level = "high" if sd > 0.15 else "medium" if sd > 0.08 else "lower"
        return {"fix": fix, "helped": s, "didnt": f, "n": s + f, "mean": round(mean, 3),
                "sd": round(sd, 3), "uncertainty": level, "prior": "Beta(1, 1)"}

    def describe(self, fix: str, who: str) -> str:
        e = self.estimate(fix)
        what = {"add_layer": "Adding a layer", "remove_layer": "Removing a layer"}.get(fix, fix)
        if e["n"] == 0:
            return f"{what}, for {who}: no follow-ups yet"
        return (f"{what}, for {who}: {e['helped']} helped, {e['didnt']} didn't "
                f"→ about {round(e['mean'] * 100)}%, {e['uncertainty']} uncertainty")

    def to_dict(self) -> dict:
        return {k: list(v) for k, v in self.counts.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "FixExperience":
        return cls(d)


class FeedbackPicker:
    """Knob while asking 'how do you feel now?': -1 cold, 0 OK, +1 warm. Bump-safe."""

    def __init__(self):
        self.pos, self.turned, self.previewed = 0, False, False

    def on_turn(self, pos: int) -> list[dict]:
        self.pos, self.turned = pos, True
        return [{"face": "feedback", "pos": pos}]

    def on_press(self) -> tuple[int | None, list[dict]]:
        if not self.turned and not self.previewed:
            self.previewed = True
            return None, [{"face": "feedback", "pos": 0}]
        vote, self.pos = self.pos, 0
        return vote, [{"face": "check"}, {"beep": "chirp"}]


class FollowUp:
    """One follow-up after a "Do it". States: waiting -> asking -> done.

        fu = FollowUp(response_record, clothing_before, now, accelerated=True)
        msgs = fu.tick(now, clothing, clothing_source)     # every loop; asks when due
        fu.picker.on_turn / on_press                        # while state == "asking"
        outcome = fu.complete(now, vote, t, rh, clothing, model, experience)
    """

    def __init__(self, response: dict, clothing_before: str, now: float, accelerated: bool = False):
        if not response.get("follow_up"):
            raise ValueError("follow-up only after 'do_it'")
        self.fix = response["fix"]
        self.mode = response["mode"]
        self.clothing_before = clothing_before
        self.started_at = now
        self.accelerated = accelerated
        self.wait_s = DEMO_WAIT_S if accelerated else FOLLOW_UP_WAIT_S
        self.state = "waiting"
        self.action_check: str | None = None
        self.asked_at: float | None = None
        self.picker = FeedbackPicker()
        self.outcome: dict | None = None

    @property
    def labels(self) -> list[str]:
        return ["ACCELERATED"] if self.accelerated else []

    def due_in(self, now: float) -> float:
        return max(0.0, self.started_at + self.wait_s - now)

    def check_action(self, clothing: str, source: str) -> str:
        if clothing == FIXES[self.fix]["to"]:
            return CONFIRMED_DASHBOARD if source == "manual" else CONFIRMED_CAMERA
        if clothing == FIXES[self.fix]["from"] and source == "camera":
            return CONTRADICTED
        return NOT_VISIBLE      # unknown clothing, or a manual setting not updated yet

    def tick(self, now: float, clothing: str, source: str) -> list[dict]:
        """Advance the follow-up. Returns sketch messages (the question) when it starts asking."""
        if self.state == "waiting" and now >= self.started_at + self.wait_s:
            self.action_check = self.check_action(clothing, source)
            self.state, self.asked_at = "asking", now
            return [{"face": "feedback", "pos": 0}, {"beep": "chime"}]
        if self.state == "asking" and now - self.asked_at > FEEDBACK_TIMEOUT_S:
            self._finish(now, {"result": "unknown", "vote": None,
                               "note": "no follow-up response: unknown, not failure"})
        return []

    def complete(self, now: float, vote: int, t: float, rh: float, clothing: str,
                 model: comfort.PersonalModel, experience: FixExperience) -> dict:
        """Apply the follow-up vote: personal offset always, fix experience if counted."""
        if self.state != "asking":
            raise RuntimeError(f"cannot complete in state {self.state}")
        comfort_record = model.observe(vote, comfort.baseline_pmv(t, rh, clothing))
        helped = vote == comfort.OK
        counted = self.action_check != CONTRADICTED
        if counted:
            experience.update(self.fix, helped)
        return self._finish(now, {
            "result": ("helped" if helped else "didnt_help") if counted else "not_counted",
            "vote": vote, "comfort_record": comfort_record,
            "experience": experience.estimate(self.fix),
            "note": ("camera saw the old clothing: comfort vote used, fix experience not updated"
                     if not counted else "association only: neither camera nor vote proves causation"),
        })

    def _finish(self, now: float, extra: dict) -> dict:
        self.state = "done"
        self.outcome = {"event": "follow_up", "at": now, "fix": self.fix, "mode": self.mode,
                        "started_at": self.started_at, "action_check": self.action_check,
                        "labels": self.labels, **extra}
        return self.outcome


# ---- Self-test -----------------------------------------------------------------------
def _selftest():
    import contracts
    M = 60
    m0 = comfort.PersonalModel()
    e = SuggestionEngine()

    # 1. Heating, no layer, 21.5 degC: cold -> add a layer replaces a heat request.
    d = e.evaluate(0, 21.5, 40, "none", m0, "heating")
    assert d["reason"] == "offer" and d["fix"] == "add_layer", d
    assert d["energy_role"] == "replaces_heat_request" and d["fix_feasible"] and not d["unresolved"]
    assert d["band_with_fix"] and d["band_with_fix"][0] < comfort.comfort_band(40, "none")[0]
    msgs = e.offer(0, d["offer"])
    assert msgs == [{"face": "suggest_layer_on"}, {"beep": "chime"}]
    assert e.evaluate(10, 21.5, 40, "none", m0, "heating")["reason"] == "suggestion_active"

    # 2. Not now: no penalty, but the 15-min gap holds.
    assert e.respond(30, NOT_NOW)["follow_up"] is False
    assert e.evaluate(5 * M, 21.5, 40, "none", m0, "heating")["reason"] == "rate_limited"
    d = e.evaluate(15 * M, 21.5, 40, "none", m0, "heating")
    assert d["reason"] == "offer"

    # 3. Not possible: blocked 4 h in this mode, band_with_fix omitted, discomfort unresolved.
    e.offer(15 * M, d["offer"])
    e.respond(16 * M, NOT_POSSIBLE)
    d = e.evaluate(40 * M, 21.5, 40, "none", m0, "heating")
    assert d["reason"] == "blocked_not_possible" and d["unresolved"] and d["band_with_fix"] is None
    assert e.evaluate(40 * M, 21.5, 40, "none", m0, "unknown")["reason"] == "offer"   # other context
    assert e.evaluate(16 * M + NOT_POSSIBLE_HOLD_S + 1, 21.5, 40, "none", m0, "heating")["reason"] == "offer"

    # 4. Do it -> follow-up flag for T2.2.
    e2 = SuggestionEngine()
    e2.offer(0, e2.evaluate(0, 21.5, 40, "none", m0, "heating")["offer"])
    assert e2.respond(20, DO_IT)["follow_up"] is True
    assert e2.evaluate(30, 21.5, 40, "none", m0, "heating", follow_up_pending=True)["reason"] == "follow_up_pending"

    # 5. Warm with a layer in heating: removing it is comfort only; the room may be overheated.
    d = SuggestionEngine().evaluate(0, 26.0, 40, "outer", m0, "heating")
    assert d["fix"] == "remove_layer" and d["energy_role"] == "comfort_only", d
    assert d["room_signal"] == "room_may_be_overheated" and d["reason"] == "offer"
    assert d["band_with_fix"] is None                    # heating fix is add_layer: n/a when wearing outer
    # Cooling mirrors it.
    d = SuggestionEngine().evaluate(0, 26.0, 40, "outer", m0, "cooling")
    assert d["energy_role"] == "replaces_cooling_request" and d["room_signal"] is None
    assert d["band_with_fix"] and d["band_with_fix"][1] > comfort.comfort_band(40, "outer")[1]
    d = SuggestionEngine().evaluate(0, 21.5, 40, "none", m0, "cooling")
    assert d["energy_role"] == "comfort_only" and d["room_signal"] == "room_may_be_overcooled"
    assert SuggestionEngine().evaluate(0, 21.5, 40, "none", m0, "unknown")["energy_role"] == "comfort_only"

    # 6. Reasons for no offer; unresolved stays visible.
    s = SuggestionEngine()
    d = s.evaluate(0, 20.0, 40, "uncertain", m0, "heating")      # 0.8 clo assumed -> cold at 20
    assert d["reason"] == "clothing_uncertain" and d["unresolved"] and d["band_with_fix"] is None
    d = s.evaluate(0, 17.0, 40, "outer", m0, "heating")
    assert d["reason"] == "no_fix_for_clothing" and d["unresolved"]
    d = s.evaluate(0, 17.0, 40, "none", m0, "heating")
    assert d["reason"] == "fix_would_not_help" and d["unresolved"] and not d["fix_feasible"]
    d = s.evaluate(0, 23.5, 40, "none", m0, "heating")
    assert d["reason"] == "comfortable" and not d["unresolved"] and d["band_with_fix"]
    d = s.evaluate(0, 21.5, 40, "none", m0, "heating", present=False)
    assert d["reason"] == "not_present" and not d["unresolved"]
    assert s.evaluate(0, 21.5, 40, "none", m0, "heating", env_stale=True)["reason"] == "env_stale"
    # Personal offset matters: someone who runs warm is fine without a layer.
    warm_person = comfort.PersonalModel(offset=0.5)
    assert s.evaluate(0, 21.5, 40, "none", warm_person, "heating")["reason"] == "comfortable"

    # 7. No answer -> no_response (unknown, no penalty).
    s.offer(100, s.evaluate(100, 21.5, 40, "none", m0, "heating")["offer"])
    s.evaluate(100 + RESPONSE_TIMEOUT_S + 1, 21.5, 40, "none", m0, "heating")
    assert s.log[-1]["response"] == NO_RESPONSE and s.active is None and not s.blocked

    # 8. Knob picker: bump-safe.
    p = ResponsePicker()
    ans, faces = p.on_press()
    assert ans is None and faces == [{"face": "text", "text": "LATER"}]
    ans, _ = p.on_press()
    assert ans == NOT_NOW
    p = ResponsePicker()
    p.on_turn(1)
    ans, faces = p.on_press()
    assert ans == DO_IT and faces == [{"face": "check"}, {"beep": "chirp"}]
    p = ResponsePicker()
    p.on_turn(-1)
    assert p.on_press()[0] == NOT_POSSIBLE

    # 9. Every sketch message passes the contract; persistence round-trips.
    for m in msgs + faces + ResponsePicker().on_turn(-1) + ResponsePicker().on_turn(0):
        contracts.check_to_sketch(m)
    r = SuggestionEngine.from_dict(e.to_dict())
    assert r.blocked == e.blocked and r.last_offered_at == e.last_offered_at and len(r.log) == len(e.log)
    print("suggest OK: offers, 3 responses, 15-min gap, 4 h not-possible hold, mode roles, "
          "unresolved, band_with_fix, knob picker")


def _selftest_followup():
    import contracts
    m0 = comfort.PersonalModel

    def do_it_response():
        e = SuggestionEngine()
        e.offer(0, e.evaluate(0, 21.5, 40, "none", m0(), "heating")["offer"])
        return e.respond(10, DO_IT)

    # Spec wording example: 4 helped, 1 didn't -> about 71%, high uncertainty.
    x = FixExperience({"add_layer": [4, 1]})
    assert x.describe("add_layer", "TA") == "Adding a layer, for TA: 4 helped, 1 didn't → about 71%, high uncertainty"
    assert FixExperience().describe("add_layer", "TA").endswith("no follow-ups yet")
    assert FixExperience({"add_layer": [30, 5]}).estimate("add_layer")["uncertainty"] == "lower"

    # Only after "Do it".
    e = SuggestionEngine()
    e.offer(0, e.evaluate(0, 21.5, 40, "none", m0(), "heating")["offer"])
    try:
        FollowUp(e.respond(5, NOT_POSSIBLE), "none", 5)
        raise AssertionError("follow-up allowed after not_possible")
    except ValueError:
        pass

    # Happy path (demo): accelerated wait, camera confirms, OK -> helped; offset logged.
    model, exp = m0(), FixExperience()
    fu = FollowUp(do_it_response(), "none", 10, accelerated=True)
    assert fu.labels == ["ACCELERATED"] and fu.tick(20, "none", "camera") == []   # still waiting
    ask = fu.tick(10 + DEMO_WAIT_S, "outer", "camera")
    assert ask == [{"face": "feedback", "pos": 0}, {"beep": "chime"}] and fu.state == "asking"
    assert fu.action_check == CONFIRMED_CAMERA
    assert fu.picker.on_press()[0] is None                       # bump: preview only
    fu.picker.on_turn(0)
    vote, msgs = fu.picker.on_press()
    out = fu.complete(50, vote, 21.5, 40, "outer", model, exp)
    assert out["result"] == "helped" and exp.counts == {"add_layer": [1, 0]}
    assert out["comfort_record"]["vote"] == 0 and model.n == 1  # offset updated + prospective record
    for m in ask + msgs + fu.picker.on_turn(-1):
        contracts.check_to_sketch(m)

    # Still cold after the layer -> didn't help.
    exp2 = FixExperience()
    fu = FollowUp(do_it_response(), "none", 0)
    assert fu.wait_s == FOLLOW_UP_WAIT_S and fu.labels == []
    fu.tick(FOLLOW_UP_WAIT_S, "outer", "manual")
    assert fu.action_check == CONFIRMED_DASHBOARD
    assert fu.complete(FOLLOW_UP_WAIT_S + 5, -1, 19.0, 40, "outer", m0(), exp2)["result"] == "didnt_help"
    assert exp2.counts == {"add_layer": [0, 1]}

    # Camera still sees no layer: comfort vote used, experience NOT updated.
    exp3, model3 = FixExperience(), m0()
    fu = FollowUp(do_it_response(), "none", 0, accelerated=True)
    fu.tick(DEMO_WAIT_S, "none", "camera")
    out = fu.complete(DEMO_WAIT_S + 5, 0, 21.5, 40, "none", model3, exp3)
    assert fu.action_check == CONTRADICTED and out["result"] == "not_counted"
    assert exp3.counts == {} and model3.n == 1

    # Clothing not visible (camera off / uncertain): the accepted "Do it" + response counts.
    exp4 = FixExperience()
    fu = FollowUp(do_it_response(), "none", 0, accelerated=True)
    fu.tick(DEMO_WAIT_S, "uncertain", "camera")
    assert fu.action_check == NOT_VISIBLE
    assert fu.complete(DEMO_WAIT_S + 5, 0, 21.5, 40, "uncertain", m0(), exp4)["result"] == "helped"

    # No answer -> unknown, nothing updated.
    exp5, model5 = FixExperience(), m0()
    fu = FollowUp(do_it_response(), "none", 0, accelerated=True)
    fu.tick(DEMO_WAIT_S, "outer", "camera")
    fu.tick(DEMO_WAIT_S + FEEDBACK_TIMEOUT_S + 1, "outer", "camera")
    assert fu.state == "done" and fu.outcome["result"] == "unknown" and fu.outcome["vote"] is None
    assert exp5.counts == {} and model5.n == 0
    try:
        fu.complete(9999, 0, 21.5, 40, "outer", model5, exp5)
        raise AssertionError("completed twice")
    except RuntimeError:
        pass

    assert FixExperience.from_dict(exp.to_dict()).counts == exp.counts
    print("follow-up OK: Do-it only, accelerated label, camera/dashboard/contradicted/not-visible checks, "
          "helped/didn't/unknown, Beta wording")


if __name__ == "__main__":
    _selftest()
    _selftest_followup()
