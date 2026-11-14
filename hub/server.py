"""Room hub (laptop).  Owner: Tuan Anh (T4.2; kickoff version).

    GET    /                 dashboard (hub/static/index.html; ?device=http://<board>:8000)
    POST   /summary          C8 summary from a device -> 204 (400 if it breaks the contract)
    GET    /summaries        every known person: summary + receipt age + stale/effective presence
    DELETE /summaries/<pid>  remove one entry (e.g. a synthetic test summary)
    GET    /ping             liveness check (used by tools/net/laptop_check.sh)

Rules (spec C8, docs/interfaces.md 0.2.4):
  - the hub stamps RECEIPT time and ignores device clocks
  - a summary older than 2 minutes is stale: the person is treated as absent
  - only pseudonymous pids, never names or images
The dashboard (T4.1) and room add-ons (A1-A4) build on /summaries.

Run (binds every interface so the UNO Q can reach it):
    python3 hub/server.py            # port 8080
    python3 hub/server.py --port 8081
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device", "python"))
import contracts  # noqa: E402  (shared contract checks)

STALE_AFTER_S = 120
DASHBOARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html")


class SummaryStore:
    """Latest summary per pid, stamped with receipt time. Thread-safe."""

    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._by_pid: dict[str, dict] = {}

    def receive(self, msg: dict, source: str) -> dict:
        contracts.check_summary(msg)
        entry = {"summary": msg, "received_at": self._clock(), "source": source}
        with self._lock:
            self._by_pid[msg["pid"]] = entry
        return entry

    def remove(self, pid: str) -> bool:
        with self._lock:
            return self._by_pid.pop(pid, None) is not None

    def view(self) -> list[dict]:
        now = self._clock()
        with self._lock:
            entries = list(self._by_pid.values())
        out = []
        for e in entries:
            age = now - e["received_at"]
            stale = age > STALE_AFTER_S
            out.append({
                **e["summary"],
                "received_at": e["received_at"],
                "age_s": round(age, 1),
                "stale": stale,
                "present_effective": e["summary"]["present"] and not stale,
                "source": e["source"],
            })
        return sorted(out, key=lambda r: r["pid"])


def make_handler(store: SummaryStore):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload=None):
            body = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            if payload is not None:
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_OPTIONS(self):
            self._send(204)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/dashboard"):
                try:
                    with open(DASHBOARD, "rb") as f:
                        body = f.read()
                except OSError:
                    return self._send(404, {"error": "dashboard missing"})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/ping":
                self._send(200, {"ok": True, "hub": "personal-weather"})
            elif path == "/summaries":
                self._send(200, {"stale_after_s": STALE_AFTER_S, "people": store.view()})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path.split("?")[0] != "/summary":
                return self._send(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                msg = json.loads(self.rfile.read(length) or b"null")
                store.receive(msg, source=self.client_address[0])
            except (ValueError, contracts.ContractError) as e:
                print(f"[hub] REJECTED from {self.client_address[0]}: {e}", flush=True)
                return self._send(400, {"error": str(e)})
            print(f"[hub] {time.strftime('%H:%M:%S')} summary from {self.client_address[0]}: "
                  f"{json.dumps(msg)}", flush=True)
            self._send(204)

        def do_DELETE(self):
            parts = self.path.split("?")[0].strip("/").split("/")
            if len(parts) == 2 and parts[0] == "summaries":
                return self._send(204 if store.remove(parts[1]) else 404)
            self._send(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    return Handler


def serve(store: SummaryStore, host="0.0.0.0", port=8080):
    server = ThreadingHTTPServer((host, port), make_handler(store))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    serve(SummaryStore(), args.host, args.port)
    print(f"[hub] listening on {args.host}:{args.port}  (POST /summary, GET /summaries)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
