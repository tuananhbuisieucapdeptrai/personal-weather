#!/usr/bin/env bash
# Smoke test for the device API /control contract (docs/kickoff-guide.md item 5).
# Usable once api.py exists (T3.2). Usage:  tools/kickoff/api_smoke.sh [host:port]
set -u
DEV="${1:-pw-desk.local:8000}"
pass=0; fail=0
check() {  # name, expected HTTP code, JSON body
  code=$(curl -s -o /tmp/pw_smoke_body -w '%{http_code}' -m 5 -X POST "http://$DEV/control" \
         -H 'Content-Type: application/json' -d "$3")
  if [ "$code" = "$2" ]; then echo "PASS  $1 ($code)"; pass=$((pass+1));
  else echo "FAIL  $1: expected $2, got $code: $(head -c 200 /tmp/pw_smoke_body)"; fail=$((fail+1)); fi
}
check "override outer"          200 '{"clothing":"outer"}'
check "override none"           200 '{"clothing":"none"}'
check "back to camera"          200 '{"clothing":"auto"}'
check "invalid clothing -> 400" 400 '{"clothing":"jacket"}'
check "empty body -> 400"       400 '{}'
check "mode heating"            200 '{"mode":"heating"}'
check "unknown field -> 400"    400 '{"volume":3}'
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
