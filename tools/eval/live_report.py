"""LIVE comfort-model results as a Markdown table for the README (T5.4).  Owner: Tuan Anh.

Reads the device's prospective feedback log and reports, per person, baseline vs personal
3-class accuracy and MAE with the honest verdict. Mock and simulated votes are excluded.

    # copy the log from the board first (it never leaves the desk otherwise):
    scp arduino@pw-desk.local:ArduinoApps/<app>/python/state/feedback_log.jsonl /tmp/feedback_log.jsonl
    python3 tools/eval/live_report.py --log /tmp/feedback_log.jsonl

    # or straight from a running device (includes any labels; check the "Data" column):
    python3 tools/eval/live_report.py --device http://pw-desk.local:8000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "device", "python"))
import evaluation  # noqa: E402

DISPLAY = {"tuananh": "Tuan Anh", "minh": "Minh"}
HEADER = ("| Person | Votes | Baseline accuracy | Personal accuracy | Baseline MAE | Personal MAE | Verdict | Data |\n"
          "|---|---|---|---|---|---|---|---|")


def row(name, r):
    if not r.get("n"):
        return f"| {name} | 0 | – | – | – | – | {r['verdict']} | |"
    return (f"| {name} | {r['n']} | {r['baseline_accuracy']:.2f} | {r['personal_accuracy']:.2f} | "
            f"{r['baseline_mae']:.2f} | {r['personal_mae']:.2f} | {r['verdict']} | {', '.join(r['labels'])} |")


def from_log(path):
    log = evaluation.FeedbackLog(path)
    names = sorted({e["profile"] for e in log.entries()}) or list(DISPLAY)
    rows = [row(DISPLAY.get(n, n), log.report(n, live_only=True)) for n in names]
    rows.append(row("**All**", log.report(live_only=True)))
    skipped = len(log.entries()) - len(log.entries(live_only=True))
    return rows, skipped


def from_device(url):
    with urllib.request.urlopen(url.rstrip("/") + "/state", timeout=5) as r:
        s = json.load(r)
    return [row(p["display"], p["evaluation"]) for p in s["people"].values()], None


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--log", help="path to a copy of state/feedback_log.jsonl")
    g.add_argument("--device", help="device base URL, e.g. http://pw-desk.local:8000")
    args = ap.parse_args(argv)
    rows, skipped = from_log(args.log) if args.log else from_device(args.device)
    print(HEADER)
    print("\n".join(rows))
    if skipped:
        print(f"\n({skipped} mock/simulated vote(s) excluded.)")


if __name__ == "__main__":
    main()
