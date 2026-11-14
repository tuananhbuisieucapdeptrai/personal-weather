"""Lifecycle tests use child processes and synthetic scalars, never a real camera."""
import os
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'device' / 'python'))
import contracts
import vision


def responsive(send, stop):
    send.send((dict(present=True, clothing='uncertain', conf=None, camera='on'),
               dict(phase='running', capture_open=True, error=None)))
    stop.wait(5)
    send.send((vision.unknown(), dict(phase='off', capture_open=False, error=None)))


def shuttered(send, stop):
    send.send((vision.unknown('shutter'), dict(phase='shutter', capture_open=False, error=None)))


def blocked(send, stop):
    time.sleep(30)


def crashed(send, stop):
    os._exit(3)


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for state')


class Lifecycle(unittest.TestCase):
    def test_motion_is_a_cue_without_a_face(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV/numpy not installed on this machine")
        d = vision.DeskPresenceDetector.__new__(vision.DeskPresenceDetector)
        d.cv2, d.face, d.prev = cv2, None, None
        still = np.full((480, 640, 3), 120, np.uint8)
        self.assertFalse(d.detect(still)[0])                 # first frame: no reference yet
        self.assertFalse(d.detect(still.copy())[0])          # nothing changed: empty chair
        moved = still.copy()
        moved[200:300, 250:400] = 200                        # someone shifts
        found, cue = d.detect(moved)
        self.assertTrue(found)
        self.assertEqual(cue['presence_cue'], 'motion')

    def test_presence_hold(self):
        t = [0.0]
        p = vision.PresenceHold(clock=lambda: t[0])
        self.assertFalse(p.update(True))            # one cue is not enough
        t[0] += 0.5
        self.assertTrue(p.update(True))             # second cue within 3 s -> present
        for _ in range(118):                        # 59 s of misses while sitting still
            t[0] += 0.5
            self.assertTrue(p.update(False))
        t[0] += 2.0
        self.assertFalse(p.update(False))           # > 60 s without a cue -> absent
        t[0] += 5.0
        self.assertFalse(p.update(True))            # stale single cue doesn't re-enter

    def service(self, worker, watchdog=8):
        service = vision.VisionService(worker, watchdog)
        self.addCleanup(service.stop)
        return service

    def test_import_does_not_capture(self):
        self.assertEqual(vision.latest(), vision.unknown())

    def test_stop_idempotence_and_restart(self):
        s = self.service(responsive)
        s.stop()
        s.start()
        wait_for(lambda: s.latest()['camera'] == 'on')
        pid = s._process.pid
        s.start()
        self.assertEqual(pid, s._process.pid)
        contracts.check_vision(s.latest())
        sample = s.latest()
        sample['present'] = False
        self.assertTrue(s.latest()['present'])
        s.stop()
        self.assertFalse(s._process.is_alive())
        self.assertEqual(s.latest(), vision.unknown())
        s.start()
        wait_for(lambda: s.latest()['camera'] == 'on')
        self.assertNotEqual(pid, s._process.pid)

    def test_shutter_latches_until_explicit_restart(self):
        s = self.service(shuttered)
        s.start()
        wait_for(lambda: s.latest()['camera'] == 'shutter')
        wait_for(lambda: not s._monitor.is_alive())
        pid = s._process.pid
        time.sleep(.1)
        self.assertEqual(s.latest(), vision.unknown('shutter'))
        self.assertFalse(s._process.is_alive())
        s.start()
        wait_for(lambda: s.latest()['camera'] == 'shutter')
        self.assertNotEqual(pid, s._process.pid)

    def test_blocked_capture_can_be_stopped(self):
        s = self.service(blocked)
        s.start()
        began = time.monotonic()
        s.stop()
        self.assertLess(time.monotonic() - began, 5)
        self.assertFalse(s._process.is_alive())
        self.assertEqual(s.latest(), vision.unknown())

    def test_watchdog_closes_hung_worker(self):
        s = self.service(blocked, .5)
        s.start()
        wait_for(lambda: s.diagnostics().get('error') is not None)
        self.assertFalse(s._process.is_alive())
        self.assertEqual(s.latest(), vision.unknown())

    def test_crash_does_not_leave_stale_presence(self):
        s = self.service(crashed)
        s.start()
        wait_for(lambda: s.diagnostics().get('error') is not None)
        self.assertEqual(s.latest(), vision.unknown())
        self.assertFalse(s.diagnostics()['capture_open'])

    def test_presence_stability(self):
        p = vision.PresenceFilter()
        self.assertFalse(p.update(False))
        self.assertFalse(p.update(True))
        self.assertFalse(p.update(False))
        self.assertFalse(p.update(True))
        self.assertFalse(p.update(True))
        self.assertTrue(p.update(True))
        self.assertTrue(p.update(False))


if __name__ == '__main__':
    unittest.main()
