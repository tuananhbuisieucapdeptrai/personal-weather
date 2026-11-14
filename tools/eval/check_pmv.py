"""Compare the runtime PMV (device/python/comfort.py) with pythermalcomfort.  Laptop only.

The runtime uses a hand-written ISO 7730 function because pythermalcomfort pulls numba,
scipy and numpy (~300 MB), which is too heavy for the UNO Q. This script is the evidence
that the two agree over the conditions the device will see.

    python3 -m venv .venv && .venv/bin/pip install pythermalcomfort
    .venv/bin/python tools/eval/check_pmv.py
"""
from __future__ import annotations

import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "device", "python"))
import comfort  # noqa: E402

warnings.filterwarnings("ignore")
from pythermalcomfort.models import pmv_ppd_iso  # noqa: E402


def main():
    worst, n = (0.0, None), 0
    for t10 in range(160, 301, 5):              # 16.0 .. 30.0 degC
        t = t10 / 10
        for rh in (20, 30, 40, 50, 60, 70):
            for clothing, clo in comfort.CLO.items():
                mine = comfort.baseline_pmv(t, rh, clothing)
                ref = float(pmv_ppd_iso(tdb=t, tr=t, vr=comfort.AIR_SPEED, rh=rh, met=comfort.MET,
                                        clo=clo, model="7730-2005", limit_inputs=False,
                                        round_output=False).pmv)
                d = abs(mine - ref)
                n += 1
                if d > worst[0]:
                    worst = (d, (t, rh, clothing, mine, ref))
                if comfort.classify(mine) != comfort.classify(ref):
                    print(f"CLASS MISMATCH at t={t} rh={rh} {clothing}: {mine:.4f} vs {ref:.4f}")
    print(f"{n} conditions compared; max |PMV difference| = {worst[0]:.5f} at {worst[1]}")
    sys.exit(0 if worst[0] < 0.01 else 1)


if __name__ == "__main__":
    main()
