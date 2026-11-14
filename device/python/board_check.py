"""Kickoff board check: items 1-3 of docs/kickoff-guide.md, run ON the UNO Q.

Checks, with PASS/FAIL printed to the App Lab console:
  A. Modulinos answer (Thermo, Knob, Buzzer)
  B. Bridge sketch -> Linux: env at ~1 Hz with float values (item 1)
  C. Bridge Linux -> sketch: every face/beep message arrives (item 1)
  D. Knob calibration: counts per click and direction (item 2)
  E. Knob behaviour: clamp, reset-after-press, single press on hold, fast spin (item 2)
  F. Click sound: manual check (item 3)

How to run: main.py calls run() while RUN_BOARD_CHECK is True. Click Run in App Lab and
follow the instructions printed in the console. Each knob step gives you 10 seconds.
Needs the sketch built with DEBUG_KNOB_RAW 1 and DEBUG_FACE_ACK 1.
"""
from __future__ import annotations

import queue
import threading
import time

import bridge_io
import contracts

STEP_SECONDS = 10

_q: queue.Queue = queue.Queue()
_lock = threading.Lock()
_dbg = {"ack": None, "hw": None, "raw": []}
_results: list[tuple[str, str, str]] = []


# ---- Debug-only Bridge handlers (not part of the contract) --------------------
def _on_ack(n):
    with _lock:
        _dbg["ack"] = int(n)


def _on_hw(thermo, knob, buzzer):
    with _lock:
        _dbg["hw"] = (bool(thermo), bool(knob), bool(buzzer))


def _on_raw(prev, new):
    with _lock:
        _dbg["raw"].append((int(prev), int(new)))


# ---- Helpers -------------------------------------------------------------------
def say(*args):
    print(*args, flush=True)


def record(name, status, detail=""):
    _results.append((name, status, detail))
    say(f"  [{status}] {name}" + (f": {detail}" if detail else ""))


def collect(seconds):
    """All contract messages received during the next `seconds`."""
    out, end = [], time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        try:
            out.append(_q.get(timeout=left))
        except queue.Empty:
            break
    return out


def flush():
    while not _q.empty():
        _q.get_nowait()
    with _lock:
        _dbg["raw"].clear()


def knob_step(instruction, seconds=STEP_SECONDS):
    flush()
    say(f"\n>>> {instruction}  (you have {seconds} s)")
    msgs = collect(seconds)
    turns = [m["pos"] for m in msgs if m.get("knob") == "turn"]
    presses = sum(1 for m in msgs if m.get("knob") == "press")
    say(f"    got turns={turns} presses={presses}")
    return turns, presses


# ---- Checks --------------------------------------------------------------------
def check_hardware():
    say("\n== A. Modulinos ==")
    time.sleep(2.5)
    with _lock:
        hw = _dbg["hw"]
    if hw is None:
        record("hw_status received", "FAIL", "no hw_status from sketch: is the sketch uploaded and running?")
        return False
    for name, ok in zip(("Thermo", "Knob", "Buzzer"), hw):
        record(f"{name} found", "PASS" if ok else "FAIL",
               "" if ok else "check the Qwiic cable; or try Modulino.begin(Wire1) in setup()")
    return all(hw)


def check_env():
    say("\n== B. Sketch -> Linux: env ==")
    flush()
    env = [m for m in collect(10) if "t" in m]
    record("env rate ~1 Hz", "PASS" if 8 <= len(env) <= 12 else "FAIL", f"{len(env)} messages in 10 s")
    if env:
        last = env[-1]
        record("env plausible", "PASS" if 5 <= last["t"] <= 40 and 5 <= last["rh"] <= 95 else "WARN",
               f"t={last['t']} degC, rh={last['rh']} %")
        all_whole = all(m["t"] == int(m["t"]) and m["rh"] == int(m["rh"]) for m in env)
        record("env has decimals (floats arrive as floats)", "WARN" if all_whole else "PASS",
               "every value is a whole number: check the float args in Bridge.notify" if all_whole else "")


