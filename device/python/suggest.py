"""Suggestion engine: optional, mode-aware free fixes.  Owner: Tuan Anh (T2.1; T2.2 next).

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
                 follow_up_pending: bool = False) -> dict:
        """Decide whether to offer a fix now. Pure: nothing changes until offer()."""
        self.expire(now)
        known = clothing in ("outer", "none")
        pcls = comfort.classify(model.predict(comfort.baseline_pmv(t, rh, clothing)))
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


if __name__ == "__main__":
    _selftest()
