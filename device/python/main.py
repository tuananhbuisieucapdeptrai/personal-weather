"""Entry point on the UNO Q (App Lab runs this) and on a laptop with mocks.  Owner: Tuan Anh.

    App Lab (board):  RUN_BOARD_CHECK = True  -> kickoff board check (board_check.py)
                      RUN_BOARD_CHECK = False -> the real app (app.py) with bridge_io + vision
    Laptop:           python3 device/python/main.py --mock [--scenario cold] [--speed 1] [--demo]
                      (fake sensors/knob/camera, labelled MOCK INPUT; type commands, see MOCK_HELP)

Everything starts under the __main__ guard: vision uses multiprocessing spawn, which
re-imports this module (Minh's integration note).
Wires: bridge_io / vision / api.ControlState / app.App; API on port 8000 (GET /state,
POST /control); summaries to the hub URL from summary.py (state/hub_url or PW_HUB_URL).
"""
from __future__ import annotations

import os
import sys
import time

# True runs the kickoff hardware check (board_check.py) instead of the app.
RUN_BOARD_CHECK = False

# Demo speed on the board: 30 s follow-up instead of 5 min, shown as "Sped up" (ACCELERATED).
# Turn on:  touch state/demo   (or set PW_DEMO=1)      Turn off: rm state/demo
DEMO_FLAG = "demo"

HERE = os.path.dirname(os.path.abspath(__file__))
TICK_S = 1.0

MOCK_HELP = """commands (then Enter):
  -  0  +       turn the knob to -1 / 0 / +1        p   press the knob
  outer none auto   dashboard clothing override      cam on | cam off | shutter
  heating cooling unknown   operating mode           tuananh | minh   switch profile
  state         print a short state line             q   quit"""


def run_board():
    import threading

    from arduino.app_utils import App as ArduinoApp

    import api
    import app as app_mod
    import bridge_io
    import vision

    def on_camera(on):
        # vision.stop() can take seconds; never block the HTTP handler or the loop on it.
        threading.Thread(target=vision.start if on else vision.stop, daemon=True).start()

    state_dir = os.path.join(HERE, "state")
    demo = os.environ.get("PW_DEMO") == "1" or os.path.exists(os.path.join(state_dir, DEMO_FLAG))
    control = api.ControlState(on_camera=on_camera)
    application = app_mod.App(bridge_io, vision, control, time.time, state_dir, accelerated=demo)
    print(f"Personal Weather starting: labels {application.labels}", flush=True)
    application.start()
    api.serve(control, application.get_state)
    if control.camera == "on":
        on_camera(True)                      # app start = explicit intent to run the camera

    def loop():
        application.tick()
        time.sleep(TICK_S)

    ArduinoApp.run(user_loop=loop)


def run_mock(argv):
    import argparse
    import threading

    sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
    import api
    import app as app_mod
    import mocks

    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="office", choices=sorted(mocks.SCENARIOS))
    ap.add_argument("--speed", type=float, default=1.0, help="simulated seconds per real second")
    ap.add_argument("--demo", action="store_true", help="30 s follow-up (labelled ACCELERATED)")
    ap.add_argument("--clothing", default="uncertain", choices=["outer", "none", "uncertain"],
                    help="what the fake camera sees")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    bridge = mocks.MockBridge(scenario=args.scenario, speed=args.speed)
    vision = mocks.MockVision(clothing=args.clothing, conf=0.9 if args.clothing != "uncertain" else 0.4)
    vision.attach_clock(bridge)
    control = api.ControlState(on_camera=lambda on: vision.start() if on else vision.stop(),
                               state_dir=os.path.join(HERE, "state", "mock"))
    t0 = time.time()
    application = app_mod.App(bridge, vision, control, lambda: t0 + bridge.sim_time,
                              os.path.join(HERE, "state", "mock"), inputs="mock",
                              accelerated=args.demo or args.speed != 1)
    application.start()
    api.serve(control, application.get_state, port=args.port)
    print(f"MOCK INPUT {application.labels}: scenario={args.scenario}; API http://127.0.0.1:{args.port}/state")
    print(MOCK_HELP, flush=True)

    def commands():
        for line in sys.stdin:
            c = line.strip().lower()
            try:
                if c in ("-", "0", "+"):
                    bridge.turn({"-": -1, "0": 0, "+": 1}[c])
                elif c == "p":
                    bridge.press()
                elif c in ("outer", "none", "auto"):
                    control.apply({"clothing": c})
                elif c in ("heating", "cooling", "unknown"):
                    control.apply({"mode": c})
                elif c in ("tuananh", "minh"):
                    control.apply({"profile": c})
                elif c in ("cam on", "cam off"):
                    control.apply({"camera": c.split()[1]})
                elif c == "shutter":
                    vision.close_shutter()
                elif c == "state":
                    s = application.get_state()
                    p = s["people"][s["control"]["profile"]]
                    e = p["estimate"] or {}
                    print(f"t={s['env']['t']} clothing={s['clothing']['value']} face={s['face']} "
                          f"class={e.get('personal_class')} reason={(p['decision'] or {}).get('reason')} "
                          f"interaction={s['interaction']}", flush=True)
                elif c == "q":
                    os._exit(0)
                elif c:
                    print(MOCK_HELP, flush=True)
            except Exception as ex:  # keep the console alive on a bad command
                print("error:", ex, flush=True)

    threading.Thread(target=commands, daemon=True).start()
    last_face = None
    while True:
        application.tick()
        if application.last_face != last_face:
            last_face = application.last_face
            print(f"[face] {last_face}", flush=True)
        time.sleep(TICK_S)


def run_board_check():
    from arduino.app_utils import App as ArduinoApp

    import board_check

    done = []

    def loop():
        if not done:
            done.append(True)
            board_check.run()
        time.sleep(1)

    ArduinoApp.run(user_loop=loop)


if __name__ == "__main__":
    if "--mock" in sys.argv:
        run_mock([a for a in sys.argv[1:] if a != "--mock"])
    elif RUN_BOARD_CHECK:
        run_board_check()
    else:
        run_board()
