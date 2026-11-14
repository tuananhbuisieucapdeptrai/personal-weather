"""Calibrate the shutter darkness threshold (docs/kickoff-guide.md item 4).

Measures the mean grey level of the camera for four conditions and suggests the
DARK_THRESHOLD for device/python/shutter.py. Frames are only measured in memory:
nothing is saved.

Run it where the camera is plugged in (best: on the UNO Q, with the real enclosure):
    python3 tools/kickoff/shutter_calibrate.py            # camera 0
    python3 tools/kickoff/shutter_calibrate.py --camera 1
Needs OpenCV (`pip install opencv-python` on a laptop). On a Mac, allow camera access
for the terminal app when asked.
"""
from __future__ import annotations

import argparse
import time

CONDITIONS = [
    ("normal", "Normal desk light, sit in front of the camera", "real"),
    ("lights_off", "Room as dark as it realistically gets (lights off / evening), shutter OPEN", "real"),
    ("hand", "Hand held over the lens (shutter open)", "info"),
    ("shutter", "Shutter CLOSED", "shutter"),
]


def suggest_threshold(stats: dict) -> tuple[float | None, str]:
    """stats: name -> (min, mean, max). Returns (threshold, explanation)."""
    shutter_max = stats["shutter"][2]
    darkest_real = min(stats[n][0] for n, _, kind in CONDITIONS if kind == "real")
    if shutter_max >= darkest_real:
        return None, (f"OVERLAP: shutter max {shutter_max:.1f} >= darkest real scene {darkest_real:.1f}. "
                      "Make the shutter more light-tight (black tape/card) and rerun.")
    thr = round((shutter_max + darkest_real) / 2, 1)
    margin = darkest_real - shutter_max
    note = "good margin" if margin >= 10 else "SMALL margin: improve the shutter if you can"
    return thr, f"shutter max {shutter_max:.1f}, darkest real {darkest_real:.1f} ({note})"


def measure(cap, seconds=3.0):
    levels, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        ok, frame = cap.read()
        if ok:
            levels.append(float(frame.mean()))
    if not levels:
        raise SystemExit("camera returned no frames: wrong --camera index?")
    return min(levels), sum(levels) / len(levels), max(levels)


def main():
    import cv2  # imported here so suggest_threshold() is testable without OpenCV

    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=320)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    if not cap.isOpened():
        raise SystemExit(f"cannot open camera {args.camera}")
    for _ in range(10):  # let auto-exposure settle
        cap.read()

    stats = {}
    try:
        for name, prompt, _ in CONDITIONS:
            input(f"\n{prompt}. Press Enter, then hold still for 3 s...")
            time.sleep(1.0)  # auto-exposure adapts
            stats[name] = measure(cap)
            lo, avg, hi = stats[name]
            print(f"  {name:10} min {lo:6.1f}  mean {avg:6.1f}  max {hi:6.1f}")
    finally:
        cap.release()

    thr, why = suggest_threshold(stats)
    print("\n" + why)
    if thr is not None:
        print(f"-> In device/python/shutter.py set:  DARK_THRESHOLD = {thr}")
        print("   Write the four numbers into the table in docs/kickoff-guide.md item 4.")
    if stats["hand"][1] < (thr or 0):
        print("   Note: a hand over the lens also reads as 'shutter' after 3 s. That's acceptable"
              " (camera stops = privacy-safe), but say so in the privacy receipt.")


if __name__ == "__main__":
    main()
