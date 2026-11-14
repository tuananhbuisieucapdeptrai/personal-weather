"""Device local API for the dashboard (local only, labelled debug).  Owner: Tuan Anh (T3.2).

    GET  /state     dashboard snapshot (shape owned by main.py, NOT frozen)
    POST /control   any non-empty subset of {"profile", "camera", "mode", "reset_pid", "clothing"}
                    -> 200 + new /state, or 400 {"error": ...} on a contract violation

Port 8000. Stdlib only (no Flask needed on the board). CORS is open because the
dashboard is served by the hub on the laptop (another origin); the API is LAN-only.

Clothing override rules (docs/interfaces.md 0.2.3):
  - "outer"/"none" beat vision; "auto" = vision decides (default)
  - sticks until set back to "auto", also across profile switches
  - dashboard shows "CLOTHING: SET MANUALLY" while active (clothing_source == "manual")

Dev server on the laptop (no board needed):
    python3 device/python/api.py            # then: tools/kickoff/api_smoke.sh 127.0.0.1:8000
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import contracts

DEFAULT_PORT = 8000
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")  # gitignored


def new_pid() -> str:
    return "p-" + secrets.token_hex(2)


class ControlState:
    """Everything the dashboard can change. Thread-safe; main.py reads it every tick.

    on_camera(bool) is called when the camera setting changes (main.py wires it to
    vision.start / vision.stop). "on" also restarts the camera after a shutter stop.
    """

    def __init__(self, on_camera=None, state_dir: str | None = STATE_DIR):
        self._lock = threading.Lock()
        self._on_camera = on_camera
        self._pid_path = os.path.join(state_dir, "pids.json") if state_dir else None
        self.profile = contracts.PROFILES[0]
        self.camera = "on"
        self.mode = "heating"              # spec section 2: default for Finland in November
        self.clothing_override = "auto"
        self.pids = self._load_pids()

    # ---- persistence of pseudonyms (spec C8: persistent, resettable) ----
    def _load_pids(self) -> dict:
        pids = {}
        if self._pid_path and os.path.exists(self._pid_path):
            try:
                with open(self._pid_path) as f:
                    pids = json.load(f)
            except (OSError, ValueError):
                pids = {}
        changed = False
        for p in contracts.PROFILES:
            if not isinstance(pids.get(p), str) or not contracts.PID_RE.match(pids[p]):
                pids[p] = new_pid()
                changed = True
        if changed:
            self._save_pids(pids)
        return {p: pids[p] for p in contracts.PROFILES}

    def _save_pids(self, pids):
        if not self._pid_path:
            return
        os.makedirs(os.path.dirname(self._pid_path), exist_ok=True)
        tmp = self._pid_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(pids, f)
        os.replace(tmp, self._pid_path)

    # ---- the /control body ----
    def apply(self, body: dict) -> None:
        """Validate and apply a /control body. Raises contracts.ContractError if invalid."""
        contracts.check_control(body)
        camera_changed_to = None
        with self._lock:
            if "profile" in body:
                self.profile = body["profile"]
            if "mode" in body:
                self.mode = body["mode"]
            if "clothing" in body:
                self.clothing_override = body["clothing"]
            if "camera" in body:
                camera_changed_to = body["camera"]   # also re-sent "on" -> restart after shutter
                self.camera = body["camera"]
            if body.get("reset_pid"):
                self.pids[self.profile] = new_pid()
                self._save_pids(self.pids)
        if camera_changed_to is not None and self._on_camera:
            self._on_camera(camera_changed_to == "on")   # outside the lock: may be slow

    # ---- what main.py uses ----
    def effective_clothing(self, vision_clothing: str) -> tuple[str, str]:
        """(clothing, source): the dashboard override wins over vision unless 'auto'."""
        with self._lock:
            override = self.clothing_override
        if override != "auto":
            return override, "manual"
        return vision_clothing, "camera"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "profile": self.profile,
                "camera_setting": self.camera,
                "mode": self.mode,
                "clothing_override": self.clothing_override,
                "clothing_source": "manual" if self.clothing_override != "auto" else "camera",
                "pids": dict(self.pids),
            }


def _make_handler(control: ControlState, get_state):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload=None):
            body = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            if payload is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):  # CORS preflight from the hub-served dashboard
            self._send(204)

        def do_GET(self):
            if self.path.split("?")[0] == "/state":
                self._send(200, get_state())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path.split("?")[0] != "/control":
                return self._send(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"null")
                control.apply(body)
            except (ValueError, contracts.ContractError) as e:  # JSONDecodeError is a ValueError
                return self._send(400, {"error": str(e)})
            self._send(200, get_state())

        def log_message(self, *args):  # keep the App Lab console readable
            pass

    return Handler


def serve(control: ControlState, get_state=None, host="0.0.0.0", port=DEFAULT_PORT):
    """Start the API on a daemon thread and return the server (call .shutdown() to stop).

    get_state: callable returning the full /state dict. main.py passes its own; the
    default exposes only the control state, labelled as debug.
    """
    if get_state is None:
        def get_state():
            return {"debug": True, "inputs": "none", "control": control.snapshot()}
    server = ThreadingHTTPServer((host, port), _make_handler(control, get_state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    import time

    ctl = ControlState(on_camera=lambda on: print("camera ->", "start" if on else "stop", flush=True))
    serve(ctl)
    print(f"Device API dev server on http://127.0.0.1:{DEFAULT_PORT} (Ctrl+C to stop)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
