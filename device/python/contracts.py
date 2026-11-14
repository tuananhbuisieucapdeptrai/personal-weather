"""Message contracts from docs/interfaces.md section 0.2, as executable checks.

Shared by Tuan Anh and Minh. Stdlib only, so it runs on the laptop and on the UNO Q.
Mocks, tests and (cheaply) the real code call these to catch drift early.

Rule: a contract changes only when BOTH of you agree, and docs/interfaces.md and
this file change in the same commit.

Run `python3 device/python/contracts.py` to self-test against the documented examples.
"""
from __future__ import annotations

import re


class ContractError(ValueError):
    pass


# ---- Shared vocabulary ------------------------------------------------------
KNOB_POSITIONS = (-1, 0, 1)        # feedback: cold / OK / warm; response: NO / LATER / DO
FACES = ("smile", "sun", "snow", "suggest_layer_on", "suggest_layer_off",
         "feedback", "check", "text", "eye_off", "off")
BEEPS = ("chirp", "chime", "low")  # knob "click" is local to the sketch, no message
RESPONSE_TEXT = {1: "DO", 0: "LATER", -1: "NO"}
TEXT_RE = re.compile(r"^[A-Z0-9 ]{1,8}$")

CLOTHING = ("outer", "none", "uncertain")   # spec: outer_layer / no_outer_layer / uncertain
CAMERA = ("on", "off", "shutter")
MODES = ("heating", "cooling", "unknown")
PROFILES = ("tuananh", "minh")
CLOTHING_OVERRIDE = ("outer", "none", "auto")  # dashboard fallback if the vision gate fails

PID_RE = re.compile(r"^p-[0-9a-f]{4}$")
SUMMARY_KEYS = {"pid", "present", "mode", "band_now", "state", "unresolved"}
SUMMARY_OPTIONAL = {"band_with_fix"}


# ---- Helpers ----------------------------------------------------------------
def _fail(msg, why):
    raise ContractError(f"{why}: {msg!r}")


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _keys(msg, required, optional=frozenset()):
    if not isinstance(msg, dict):
        _fail(msg, "not a dict")
    missing = set(required) - msg.keys()
    extra = msg.keys() - set(required) - set(optional)
    if missing:
        _fail(msg, f"missing keys {sorted(missing)}")
    if extra:
        _fail(msg, f"unknown keys {sorted(extra)}")


def _band(msg, band, name):
    if band is None:
        return  # no temperature in the search range is OK for this person
    if not (isinstance(band, list) and len(band) == 2 and all(_is_num(v) for v in band)):
        _fail(msg, f"{name} must be [low, high] in degC or null")
    if band[0] > band[1]:
        _fail(msg, f"{name} low > high")


# ---- Sketch -> Linux ---------------------------------------------------------
def check_from_sketch(msg):
    """{"t": 23.4, "rh": 41.2} | {"knob": "turn", "pos": -1} | {"knob": "press"}"""
    if isinstance(msg, dict) and "knob" in msg:
        if msg["knob"] == "turn":
            _keys(msg, {"knob", "pos"})
            if not _is_int(msg["pos"]) or msg["pos"] not in KNOB_POSITIONS:
                _fail(msg, "pos must be -1, 0 or 1")
        elif msg["knob"] == "press":
            _keys(msg, {"knob"})
        else:
            _fail(msg, "knob must be 'turn' or 'press'")
        return msg
    _keys(msg, {"t", "rh"})
    if not (_is_num(msg["t"]) and -20 <= msg["t"] <= 60):
        _fail(msg, "t must be a number in degC (-20..60)")
    if not (_is_num(msg["rh"]) and 0 <= msg["rh"] <= 100):
        _fail(msg, "rh must be a number in %RH (0..100)")
    return msg


# ---- Linux -> Sketch ---------------------------------------------------------
def check_to_sketch(msg):
    """{"face": "smile"} | {"face": "feedback", "pos": -1} | {"face": "text", "text": "DO"} | {"beep": "chirp"}"""
    if isinstance(msg, dict) and "beep" in msg:
        _keys(msg, {"beep"})
        if msg["beep"] not in BEEPS:
            _fail(msg, f"beep must be one of {BEEPS}")
        return msg
    if not isinstance(msg, dict) or msg.get("face") not in FACES:
        _fail(msg, f"face must be one of {FACES}")
    face = msg["face"]
    if face == "feedback":
        _keys(msg, {"face", "pos"})
        if not _is_int(msg["pos"]) or msg["pos"] not in KNOB_POSITIONS:
            _fail(msg, "feedback pos must be -1, 0 or 1")
    elif face == "text":
        _keys(msg, {"face", "text"})
        if not (isinstance(msg["text"], str) and TEXT_RE.match(msg["text"])):
            _fail(msg, "text must be 1-8 chars of A-Z, 0-9, space")
    else:
        _keys(msg, {"face"})
    return msg


# ---- vision.py -> main.py ----------------------------------------------------
def check_vision(msg):
    """{"present": true, "clothing": "outer", "conf": 0.86, "camera": "on"}"""
    _keys(msg, {"present", "clothing", "conf", "camera"})
    if msg["camera"] not in CAMERA:
        _fail(msg, f"camera must be one of {CAMERA}")
    if msg["clothing"] not in CLOTHING:
        _fail(msg, f"clothing must be one of {CLOTHING}")
    conf = msg["conf"]
    if conf is not None and not (_is_num(conf) and 0 <= conf <= 1):
        _fail(msg, "conf must be in [0, 1] or null")
    if msg["camera"] != "on":
        # Camera not running: vision knows nothing.
        if msg["present"] is not None or msg["clothing"] != "uncertain" or conf is not None:
            _fail(msg, "camera off/shutter => present null, clothing 'uncertain', conf null")
        return msg
    if not isinstance(msg["present"], bool):
        _fail(msg, "present must be true/false while camera is on")
    if not msg["present"] and msg["clothing"] != "uncertain":
        _fail(msg, "nobody present => clothing 'uncertain'")
    if msg["clothing"] in ("outer", "none") and conf is None:
        _fail(msg, "a clothing decision needs a conf value")
    return msg


