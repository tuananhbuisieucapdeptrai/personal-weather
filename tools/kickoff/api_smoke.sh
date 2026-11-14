#!/usr/bin/env bash
# Smoke test for the device API /control contract (docs/kickoff-guide.md item 5).
# Usable once api.py exists (T3.2). Usage:  tools/kickoff/api_smoke.sh [host:port]
set -u
DEV="${1:-pw-desk.local:8000}"
pass=0; fail=0; BODY=$(mktemp); trap 'rm -f "$BODY"' EXIT
check() {  # name, expected HTTP code, JSON body
  code=$(curl -s -o "$BODY" -w '%{http_code}' -m 5 -X POST "http://$DEV/control" \
         -H 'Content-Type: application/json' -d "$3")
  if [ "$code" = "$2" ]; then echo "PASS  $1 ($code)"; pass=$((pass+1));
  else echo "FAIL  $1: expected $2, got $code: $(head -c 200 "$BODY")"; fail=$((fail+1)); fi
}
code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://$DEV/state")
if [ "$code" = "200" ]; then echo "PASS  GET /state (200)"; pass=$((pass+1)); else echo "FAIL  GET /state: got $code"; fail=$((fail+1)); fi
check "override outer"          200 '{"clothing":"outer"}'
check "override none"           200 '{"clothing":"none"}'
check "back to camera"          200 '{"clothing":"auto"}'
check "invalid clothing -> 400" 400 '{"clothing":"jacket"}'
check "empty body -> 400"       400 '{}'
check "mode heating"            200 '{"mode":"heating"}'
check "unknown field -> 400"    400 '{"volume":3}'
check "broken JSON -> 400"      400 '{"mode":'
check "camera off"              200 '{"camera":"off"}'
check "camera on"               200 '{"camera":"on"}'
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
