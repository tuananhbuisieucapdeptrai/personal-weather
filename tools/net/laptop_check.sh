#!/usr/bin/env bash
# Run on the laptop (macOS) once laptop AND board are on the hotspot.
# docs/kickoff-guide.md item 6. Usage: tools/net/laptop_check.sh [board-host]
set -u
BOARD="${1:-pw-desk.local}"
IFACE=$(route -n get default 2>/dev/null | awk '/interface:/ {print $2}')
IP=$(ipconfig getifaddr "${IFACE:-en0}")
echo "Laptop interface ${IFACE:-?}, IP ${IP:-NONE}"
echo
if ping -c 2 -t 3 "$BOARD" >/dev/null 2>&1; then
  echo "PASS  laptop -> $BOARD reachable"
else
  echo "FAIL  laptop cannot reach $BOARD (same hotspot? hostname set and board rebooted? try its IP)"
fi
echo
echo "Now testing board -> laptop on port 8080 for 60 s."
echo "On the BOARD run:   curl -s http://$IP:8080/ping"
echo "(If macOS asks to allow incoming connections for Python, click Allow.)"
python3 - "$IP" <<'PY'
import http.server, sys, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"pong from laptop\n")
        print(f"PASS  board -> laptop: request from {self.client_address[0]}", flush=True)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("0.0.0.0", 8080), H)
threading.Timer(60, srv.shutdown).start()
srv.serve_forever()
print("Listener closed.")
PY
echo
echo "On the board, set:  export PW_HUB_URL=http://$IP:8080"
