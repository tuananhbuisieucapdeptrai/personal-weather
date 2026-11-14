"""Linux <-> sketch over the App Lab Bridge.  Owner: Minh (M2.2).

Public API (frozen, see docs/interfaces.md "Python module interfaces"):

    start(on_message)  register Bridge handlers; on_message(dict) gets every
                       sketch -> Linux message as a contract dict
                       ({"t", "rh"} / {"knob": "turn", "pos"} / {"knob": "press"}).
                       Called from the Bridge thread: the callback must only enqueue.
    send(msg)          send one Linux -> sketch contract dict ({"face": ...} / {"beep": ...}).

main.py never imports the Bridge itself; tools/mocks.py implements the same two functions.

Bridge mapping: docs/interfaces.md 0.2.1. Everything uses notify, so send() never blocks.
The `arduino` package only exists on the board, so it is imported inside the functions.
"""
from __future__ import annotations

import sys

import contracts


def _log(*args):
    print("[bridge_io]", *args, file=sys.stderr, flush=True)


dropped = 0  # invalid sketch messages seen (board_check.py reports this)


def start(on_message, extra_handlers=None):
    """Register sketch -> Linux handlers.

    extra_handlers: optional {bridge_name: fn} for debug-only messages
    (knob_raw, face_ack, hw_status) used by board_check.py. Not part of the contract.
    """
    from arduino.app_utils import Bridge

    def deliver(msg):
        # Runs on the Bridge thread: validate, hand over, never raise, never Bridge.call.
        try:
            on_message(contracts.check_from_sketch(msg))
        except contracts.ContractError as e:
            global dropped
            dropped += 1
            _log("dropped invalid message:", e)
        except Exception as e:  # a crash here would kill the Bridge thread
            _log("on_message failed:", repr(e))

    def on_env(t, rh):
        deliver({"t": round(float(t), 1), "rh": round(float(rh), 1)})

    def on_knob_turn(pos):
        deliver({"knob": "turn", "pos": int(pos)})

    def on_knob_press(*_ignored):  # tolerate a dummy arg if zero-arg notify is unsupported
        deliver({"knob": "press"})

    Bridge.provide("env", on_env)
    Bridge.provide("knob_turn", on_knob_turn)
    Bridge.provide("knob_press", on_knob_press)
    for name, fn in (extra_handlers or {}).items():
        Bridge.provide(name, fn)


def send(msg):
    """Send one Linux -> sketch contract dict. Raises ContractError on a bad message."""
    from arduino.app_utils import Bridge

    contracts.check_to_sketch(msg)
    if "beep" in msg:
        Bridge.notify("beep", msg["beep"])
    elif msg["face"] == "feedback":
        Bridge.notify("face_feedback", msg["pos"])
    elif msg["face"] == "text":
        Bridge.notify("face_text", msg["text"])
    else:
        Bridge.notify("face", msg["face"])
