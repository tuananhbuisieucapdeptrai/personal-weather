"""T1.4: does Tuan Anh's code install and run on the UNO Q?  Owner: Tuan Anh.

Run ON the board, from this folder (device/python of the deployed app):
    python3 env_check.py                         # everything
    python3 env_check.py --hub http://192.168.0.7:8080   # also ping the hub

Checks, printed as PASS / WARN / FAIL:
  - Python version and platform; RAM and disk
  - packages: stdlib pieces we rely on; numpy / cv2 (needed by Minh's vision only);
    arduino.app_utils (only present inside App Lab)
  - self-tests of contracts, sensing, shutter, comfort (PMV) on the board's CPU
  - speed of the comfort estimate (budget: < 50 ms per estimate)
  - device API: starts on a free port, GET /state, POST /control valid + invalid
  - port 8000 (production API port): free or taken (Minh's camera test app uses it)
  - state/ folder writable (pseudonyms, hub URL, later feedback log)
  - hub reachable (if --hub given or state/hub_url / PW_HUB_URL set)
Nothing is installed by this script and nothing is left running.
"""
from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
results: list[tuple[str, str, str]] = []


def rec(status, name, detail=""):
    results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""), flush=True)


def section(title):
    print(f"\n== {title} ==", flush=True)


def check_platform():
    section("Platform")
    v = sys.version_info
    rec("PASS" if v >= (3, 9) else "FAIL", "Python >= 3.9", f"{platform.python_version()} at {sys.executable}")
    rec("PASS", "platform", f"{platform.machine()} / {platform.system()} {platform.release()}")
    try:
        with open("/proc/meminfo") as f:
            mem = {l.split(":")[0]: int(l.split()[1]) for l in f if l.split()[1:2]}
        avail = mem.get("MemAvailable", 0) // 1024
        rec("PASS" if avail > 300 else "WARN", "RAM available", f"{avail} MB of {mem.get('MemTotal', 0) // 1024} MB")
    except OSError:
        rec("WARN", "RAM available", "no /proc/meminfo (not Linux?)")
    free = shutil.disk_usage(HERE).free // (1024 * 1024)
    rec("PASS" if free > 500 else "WARN", "disk free here", f"{free} MB")
    rec("PASS", "CPU cores", str(os.cpu_count()))


def check_packages():
    section("Packages")
    for mod in ("json", "math", "secrets", "threading", "http.server", "urllib.request", "queue"):
        try:
            importlib.import_module(mod)
        except ImportError as e:
            rec("FAIL", f"stdlib {mod}", str(e))
    rec("PASS", "stdlib modules used by Tuan Anh's code", "json, math, secrets, threading, http.server, urllib, queue")
    for mod, why in (("numpy", "vision frames (Minh)"), ("cv2", "camera capture (Minh)"),
                     ("arduino.app_utils", "Bridge; present only inside App Lab")):
        try:
            m = importlib.import_module(mod)
            rec("PASS", f"{mod} available", f"{getattr(m, '__version__', 'ok')} ({why})")
        except Exception as e:
            rec("WARN", f"{mod} not importable here", f"{type(e).__name__}; needed for: {why}")
    rec("PASS", "pythermalcomfort NOT needed", "PMV is hand-written (comfort.py); nothing to install")


def check_selftests():
    section("Self-tests on this CPU")
    for name in ("contracts", "sensing", "shutter", "comfort"):
        try:
            m = importlib.import_module(name)
            t0 = time.perf_counter()
            m._selftest()
            rec("PASS", f"{name} self-test", f"{(time.perf_counter() - t0) * 1000:.0f} ms")
        except Exception as e:
            rec("FAIL", f"{name} self-test", f"{type(e).__name__}: {e}")


def check_speed():
    section("Speed")
    try:
        import comfort
        n = 200
        t0 = time.perf_counter()
        for i in range(n):
            comfort.estimate(19.0 + (i % 60) / 10, 40.0, "none", comfort.PersonalModel(0.2, 3))
        ms = (time.perf_counter() - t0) * 1000 / n
        rec("PASS" if ms < 50 else "WARN", "comfort.estimate() incl. band", f"{ms:.2f} ms each (budget 50 ms)")
        t0 = time.perf_counter()
        for i in range(1000):
            comfort.baseline_pmv(21.5, 40.0, "outer")
        rec("PASS", "baseline PMV only", f"{(time.perf_counter() - t0):.3f} ms each")
    except Exception as e:
        rec("FAIL", "speed test", f"{type(e).__name__}: {e}")


def _http(method, url, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def check_api():
    section("Device API (temporary instance on a free port)")
    try:
        import api
        ctl = api.ControlState(state_dir=tempfile.mkdtemp())
        srv = api.serve(ctl, host="127.0.0.1", port=0)
        port = srv.server_address[1]
        base = f"http://127.0.0.1:{port}"
        try:
            s1, _ = _http("GET", base + "/state")
            s2, b2 = _http("POST", base + "/control", {"clothing": "outer", "mode": "heating"})
            s3, _ = _http("POST", base + "/control", {"clothing": "jacket"})
            ok = (s1, s2, s3) == (200, 200, 400) and json.loads(b2)["control"]["clothing_source"] == "manual"
            rec("PASS" if ok else "FAIL", "api.py serves /state and /control", f"GET {s1}, POST {s2}, invalid {s3}")
        finally:
            srv.shutdown()
            srv.server_close()
    except Exception as e:
        rec("FAIL", "api.py", f"{type(e).__name__}: {e}")

    s = socket.socket()
    s.settimeout(1)
    taken = s.connect_ex(("127.0.0.1", 8000)) == 0
    s.close()
    rec("WARN" if taken else "PASS", "port 8000",
        "IN USE (stop Minh's camera test app before running production api.py)" if taken else "free")


def check_state_dir():
    section("Storage")
    state = os.path.join(HERE, "state")
    try:
        os.makedirs(state, exist_ok=True)
        probe = os.path.join(state, ".write_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        rec("PASS", "state/ writable", state)
    except OSError as e:
        rec("FAIL", "state/ writable", f"{state}: {e}")


def check_hub(cli_url):
    section("Hub")
    import summary
    url, where = (cli_url.rstrip("/"), "--hub") if cli_url else summary.hub_url()
    if not url:
        rec("WARN", "hub URL", "not configured: python3 summary.py --set-hub http://<laptop-ip>:8080")
        return
    try:
        code, body = _http("GET", url + "/ping")
        rec("PASS" if code == 200 else "FAIL", "hub /ping", f"{url} (from {where}) -> {code}")
    except OSError as e:
        rec("FAIL", "hub /ping", f"{url} (from {where}): {e}")


def main(argv):
    hub = argv[argv.index("--hub") + 1] if "--hub" in argv else None
    print(f"Personal Weather T1.4 environment check on {socket.gethostname()}", flush=True)
    check_platform()
    check_packages()
    check_selftests()
    check_speed()
    check_api()
    check_state_dir()
    check_hub(hub)
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print("\n================ T1.4 SUMMARY ================")
    print(f"  {len(results) - len(fails) - len(warns)} PASS, {len(warns)} WARN, {len(fails)} FAIL")
    for status, name, detail in fails + warns:
        print(f"  {status}  {name}: {detail}")
    print("==============================================")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
