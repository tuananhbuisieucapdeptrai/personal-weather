"""UNO Q camera lifecycle, shutter shutdown, presence (movement or face, with hold) and clothing.

Public API: start(), stop(), latest(). No capture occurs on import. Call start()
only on explicit application/operator intent; do not call it in every main-loop
iteration. Clothing stays uncertain: no classifier is installed here.

A spawn child owns all frames and the camera. Only scalar diagnostics and the
contract state cross the pipe. stop() waits for exit (terminating a blocked read
if necessary). Startup reports off/unknown until first inference; diagnostics
phase distinguishes startup from idle. Call entry points under a __main__ guard.
"""
from __future__ import annotations

import atexit
import glob
import multiprocessing as mp
import os
from pathlib import Path
import threading
import time

from shutter import DARK_THRESHOLD, ShutterDetector, brightness


def unknown(camera="off"):
    return dict(present=None, clothing="uncertain", conf=None, camera=camera)


class PresenceFilter:
    """Accept the first observation, then require 3 matching observations to change."""
    def __init__(self, count=3):
        self.count = count
        self.value = self.candidate = None
        self.hits = 0

    def update(self, detected):
        detected = bool(detected)
        if self.value is None:
            self.value = detected
        self.hits = self.hits + 1 if detected == self.candidate else 1
        self.candidate = detected
        if self.hits >= self.count:
            self.value = detected
        return self.value


class PresenceHold:
    """Presence with memory (desk use): present after ENTER_HITS cues within ENTER_WINDOW_S;
    absent only after no cue for HOLD_S (60 s: someone can sit very still). Sitting still or looking away briefly never flickers."""
    ENTER_HITS, ENTER_WINDOW_S, HOLD_S = 2, 3.0, 60.0

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.value = False
        self.hits = []
        self.last_cue = None

    def update(self, detected):
        now = self.clock()
        if detected:
            self.last_cue = now
            self.hits = [t for t in self.hits if now - t <= self.ENTER_WINDOW_S] + [now]
            if len(self.hits) >= self.ENTER_HITS:
                self.value = True
        elif self.value and (self.last_cue is None or now - self.last_cue > self.HOLD_S):
            self.value, self.hits = False, []
        return self.value


class DeskPresenceDetector:
    """Presence cue = small movement in the frame OR a visible frontal face. Never identity.

    The desk camera is framed on the chest (for the clothing model), so faces are often out
    of view. A seated person always moves a little (breathing, typing); an empty chair does
    not. Movement = share of pixels that changed between consecutive small grey frames.
    (Earlier full-body HOG and profile-face cues were removed: they rarely fire at a desk
    and cost most of the frame time.)
    """
    MOTION_PIXEL_DIFF = 18       # grey levels
    MOTION_MIN_SHARE = 0.003     # 0.3 % of pixels changed

    def __init__(self, cv2):
        self.cv2 = cv2
        self.face = self._load('haarcascade_frontalface_default.xml', required=False)
        self.prev = None

    def _load(self, name, required):
        cv2 = self.cv2
        candidates = [Path(__file__).parent / 'models' / name]
        data = getattr(getattr(cv2, 'data', None), 'haarcascades', None)
        if data:
            candidates.append(Path(data) / name)
        if getattr(cv2, '__file__', None):
            candidates.append(Path(cv2.__file__).parent / 'data' / name)
        candidates.extend(Path(root) / name for root in
                          ('/usr/share/opencv4/haarcascades', '/usr/share/opencv/haarcascades'))
        for path in candidates:
            if path.is_file():
                cascade = cv2.CascadeClassifier(str(path))
                if not cascade.empty():
                    return cascade
        if required:
            raise RuntimeError(f'Face model missing: place {name} from OpenCV in python/models/')
        return None

    def motion_share(self, frame):
        cv2 = self.cv2
        small = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY), (5, 5), 0)
        prev, self.prev = self.prev, small
        if prev is None:
            return 0.0
        changed = cv2.absdiff(small, prev) > self.MOTION_PIXEL_DIFF
        return float(changed.mean())

    def detect(self, frame):
        cv2 = self.cv2
        h, w = frame.shape[:2]
        if h < 128 or w < 64:
            raise RuntimeError('Frame too small for presence detector')
        share = self.motion_share(frame)
        if share >= self.MOTION_MIN_SHARE:
            return True, dict(face_count=None, motion=round(share, 4), presence_cue='motion')
        if self.face is not None:
            gray = cv2.cvtColor(cv2.resize(frame, (320, max(128, round(h * 320 / w)))), cv2.COLOR_BGR2GRAY)
            faces = self.face.detectMultiScale(cv2.equalizeHist(gray), scaleFactor=1.15,
                                              minNeighbors=4, minSize=(48, 48))
            if len(faces):
                return True, dict(face_count=len(faces), motion=round(share, 4), presence_cue='face')
        return False, dict(face_count=0, motion=round(share, 4), presence_cue='none')


