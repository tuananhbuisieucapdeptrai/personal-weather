"""End-to-end tests of the device app (T2.4) with mocks and simulated time. No hardware.

    python3 -m unittest tools/tests/test_app.py -v
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "device" / "python"), str(ROOT / "tools")]
import api        # noqa: E402
import app        # noqa: E402
import comfort    # noqa: E402
import contracts  # noqa: E402
import mocks      # noqa: E402
import suggest    # noqa: E402


class FakeSender:
    def __init__(self):
        self.sent = []
        self.status = {}

    def send(self, msg, at):
        self.sent.append((at, msg))


class Rig:
    """Mock board + app with deterministic simulated time."""

    def __init__(self, scenario="office", clothing="uncertain", vision_script=None, state_dir=None,
                 accelerated=True):
        self.dir = state_dir or tempfile.mkdtemp()
        self.bridge = mocks.MockBridge(scenario=scenario, realtime=False, seed=4)
        self.vision = mocks.MockVision(clothing=clothing, conf=0.9 if clothing != "uncertain" else 0.4,
                                       script=vision_script)
        self.vision.attach_clock(self.bridge)
        self.control = api.ControlState(state_dir=self.dir)
        self.sender = FakeSender()
        self.app = app.App(self.bridge, self.vision, self.control, lambda: 1_000_000 + self.bridge.sim_time,
                           self.dir, inputs="mock", accelerated=accelerated, sender=self.sender)
        self.app.start()

    def run(self, seconds):
        for _ in range(int(seconds)):
            self.bridge.step(1)
            self.app.tick()

    def knob(self, *actions):
        for a in actions:
            if a == "p":
                self.bridge.press()
            else:
                self.bridge.turn(a)
            self.run(1)

    def faces(self):
        return [m for _, m in self.bridge.sent]


class TestApp(unittest.TestCase):
    def test_demo_steps_4_and_5(self):
        # Vision has no classifier yet: dashboard says "none"; camera "sees" the layer at t=20.
        r = Rig(vision_script=[(20, {"clothing": "outer", "conf": 0.88})])
        r.run(3)
        self.assertIsNone(r.app.get_state()["people"]["tuananh"]["decision"]["offer"])   # clothing unknown
        self.assertNotIn({"face": "suggest_layer_on"}, r.faces())
        r.control.apply({"clothing": "none"})
        r.run(2)
        self.assertIn({"face": "suggest_layer_on"}, r.faces())
        self.assertIn({"beep": "chime"}, r.faces())
        r.knob("p")                                   # bump: preview only
        self.assertIsNotNone(r.app.active.engine.active)
        r.knob(1, "p")                                # DO
        p = r.app.active
        self.assertIsNotNone(p.follow_up)
        self.assertEqual(p.follow_up.labels, ["ACCELERATED"])
        r.control.apply({"clothing": "auto"})         # back to camera: it sees the layer (t>=20)
        r.run(suggest.DEMO_WAIT_S + 1)
        self.assertEqual(p.follow_up.state, "asking")
        self.assertEqual(p.follow_up.action_check, suggest.CONFIRMED_CAMERA)
        self.assertEqual(r.app.get_state()["interaction"], "follow_up")
        r.knob(0, "p")                                # OK now
        self.assertIsNone(p.follow_up)
        self.assertEqual(p.last_outcome["result"], "helped")
        self.assertEqual(p.experience.counts, {"add_layer": [1, 0]})
        self.assertEqual(r.app.log.report("tuananh")["by_source"], {"follow_up": 1})
        r.run(3)
        self.assertEqual(r.app.last_face, {"face": "smile"})
        for m in r.faces():
            contracts.check_to_sketch(m)

    def test_two_profiles_diverge(self):
        r = Rig(clothing="none")
        r.run(3)
        # Tuan Anh dismisses the offered suggestion first, so the knob means feedback.
        r.knob(0, "p")                                # LATER
        r.knob(-1, "p")                               # feedback: cold
        r.control.apply({"profile": "minh"})
        r.run(1)
        r.knob(0, "p")                                # Minh: OK
        r.knob(0, "p")
        ta, mi = r.app.profiles["tuananh"].model, r.app.profiles["minh"].model
        self.assertEqual(ta.offset, 0.0)              # baseline already said cold
        self.assertGreater(mi.offset, 0.3)
        self.assertEqual(r.app.log.report("minh")["n"], 2)
        t, rh = r.app.env.reading(r.app.clock())["t"], 40
        self.assertNotEqual(comfort.classify(ta.predict(comfort.baseline_pmv(t, rh, "none"))),
                            comfort.classify(mi.predict(comfort.baseline_pmv(t, rh, "none"))))

    def test_single_press_in_idle_votes_ok(self):
        r = Rig(clothing="outer")                    # comfortable: no suggestion
        r.run(3)
        r.knob("p")                                  # one press, no turn = "OK"
        self.assertEqual(r.app.log.report()["n"], 1)
        self.assertEqual(r.app.log.entries()[-1]["vote"], 0)
        self.assertIn({"face": "check"}, r.faces())
        r.knob(1)                                    # a turn without a press is abandoned
        r.run(app.FEEDBACK_IDLE_S + 2)
        self.assertEqual(r.app.log.report()["n"], 1)
        self.assertEqual(r.app.last_face, {"face": "smile"})

    def test_cold_vote_triggers_layer_suggestion_now(self):
        r = Rig(scenario="steady", clothing="none")       # 21.5 degC, model starts at 0 offset
        r.control.apply({"clothing": "none"})
        r.app.profiles["tuananh"].model.offset = 0.6      # model thinks this person is fine
        r.run(3)
        self.assertIsNone(r.app.active.engine.active)
        r.knob(-1, "p")                                   # "I'm cold"
        r.run(3)
        self.assertEqual(r.app.active.estimate["personal_class"], -1)
        self.assertTrue(r.app.active.estimate.get("from_report"))
        self.assertIsNotNone(r.app.active.engine.active)  # "Put on a layer?" right away
        self.assertIn({"face": "suggest_layer_on"}, r.faces())

    def test_summaries(self):
        r = Rig(clothing="none")
        r.run(3)
        by_pid = {}
        for _, m in r.sender.sent:
            contracts.check_summary(m)
            by_pid.setdefault(m["pid"], []).append(m)
        self.assertEqual(len(by_pid), 2)                                # one per profile
        pids = r.control.snapshot()["pids"]
        self.assertTrue(by_pid[pids["tuananh"]][-1]["present"])
        self.assertFalse(by_pid[pids["minh"]][-1]["present"])          # inactive: absent
        self.assertIn("band_with_fix", by_pid[pids["tuananh"]][-1])     # heating: add a layer
        n = len(r.sender.sent)
        r.run(10)
        self.assertLessEqual(len(r.sender.sent) - n, 2)                 # no spam when nothing changes
        r.run(app.SUMMARY_HEARTBEAT_S)
        self.assertGreaterEqual(len(r.sender.sent) - n, 2)              # heartbeat
        r.control.apply({"mode": "cooling"})
        n = len(r.sender.sent)
        r.run(1)
        self.assertEqual(len(r.sender.sent) - n, 2)                     # change -> immediate
        self.assertEqual(r.sender.sent[-1][1]["mode"], "cooling")

    def test_camera_off_and_presence_fallback(self):
        r = Rig(clothing="none")
        r.run(3)
        r.vision.close_shutter()
        r.run(1)
        self.assertIn({"face": "eye_off"}, r.faces())
        self.assertIn({"beep": "low"}, r.faces())
        st = r.app.get_state()
        self.assertEqual(st["presence"], {"present": False, "source": "knob_activity"})
        self.assertIn("shutter", st["privacy_receipt"]["images"])
        r.knob(0)
        self.assertTrue(r.app.get_state()["presence"]["present"])      # knob use = someone there

    def test_persistence_and_state_json(self):
        d = tempfile.mkdtemp()
        r = Rig(clothing="outer", state_dir=d)
        r.run(3)
        r.knob(1, "p")                                                  # warm vote
        off = r.app.profiles["tuananh"].model.offset
        st = r.app.get_state()
        json.dumps(st)                                                  # serialisable for /state
        self.assertEqual(st["labels"], ["MOCK INPUT", "ACCELERATED"])
        self.assertEqual(st["privacy_receipt"]["sent"][0].keys() - {"band_with_fix"},
                         {"pid", "present", "mode", "band_now", "state", "unresolved"})
        r2 = Rig(clothing="outer", state_dir=d)
        self.assertEqual(r2.app.profiles["tuananh"].model.offset, off)
        self.assertEqual(r2.app.log.report("tuananh")["n"], 1)
        self.assertEqual(r2.control.snapshot()["pids"], r.control.snapshot()["pids"])

    def test_not_possible_keeps_discomfort_visible(self):
        r = Rig(clothing="none")
        r.run(3)
        r.knob(-1, "p")                                                 # NO: not possible
        r.run(2)
        d = r.app.get_state()["people"]["tuananh"]["decision"]
        self.assertEqual(d["reason"], "blocked_not_possible")
        self.assertTrue(d["unresolved"])
        last = [m for _, m in r.sender.sent if m["pid"] == r.control.snapshot()["pids"]["tuananh"]][-1]
        self.assertTrue(last["unresolved"])
        self.assertNotIn("band_with_fix", last)


if __name__ == "__main__":
    unittest.main()