def check_to_sketch():
    say("\n== C. Linux -> sketch: faces and beeps (you will hear 3 beeps) ==")
    bridge_io.send({"face": "smile"})
    time.sleep(1.5)
    with _lock:
        base = _dbg["ack"]
    if base is None:
        record("face_ack received", "FAIL",
               "sketch never acknowledged: Python->sketch notify not arriving (see guide item 1 fallback)")
        return
    msgs = [{"face": f} for f in contracts.FACES if f not in ("feedback", "text")]
    msgs += [{"face": "feedback", "pos": p} for p in contracts.KNOB_POSITIONS]
    msgs += [{"face": "text", "text": t} for t in contracts.RESPONSE_TEXT.values()]
    msgs += [{"beep": b} for b in contracts.BEEPS]
    for m in msgs:
        bridge_io.send(m)
        time.sleep(0.4 if "beep" in m else 0.1)
    time.sleep(2)
    with _lock:
        got = _dbg["ack"] - base
    record("all Linux->sketch messages arrive", "PASS" if got == len(msgs) else "FAIL",
           f"sketch counted {got} of {len(msgs)}")
    bridge_io.send({"face": "smile"})


def check_knob_calibration():
    say("\n== D. Knob calibration ==")
    flush()
    say(f"\n>>> Turn the knob exactly ONE click CLOCKWISE, slowly.  (you have {STEP_SECONDS} s)")
    time.sleep(STEP_SECONDS)
    with _lock:
        raw = list(_dbg["raw"])
    if not raw:
        record("knob raw changes seen", "FAIL", "no knob_raw: is DEBUG_KNOB_RAW 1 in the sketch?")
        return False
    total = sum(new - prev for prev, new in raw)
    if total == 0:
        record("knob calibration", "FAIL", "raw value went back to where it started; try again")
        return False
    counts, direction = abs(total), (1 if total > 0 else -1)
    ok = counts == 1 and direction == 1
    record("knob calibration", "PASS" if ok else "FAIL",
           f"one click = {counts} count(s), clockwise is {'+' if direction > 0 else '-'}")
    if not ok:
        say(f"    -> In sketch.ino set: #define COUNTS_PER_DETENT {counts}"
            f"  and  #define KNOB_DIRECTION {direction}, upload again, rerun this check.")
    return ok


def check_knob_behaviour():
    say("\n== E. Knob behaviour ==")
    knob_step("Press the knob once (this resets it to the middle).")

    turns, presses = knob_step("Turn 3 clicks CLOCKWISE.")
    record("clockwise clamps at +1, one message", "PASS" if turns == [1] and presses == 0 else "FAIL",
           f"expected turns=[1], got {turns}")

    turns, presses = knob_step("Press once.")
    record("press sends one 'press'", "PASS" if presses == 1 and not turns else "FAIL",
           f"presses={presses}, turns={turns}")

    turns, presses = knob_step("Turn 1 click COUNTER-clockwise.")
    record("press reset the position to 0", "PASS" if turns == [-1] else "FAIL",
           "expected turns=[-1]; [0] means the press did not reset" if turns != [-1] else "")

    turns, presses = knob_step("Press and HOLD for 2 seconds, then release.")
    record("holding gives exactly one press", "PASS" if presses == 1 else "FAIL", f"presses={presses}")

    before = bridge_io.dropped
    turns, presses = knob_step("Spin FAST back and forth until the time is up.")
    bad = bridge_io.dropped - before
    record("fast spin: only -1/0/+1, nothing invalid",
           "PASS" if len(turns) >= 2 and bad == 0 else "FAIL", f"{len(turns)} turns, {bad} invalid")


def summary():
    say("\n== F. Click sound (manual) ==")
    say("  [MANUAL] Slow turn = one click per detent? Fast spin = soft rattle, not a continuous tone?")
    say("  [MANUAL] Is the click acceptable in a quiet office? If not, see guide item 3.")
    fails = [r for r in _results if r[1] == "FAIL"]
    say("\n================ BOARD CHECK SUMMARY ================")
    for name, status, _ in _results:
        say(f"  {status:5} {name}")
    say("  RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL(S): fix and rerun")
    say("  If all pass: set DEBUG_KNOB_RAW 0 in sketch.ino and tick items 1-3 in docs/interfaces.md.")
    say("======================================================\n")


def run():
    bridge_io.start(_q.put, extra_handlers={
        "face_ack": _on_ack, "hw_status": _on_hw, "knob_raw": _on_raw})
    say("Personal Weather board check starting. Keep this console visible.")
    hw_ok = check_hardware()
    check_env()
    check_to_sketch()
    if hw_ok and check_knob_calibration():
        check_knob_behaviour()
    else:
        record("knob behaviour", "SKIP", "fix hardware/calibration first")
    summary()