def _open_camera(cv2):
    source = os.environ.get("PW_CAMERA_DEVICE")
    paths = [source] if source else sorted(glob.glob("/dev/video*"))
    if not paths:
        raise RuntimeError("No camera device; connect the USB camera to the UNO Q hub")
    for path in paths:
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, frame = cap.read() if cap.isOpened() else (False, None)
            if ok:
                return cap, frame, path
        except Exception:
            cap.release()
            raise
        cap.release()
    raise RuntimeError("No readable camera; stop other camera apps and check USB/power")


def _worker(send, stopping):
    """Only this process imports cv2, opens the camera or handles image arrays."""
    cap = None
    final = unknown()
    diag = dict(phase="starting", capture_open=False, frames=0, error=None,
                detector="movement or frontal face, 60 s hold (v4)", inference_ms=None,
                mean_inference_ms=None, max_inference_ms=None, inferences=0,
                threshold=DARK_THRESHOLD, level=None, device=None)
    try:
        import cv2
        cv2.setNumThreads(1)
        detector = DeskPresenceDetector(cv2)
        classifier = None
        last_clothing = ('uncertain', None)
        try:
            from clothing import ClothingClassifier
            classifier = ClothingClassifier()
            diag['clothing_classifier'] = classifier.backend
        except Exception as exc:
            diag['clothing_error'] = str(exc)
        cap, frame, path = _open_camera(cv2)
        diag.update(capture_open=True, device=path, phase="starting")
        send.send((unknown(), dict(diag)))
        shutter = ShutterDetector()
        presence = PresenceHold()
        current = unknown()
        next_inference = next_report = total_ms = 0.0
        while not stopping.is_set():
            now = time.monotonic()
            level = brightness(frame)
            diag.update(frames=diag["frames"] + 1, level=round(level, 3))
            if shutter.update(level, now):
                final = unknown("shutter")
                break
            if now >= next_inference:
                began = time.monotonic()
                detected, cues = detector.detect(frame)
                present = presence.update(detected)
                if classifier is not None:
                    if present:                       # every frame while someone is at the desk
                        try:
                            last_clothing = classifier.predict(frame)[:2]
                            diag['clothing_inference_ms'] = round(classifier.last_ms, 2)
                        except Exception as exc:
                            classifier.reset()
                            last_clothing = ('uncertain', None)
                            diag['clothing_error'] = str(exc)
                    elif not present:
                        # Only reset once the person has really gone; a single missed face
                        # (looking away) keeps the last stable clothing label.
                        classifier.reset()
                        last_clothing = ('uncertain', None)
                clothing, confidence = last_clothing if present else ('uncertain', None)
                if clothing == 'uncertain':
                    confidence = None if not present else confidence
                diag.update(cues)
                elapsed = (time.monotonic() - began) * 1000
                total_ms += elapsed
                n = diag["inferences"] + 1
                diag.update(phase="running", inferences=n,
                            inference_ms=round(elapsed, 2),
                            mean_inference_ms=round(total_ms / n, 2),
                            max_inference_ms=round(max(diag["max_inference_ms"] or 0, elapsed), 2))
                current = dict(present=present, clothing=clothing, conf=confidence, camera="on")
                next_inference = time.monotonic() + 0.5
            if now >= next_report:
                send.send((current, dict(diag)))
                next_report = now + 0.2
            if stopping.is_set():
                break
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Camera stopped returning frames")
    except Exception as exc:
        diag["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if cap is not None:
            cap.release()
        diag.update(capture_open=False, phase=final["camera"], level=None)
        try:
            send.send((final, diag))
        except (BrokenPipeError, EOFError, OSError):
            pass
        send.close()


class VisionService:
    """The monitor keeps latest() free of camera I/O and process waits."""
    def __init__(self, worker=_worker, watchdog_s=8.0):
        self._worker = worker
        self._watchdog_s = watchdog_s
        self._ctx = mp.get_context("spawn")
        self._control = threading.Lock()
        self._lock = threading.Lock()
        self._process = self._monitor = self._stop_event = None
        self._state = unknown()
        self._diag = dict(phase="off", capture_open=False, error=None)

    def latest(self):
        with self._lock:
            return dict(self._state)

    def diagnostics(self):
        with self._lock:
            return dict(self._diag)

    def _publish(self, state, diag):
        with self._lock:
            self._state = dict(state)
            self._diag = dict(diag)

    @staticmethod
    def _terminate(process):
        if process.is_alive():
            process.terminate()
            process.join(1)
        if process.is_alive():
            process.kill()
            process.join(1)
        if process.is_alive():
            raise RuntimeError("Camera worker did not exit; cannot claim capture stopped")

    def _watch(self, process, recv):
        last = time.monotonic()
        terminal = False
        try:
            while True:
                if recv.poll(0.05):
                    try:
                        state, diag = recv.recv()
                    except EOFError:
                        break
                    self._publish(state, diag)
                    last = time.monotonic()
                    terminal = diag.get("phase") in ("off", "shutter")
                    if terminal:
                        break
                if not process.is_alive():
                    # Drain any final update before declaring an unexpected exit.
                    if recv.poll():
                        continue
                    break
                if time.monotonic() - last > self._watchdog_s:
                    self._terminate(process)
                    self._publish(unknown(), dict(phase="off", capture_open=False,
                        error="Camera worker timed out; capture process terminated"))
                    terminal = True
                    break
            process.join(1)
            if process.is_alive():
                self._terminate(process)
            if not terminal:
                self._publish(unknown(), dict(phase="off", capture_open=False,
                    error="Camera worker exited without a final state"))
        finally:
            recv.close()

    def start(self):
        with self._control:
            if self._monitor is not None and self._monitor.is_alive():
                if self.latest()["camera"] == "shutter":
                    self._monitor.join(2)
                else:
                    return  # idempotent while running or starting
            if self._monitor is not None and self._monitor.is_alive():
                raise RuntimeError("Previous camera worker is still stopping")
            recv, send = self._ctx.Pipe(duplex=False)
            self._stop_event = self._ctx.Event()
            process = self._ctx.Process(target=self._worker, args=(send, self._stop_event),
                                        name="personal-weather-camera", daemon=True)
            self._publish(unknown(), dict(phase="starting", capture_open=False, error=None))
            try:
                process.start()
            except Exception:
                recv.close()
                send.close()
                self._publish(unknown(), dict(phase="off", capture_open=False,
                                             error="Could not start camera process"))
                raise
            send.close()
            self._process = process
            self._monitor = threading.Thread(target=self._watch, args=(process, recv),
                                             name="vision-monitor", daemon=True)
            self._monitor.start()

    def stop(self):
        with self._control:
            if self._process is not None:
                self._stop_event.set()
                self._process.join(1.5)
                self._terminate(self._process)
            if self._monitor is not None:
                self._monitor.join(2)
                if self._monitor.is_alive():
                    raise RuntimeError("Vision monitor has not stopped")
            diag = self.diagnostics()
            diag.update(phase="off", capture_open=False, level=None)
            self._publish(unknown(), diag)


_service = VisionService()
start = _service.start
stop = _service.stop
latest = _service.latest
diagnostics = _service.diagnostics
atexit.register(stop)
