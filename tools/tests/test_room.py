"""Hub room endpoints (T4.3/T4.4) over real HTTP on a free port. No device needed.

    python3 -m unittest tools/tests/test_room.py -v
"""
import json
from pathlib import Path
import sys
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "hub"), str(ROOT / "device" / "python")]
import room    # noqa: E402
import server  # noqa: E402


class TestRoomHTTP(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.store = server.SummaryStore(clock=lambda: self.now[0])
        self.room = room.Room(lambda: self.now[0], demo=True)
        self.srv = server.serve(self.store, host="127.0.0.1", port=0, room=self.room)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw and r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def desk(self, fix=True, mode="heating"):
        msg = {"pid": "p-0a01", "present": True, "mode": mode, "band_now": [22.6, 26.1], "state": -1, "unresolved": False}
        if fix:
            msg["band_with_fix"] = [19.6, 24.1]
        self.assertEqual(self.call("POST", "/summary", msg)[0], 204)

    def test_pages_served(self):
        for path in ("/", "/room"):
            code, body = self.call("GET", path)
            self.assertEqual(code, 200)
            self.assertIn(b"<html", body)

    def test_recommend_agree_and_sims(self):
        code, v = self.call("GET", "/room.json")
        self.assertEqual(v["recommendation"]["reason"], "unknown_mode")      # no desks yet
        self.desk()
        _, v = self.call("GET", "/room.json")
        self.assertEqual((v["recommendation"]["setpoint"], v["recommendation"]["reason"]), (20.0, "propose"))
        self.assertEqual(v["labels"], ["ACCELERATED"])
        _, v = self.call("POST", "/room/sims", {"on": True})
        self.assertEqual(len(v["people"]), 4)
        self.assertEqual(v["labels"], ["SIMULATED", "ACCELERATED"])
        self.assertTrue(all(p["sim"] for p in v["people"][1:]))
        self.assertEqual(self.call("POST", "/room/agree", {"setpoint": 25.0})[0], 400)   # not the recommendation
        code, v = self.call("POST", "/room/agree", {"setpoint": 20.0})
        self.assertEqual(code, 200)
        self.assertEqual(v["setpoint"], 20.0)
        self.assertEqual(v["recommendation"]["reason"], "keep_current")
        # The desk later says "not possible": the room would need to be warmer,
        # but nothing is re-proposed inside the re-check window for the same people.
        self.desk(fix=False)
        _, v = self.call("GET", "/room.json")
        self.assertEqual(v["recommendation"]["reason"], "recently_agreed")
        self.assertEqual(v["recommendation"]["setpoint"], 23.0)
        self.now[0] += room.DEMO_RECHECK_S + 1
        self.desk(fix=False)
        _, v = self.call("GET", "/room.json")
        self.assertEqual(v["recommendation"]["reason"], "propose")

    def test_stale_desk_is_absent_and_mode_from_desks(self):
        self.desk(mode="cooling")
        _, v = self.call("GET", "/room.json")
        self.assertEqual(v["recommendation"]["mode"], "cooling")
        self.now[0] += 121                                               # > 2 min: stale
        _, v = self.call("GET", "/room.json")
        self.assertEqual(v["recommendation"]["mode"], "unknown")
        self.assertFalse(v["people"][0]["present"])

    def test_unresolved_minutes_and_energy(self):
        msg = {"pid": "p-0b01", "present": True, "mode": "heating", "band_now": [23.0, 26.0],
               "state": -1, "unresolved": True}                          # said "not possible": no band_with_fix
        self.call("POST", "/summary", msg)
        for _ in range(3):                                               # 3 x 60 s, demo counts 10x
            self.now[0] += 60
            self.call("POST", "/summary", msg)
        _, v = self.call("GET", "/room.json")
        p = v["people"][0]
        self.assertEqual(p["unresolved_min"], 30.0)
        self.assertEqual(p["weight"], 2.0)
        e = v["energy"]
        self.assertEqual(e["measured"]["unresolved"], 1)
        self.assertEqual(e["proposed"]["status"], "proposed")
        self.assertFalse(e["proposed"]["thermostat_verified"])
        self.assertNotIn("%", e["modelled"]["text"])
        # Leaves (stale): minutes stay visible, no longer counted as present.
        self.now[0] += 121
        _, v = self.call("GET", "/room.json")
        self.assertEqual(v["people"][0]["unresolved_min"], 30.0)
        self.assertFalse(v["people"][0]["present"])

    def test_setpoint_validation(self):
        self.assertEqual(self.call("POST", "/room/setpoint", {"value": 22.0})[1]["setpoint"], 22.0)
        self.assertEqual(self.call("POST", "/room/setpoint", {"value": 40})[0], 400)
        self.assertEqual(self.call("POST", "/room/nope", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
