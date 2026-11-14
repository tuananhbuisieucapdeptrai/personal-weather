"""Consent-only, local UNO Q clothing dataset capture; no network upload.

Run in a board shell after stopping any app that owns /dev/video0. For every
session/class, invoke separately. Keep the held-out session entirely out of
training and validation. Images are intentionally saved outside this repo.
"""
import argparse
from pathlib import Path
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--session", required=True, help="e.g. s2 or s3_holdout")
    p.add_argument("--label", required=True, choices=("outer", "none"))
    p.add_argument("--person", required=True, help="consenting participant code, not name")
    p.add_argument("--output", type=Path, default=Path.home() / "pw-clothing-data")
    p.add_argument("--camera", default="/dev/video0")
    p.add_argument("--count", type=int, default=8)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--width", type=int, default=1280, help="Requested camera width")
    p.add_argument("--height", type=int, default=720, help="Requested camera height")
    p.add_argument("--size", type=int, default=0,
                   help="Maximum saved crop edge; 0 keeps native crop resolution (default)")
    a = p.parse_args()
    if not a.session.replace("_", "").isalnum() or not a.person.replace("_", "").isalnum():
        p.error("session/person may contain only letters, digits, underscore")
    if a.count < 1 or a.interval < 0.5:
        p.error("count must be positive and interval at least 0.5 seconds")
    if a.width < 1 or a.height < 1 or a.size < 0:
        p.error("width/height must be positive; size must be zero or positive")
    import cv2
    out = a.output / a.session / a.label
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(a.camera, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {a.camera}; stop the vision app and check the camera")
    print(f"Capturing {a.count} torso crops for {a.person}, {a.session}, {a.label} in {out}")
    print("Capture only after the participant explicitly agrees. Press Ctrl+C to stop.")
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, a.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, a.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        print(f"Requested camera: {a.width}x{a.height}; native crop saved unless --size is set", flush=True)
        for i in range(a.count):
            # Keep draining frames while waiting, so poses are current rather
            # than frames left in the camera's queue from the previous capture.
            deadline = time.monotonic() + a.interval
            while True:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera read failed")
                if time.monotonic() >= deadline:
                    break
            h, w = frame.shape[:2]
            if i == 0:
                print(f"Actual camera frame: {w}x{h}", flush=True)
                if (w, h) != (a.width, a.height):
                    print("Camera chose a different resolution; using its actual frames.", flush=True)
            # Fixed desk-camera ROI below the head. Review samples before training;
            # adjust camera framing rather than silently using a face/background.
            crop = frame[int(.38*h):int(.90*h), int(.20*w):int(.80*w)]
            if crop.size == 0:
                raise RuntimeError("Frame too small for torso crop")
            # Preserve garment proportions and original detail. Never upscale.
            if a.size and max(crop.shape[:2]) > a.size:
                scale = a.size / max(crop.shape[:2])
                crop = cv2.resize(crop, (max(1, round(crop.shape[1]*scale)),
                                         max(1, round(crop.shape[0]*scale))),
                                  interpolation=cv2.INTER_AREA)
            path = out / f"{a.person}_{a.session}_{a.label}_{int(time.time()*1000)}_{i:03}.jpg"
            if not cv2.imwrite(str(path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise RuntimeError(f"Could not save {path}")
            print(f"{i+1}/{a.count} {path} ({crop.shape[1]}x{crop.shape[0]})", flush=True)
    finally:
        cap.release()


if __name__ == "__main__":
    main()
