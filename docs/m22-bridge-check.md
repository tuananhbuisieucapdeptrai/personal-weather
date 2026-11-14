# M2.2 Bridge adapter acceptance

M2.2 is complete. `device/python/bridge_io.py` implements the frozen `start(on_message)` and `send(msg)` interface in `docs/interfaces.md` section 0.2.1. It translates `env`, `knob_turn`, and `knob_press` notifications into checked dictionaries, and sends face, feedback, text and beep commands with nonblocking `Bridge.notify`. Extra handlers are diagnostic only. Malformed transport values are logged and dropped without raising out of a Bridge callback.

## Evidence, 2026-11-14

- The UNO Q face-check v4 run detected Thermo, Knob and Buzzer, delivered 92 environment messages and 4 knob events while all 18 face/sound commands were acknowledged; zero invalid messages and no stale-reading warnings.
- The earlier kickoff board check verified the full knob calibration and Bridge round trip. M2.1 physical display and sound were confirmed separately by Minh.
- `python -m unittest discover -s tools/tests -p test_bridge_io.py -v`: 2 tests passed, covering both directions, malformed incoming values and invalid outgoing commands.
- `python device/python/contracts.py`: 26 valid and 13 invalid examples passed.

The face-check app is a diagnostic entry point. Production `main.py` uses the same adapter interface; end-to-end state-machine integration belongs to M3.2/T3.1. Local changes are not yet committed or pushed.
