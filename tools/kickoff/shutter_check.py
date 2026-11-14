"""Standalone physical shutter check; does not implement the vision classifier.

Run on the UNO Q with its USB camera, after shutter_calibrate.py:
    python3 tools/kickoff/shutter_check.py --threshold 12
No frames are saved or transmitted. Restart requires an explicit Enter press.
"""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "device" / "python"))
from shutter import ShutterDetector, brightness


def capture_until_closed(cap, threshold, emit=print, clock=time.monotonic):
    detector = ShutterDetector(threshold=threshold)
    last_report = float("-inf")
    try:
        if not cap.isOpened():
            raise RuntimeError("Cannot open camera; check index and stop other camera apps.")
        emit("Camera capturing. Close the shutter; Ctrl+C stops the check.")
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Camera read failed; this is NOT shutter detection.")
            now = clock()
            level = brightness(frame)
            if now - last_report >= 1:
                emit(f"brightness={level:.2f}, threshold={threshold}")
                last_report = now
            if detector.update(level, now):
                break
    finally:
        cap.release()
    emit('Capture released: camera="shutter". Verify the camera LED is off.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--threshold", type=float, required=True)
    args = parser.parse_args()
    if not 0 < args.threshold < 255:
        parser.error("threshold must be between 0 and 255")
    import cv2
    try:
        while True:
            cap = cv2.VideoCapture(args.camera)
            capture_until_closed(cap, args.threshold)
            answer = input("Open shutter; Enter to explicitly restart, or q to quit: ")
            if answer.strip().lower() == "q":
                return
    except KeyboardInterrupt:
        print("\nStopped; camera released.")


if __name__ == "__main__":
    main()
