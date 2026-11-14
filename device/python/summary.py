"""Minimal comfort summary -> hub.  Owner: Tuan Anh (T3.3; kickoff part done).

POST http://<hub>:8080/summary with exactly the spec C8 shape (contracts.check_summary()).
One summary per profile; heartbeat every 60 s, plus immediately when anything changes.
Persistent pseudonymous pid per profile ("p-" + 4 hex), resettable from the dashboard.

Kickoff part (done): where the hub is, and a sender + test command.
Still T3.3: building summaries from comfort state, heartbeat/on-change scheduling.

Hub address, first match wins:
  1. env var PW_HUB_URL                     (only if App Lab passes it to the app)
  2. file device/python/state/hub_url       (one line, e.g. http://192.168.0.7:8080;
                                              gitignored, survives app restarts: use this)
  3. none -> summaries are not sent, and /state says so

Test from the board (synthetic, present=false, NOT live evidence):
    python3 summary.py --set-hub http://<laptop-ip>:8080
    python3 summary.py --test
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

import contracts

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
HUB_URL_FILE = os.path.join(STATE_DIR, "hub_url")
TIMEOUT_S = 3


def hub_url() -> tuple[str | None, str]:
    """(url, where it came from). Strips a trailing slash."""
    env = os.environ.get("PW_HUB_URL", "").strip()
    if env:
        return env.rstrip("/"), "env PW_HUB_URL"
    try:
        with open(HUB_URL_FILE) as f:
            url = f.read().strip()
        if url:
            return url.rstrip("/"), HUB_URL_FILE
    except OSError:
        pass
    return None, "not configured"


def set_hub_url(url: str) -> None:
    if not url.startswith("http://"):
        raise ValueError("hub URL must look like http://<laptop-ip>:8080")
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(HUB_URL_FILE, "w") as f:
        f.write(url.rstrip("/") + "\n")


def post_summary(msg: dict, url: str | None = None) -> int:
    """Validate and POST one summary. Returns the HTTP status (204 expected).

    Raises contracts.ContractError for a bad summary, OSError/URLError if the hub is
    unreachable (the caller logs it and retries on the next heartbeat).
    """
    contracts.check_summary(msg)
    url = url or hub_url()[0]
    if not url:
        raise OSError("hub URL not configured (PW_HUB_URL or state/hub_url)")
    req = urllib.request.Request(url + "/summary", data=json.dumps(msg).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.status
    except urllib.error.HTTPError as e:   # 400 etc.: return the status, don't raise
        return e.code


TEST_SUMMARY = {"pid": "p-a001", "present": False, "mode": "heating",
                "band_now": [21.0, 22.5], "state": 0, "unresolved": False}


def _cli(argv):
    if len(argv) >= 2 and argv[0] == "--set-hub":
        set_hub_url(argv[1])
    url, where = hub_url()
    print(f"hub URL: {url}  (from {where})")
    if "--test" in argv:
        if not url:
            sys.exit("FAIL  no hub URL: run  python3 summary.py --set-hub http://<laptop-ip>:8080")
        try:
            code = post_summary(TEST_SUMMARY, url)
        except OSError as e:
            sys.exit(f"FAIL  cannot reach {url}: {e}  (hub running? same network? right IP?)")
        print(("PASS" if code == 204 else "FAIL") + f"  POST /summary -> {code} (expect 204)")
        print(f"Synthetic test entry {TEST_SUMMARY['pid']}; remove it on the laptop with:")
        print(f"  curl -X DELETE {url}/summaries/{TEST_SUMMARY['pid']}")
        sys.exit(0 if code == 204 else 1)


if __name__ == "__main__":
    _cli(sys.argv[1:])