# ---- Dashboard -> device API ---------------------------------------------------
def check_control(msg):
    """POST /control body: any non-empty subset of profile, camera, mode, reset_pid, clothing."""
    allowed = {"profile", "camera", "mode", "reset_pid", "clothing"}
    _keys(msg, set(), allowed)
    if not msg:
        _fail(msg, "empty control body")
    if "profile" in msg and msg["profile"] not in PROFILES:
        _fail(msg, f"profile must be one of {PROFILES}")
    if "camera" in msg and msg["camera"] not in ("on", "off"):
        _fail(msg, "camera must be 'on' or 'off'")
    if "mode" in msg and msg["mode"] not in MODES:
        _fail(msg, f"mode must be one of {MODES}")
    if "reset_pid" in msg and msg["reset_pid"] is not True:
        _fail(msg, "reset_pid must be true (omit it otherwise)")
    if "clothing" in msg and msg["clothing"] not in CLOTHING_OVERRIDE:
        _fail(msg, f"clothing must be one of {CLOTHING_OVERRIDE}")
    return msg


# ---- Device -> hub (spec C8) -------------------------------------------------
def check_summary(msg):
    """{"pid": "p-7f3a", "present": true, "mode": "heating", "band_now": [21.0, 22.5],
        "band_with_fix": [19.5, 22.5], "state": -1, "unresolved": false}"""
    _keys(msg, SUMMARY_KEYS, SUMMARY_OPTIONAL)
    if not (isinstance(msg["pid"], str) and PID_RE.match(msg["pid"])):
        _fail(msg, "pid must look like 'p-7f3a'")
    if not isinstance(msg["present"], bool):
        _fail(msg, "present must be true/false")
    if msg["mode"] not in MODES:
        _fail(msg, f"mode must be one of {MODES}")
    _band(msg, msg["band_now"], "band_now")
    if "band_with_fix" in msg:
        _band(msg, msg["band_with_fix"], "band_with_fix")
    if not _is_int(msg["state"]) or msg["state"] not in (-1, 0, 1):
        _fail(msg, "state must be -1, 0 or 1")
    if not isinstance(msg["unresolved"], bool):
        _fail(msg, "unresolved must be true/false")
    return msg


# ---- Self-test ---------------------------------------------------------------
def _selftest():
    good = [
        (check_from_sketch, {"t": 23.4, "rh": 41.2}),
        (check_from_sketch, {"knob": "turn", "pos": -1}),
        (check_from_sketch, {"knob": "press"}),
        *[(check_to_sketch, {"face": f}) for f in FACES if f not in ("feedback", "text")],
        (check_to_sketch, {"face": "feedback", "pos": 1}),
        *[(check_to_sketch, {"face": "text", "text": t}) for t in RESPONSE_TEXT.values()],
        *[(check_to_sketch, {"beep": b}) for b in BEEPS],
        (check_vision, {"present": True, "clothing": "outer", "conf": 0.86, "camera": "on"}),
        (check_vision, {"present": True, "clothing": "uncertain", "conf": 0.41, "camera": "on"}),
        (check_vision, {"present": False, "clothing": "uncertain", "conf": None, "camera": "on"}),
        (check_vision, {"present": None, "clothing": "uncertain", "conf": None, "camera": "shutter"}),
        (check_control, {"profile": "minh"}),
        (check_control, {"mode": "heating", "camera": "off", "reset_pid": True, "clothing": "auto"}),
        (check_summary, {"pid": "p-7f3a", "present": True, "mode": "heating",
                         "band_now": [21.0, 22.5], "band_with_fix": [19.5, 22.5],
                         "state": -1, "unresolved": False}),
        (check_summary, {"pid": "p-00b1", "present": False, "mode": "unknown",
                         "band_now": None, "state": 0, "unresolved": True}),
    ]
    bad = [
        (check_from_sketch, {"t": "23.4", "rh": 41.2}),
        (check_from_sketch, {"knob": "turn", "pos": 2}),
        (check_from_sketch, {"knob": "turn", "pos": True}),
        (check_to_sketch, {"face": "frown"}),
        (check_to_sketch, {"face": "text", "text": "do it"}),
        (check_to_sketch, {"beep": "click"}),
        (check_vision, {"present": True, "clothing": "outer_layer", "conf": 0.9, "camera": "on"}),
        (check_vision, {"present": False, "clothing": "outer", "conf": 0.9, "camera": "on"}),
        (check_vision, {"present": True, "clothing": "uncertain", "conf": None, "camera": "off"}),
        (check_control, {}),
        (check_control, {"mode": "auto"}),
        (check_summary, {"pid": "Tuan Anh", "present": True, "mode": "heating",
                         "band_now": [21.0, 22.5], "state": 0, "unresolved": False}),
        (check_summary, {"pid": "p-7f3a", "present": True, "mode": "heating",
                         "band_now": [22.5, 21.0], "state": 0, "unresolved": False}),
    ]
    for fn, msg in good:
        fn(msg)
    for fn, msg in bad:
        try:
            fn(msg)
        except ContractError:
            continue
        raise AssertionError(f"{fn.__name__} accepted bad message {msg!r}")
    print(f"contracts OK: {len(good)} valid examples accepted, {len(bad)} invalid rejected")


if __name__ == "__main__":
    _selftest()
