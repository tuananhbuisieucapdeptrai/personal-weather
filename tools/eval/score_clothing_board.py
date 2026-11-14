"""Re-score Minh's clothing holdout ON THE BOARD with the OpenCV/ONNX runtime (M2.4 check).

Photos never leave the board: this prints only counts, a confusion matrix and timings.
Run inside the App Lab image (it has OpenCV), with the app's python/ folder and the
photo folder mounted, e.g.:

  docker run --rm --user 1000:1000 --entrypoint python3 \
    -v ~/pw-eval:/app -v ~/pw-clothing-data:/data:ro -w /app \
    ghcr.io/arduino/app-bricks/python-apps-base:0.13.2 score_clothing_board.py \
    [--model=clip|mobilenet] /data/holdout_jacket4/outer:outer /data/holdout_top4/none:none
"""
from __future__ import annotations

import glob
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clothing  # noqa: E402
from clothing import LABELS  # noqa: E402


def main(args):
    which = "clip"
    if args and args[0].startswith("--model="):
        which, args = args[0].split("=", 1)[1], args[1:]
    clf = clothing.ClipClothing() if which == "clip" else clothing.MobileNetClothing()
    threshold = clothing.CLIP_SCORE_MIN if which == "clip" else clothing.SCORE_MIN
    print("backend:", clf.backend)
    conf = {(t, p): 0 for t in LABELS for p in LABELS}
    abstain, times, n = 0, [], 0
    for spec in args:
        folder, truth = spec.rsplit(":", 1)
        for path in sorted(glob.glob(os.path.join(folder, "*.jpg"))):
            img = cv2.imread(path)
            t0 = time.monotonic()
            s = clf.scores(img)                     # images are already torso crops
            times.append((time.monotonic() - t0) * 1000)
            pred = LABELS[int(s.argmax())]
            conf[(truth, pred)] += 1
            abstain += int(float(s.max()) < threshold)
            n += 1
    correct = sum(v for (t, p), v in conf.items() if t == p)
    print(f"images: {n}   argmax accuracy: {correct}/{n} = {correct / n:.1%}")
    print("actual \\ predicted   none  outer")
    for t in LABELS:
        print(f"{t:>18}   {conf[(t, 'none')]:4d}  {conf[(t, 'outer')]:5d}")
    print(f"below threshold {threshold} (would be 'uncertain' per frame): {abstain}/{n}")
    times.sort()
    print(f"inference ms: mean {sum(times) / len(times):.1f}, median {times[len(times) // 2]:.1f}, "
          f"max {times[-1]:.1f} (first call includes warm-up)")


if __name__ == "__main__":
    main(sys.argv[1:])
