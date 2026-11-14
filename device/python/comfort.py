"""Comfort estimate: PMV baseline, 3 classes, personal offset, comfort band.
Owner: Tuan Anh (T1.2, T1.3; prospective records for T2.3).

Wording for the UI/README (spec C3): "an approximate comfort estimate using measured
conditions and explicitly assumed inputs".

BASELINE (T1.2): PMV per ISO 7730 (Fanger), hand-written here, stdlib only.
  pythermalcomfort was tried: it pulls numba + scipy + numpy (~300 MB), too heavy for the
  UNO Q, so the plan's fallback is the runtime implementation. The library is kept as a
  laptop-side reference: tools/eval/check_pmv.py compares both (max difference reported).
  Measured: air temperature t, relative humidity rh. ASSUMED (declared in ASSUMPTIONS):
  radiant temperature = air temperature, still air 0.1 m/s, sedentary office activity
  1.2 met, no external work, clothing from vision (outer 1.0 clo / none 0.6 clo).

CLASSES (T1.3): PMV < -0.5 cold (-1), -0.5..+0.5 OK (0), > +0.5 warm (+1).

PERSONAL OFFSET (T1.3): one number per person, added to the baseline PMV.
  After each feedback vote, the personal prediction is pulled toward the vote's zone
  (cold: <= -0.75, OK: -0.25..+0.25, warm: >= +0.75). If it is already inside, nothing
  changes. Step size 1/(n+2), never below 0.15: big at first, smaller with evidence,
  still able to follow a change. Clipped to +-2.
  Every observe() call returns the baseline and personal predictions made BEFORE the
  update: that is the prospective evaluation log (T2.3 aggregates it; see score()).

COMFORT BAND (T1.3): air temperatures where the personal prediction is OK, at the
  current humidity and clothing. Found by bisection (PMV rises with temperature).
"""
from __future__ import annotations

import math

# ---- Declared assumptions (shown in the evidence panel and README) ----------------
CLO = {"outer": 1.0, "none": 0.6, "uncertain": 0.8}   # uncertain: midpoint, flagged
ASSUMPTIONS = {
    "radiant_temperature": "equal to measured air temperature",
    "air_speed_m_s": 0.1,
    "metabolic_rate_met": 1.2,
    "external_work_met": 0.0,
    "clothing_clo": CLO,
}
AIR_SPEED = ASSUMPTIONS["air_speed_m_s"]
MET = ASSUMPTIONS["metabolic_rate_met"]

# ISO 7730 applicability ranges (outside them the number is still computed, but flagged)
RANGES = {"t": (10.0, 30.0), "rh_pa": (0.0, 2700.0)}

COLD, OK, WARM = -1, 0, 1
CLASS_NAMES = {COLD: "cold", OK: "OK", WARM: "warm"}


# ---- T1.2: PMV / PPD (ISO 7730 Annex D algorithm) ---------------------------------
def vapour_pressure_pa(t: float, rh: float) -> float:
    return rh * 10.0 * math.exp(16.6536 - 4030.183 / (t + 235.0))


def pmv_ppd(ta: float, tr: float, vr: float, rh: float, met: float, clo: float,
            wme: float = 0.0) -> tuple[float, float]:
    """Fanger PMV and PPD (%). ta/tr in degC, vr m/s, rh %, met, clo."""
    pa = vapour_pressure_pa(ta, rh)
    icl = 0.155 * clo
    m = met * 58.15
    w = wme * 58.15
    mw = m - w
    fcl = 1.0 + 1.29 * icl if icl <= 0.078 else 1.05 + 0.645 * icl
    hcf = 12.1 * math.sqrt(vr)
    taa, tra = ta + 273.0, tr + 273.0
    tcla = taa + (35.5 - ta) / (3.5 * icl + 0.1)
    p1 = icl * fcl
    p2 = p1 * 3.96
    p3 = p1 * 100.0
    p4 = p1 * taa
    p5 = 308.7 - 0.028 * mw + p2 * (tra / 100.0) ** 4
    xn, xf = tcla / 100.0, tcla / 50.0
    hc = hcf
    for _ in range(150):
        if abs(xn - xf) <= 0.00015:
            break
        xf = (xf + xn) / 2.0
        hcn = 2.38 * abs(100.0 * xf - taa) ** 0.25
        hc = max(hcf, hcn)
        xn = (p5 + p4 * hc - p2 * xf ** 4) / (100.0 + p3 * hc)
    else:
        raise ArithmeticError("PMV clothing temperature did not converge")
    tcl = 100.0 * xn - 273.0
    hl1 = 3.05e-3 * (5733.0 - 6.99 * mw - pa)                 # skin diffusion
    hl2 = 0.42 * (mw - 58.15) if mw > 58.15 else 0.0          # sweating
    hl3 = 1.7e-5 * m * (5867.0 - pa)                          # latent respiration
    hl4 = 0.0014 * m * (34.0 - ta)                            # dry respiration
    hl5 = 3.96 * fcl * (xn ** 4 - (tra / 100.0) ** 4)         # radiation
    hl6 = fcl * hc * (tcl - ta)                               # convection
    ts = 0.303 * math.exp(-0.036 * m) + 0.028
    pmv = ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)
    ppd = 100.0 - 95.0 * math.exp(-0.03353 * pmv ** 4 - 0.2179 * pmv ** 2)
    return pmv, ppd


def baseline_pmv(t: float, rh: float, clothing: str) -> float:
    """PMV from measured t/rh with the declared assumptions."""
    return pmv_ppd(t, t, AIR_SPEED, rh, MET, CLO[clothing])[0]


# ---- T1.3: three classes ----------------------------------------------------------
def classify(pmv: float) -> int:
    if pmv < -0.5:
        return COLD
    if pmv > 0.5:
        return WARM
    return OK


# ---- T1.3: personal offset --------------------------------------------------------
VOTE_ZONE = {COLD: (-math.inf, -0.75), OK: (-0.25, 0.25), WARM: (0.75, math.inf)}
PRIOR_N = 2.0
MIN_STEP = 0.15
MAX_OFFSET = 2.0


class PersonalModel:
    """One person's offset. Serialisable with to_dict()/from_dict() (stored on the device)."""

    def __init__(self, offset: float = 0.0, n: int = 0):
        self.offset = offset
        self.n = n

    def predict(self, pmv_base: float) -> float:
        return pmv_base + self.offset

    def observe(self, vote: int, pmv_base: float) -> dict:
        """Record a feedback vote (-1/0/+1). Returns the prospective record (pre-update)."""
        if vote not in (COLD, OK, WARM):
            raise ValueError("vote must be -1, 0 or 1")
        before = self.predict(pmv_base)
        record = {
            "vote": vote,
            "pmv_baseline": round(pmv_base, 3),
            "baseline_class": classify(pmv_base),
            "pmv_personal": round(before, 3),
            "personal_class": classify(before),
            "offset_before": round(self.offset, 3),
            "n_before": self.n,
        }
        lo, hi = VOTE_ZONE[vote]
        target = min(max(before, lo), hi)          # nearest point of the vote's zone
        step = max(1.0 / (self.n + PRIOR_N), MIN_STEP)
        self.offset = min(max(self.offset + step * (target - before), -MAX_OFFSET), MAX_OFFSET)
        self.n += 1
        record["offset_after"] = round(self.offset, 3)
        return record

    def to_dict(self) -> dict:
        return {"offset": self.offset, "n": self.n}

    @classmethod
    def from_dict(cls, d: dict) -> "PersonalModel":
        return cls(offset=float(d.get("offset", 0.0)), n=int(d.get("n", 0)))


# ---- T1.3: comfort band -----------------------------------------------------------
BAND_SEARCH = (10.0, 35.0)


def _solve_t(rh: float, clothing: str, offset: float, target_pmv: float) -> float | None:
    """Air temperature where baseline PMV + offset == target (PMV rises with t)."""
    lo, hi = BAND_SEARCH
    f = lambda t: baseline_pmv(t, rh, clothing) + offset - target_pmv  # noqa: E731
    if f(lo) > 0 or f(hi) < 0:
        return None
    for _ in range(40):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def comfort_band(rh: float, clothing: str, offset: float = 0.0) -> list[float] | None:
    """[low, high] degC (0.1 steps, inside the OK zone) or None if nowhere in 10-35 degC."""
    lo = _solve_t(rh, clothing, offset, -0.5)
    hi = _solve_t(rh, clothing, offset, +0.5)
    if lo is None and hi is None:
        return None
    lo = BAND_SEARCH[0] if lo is None else math.ceil(lo * 10 - 1e-9) / 10
    hi = BAND_SEARCH[1] if hi is None else math.floor(hi * 10 + 1e-9) / 10
    return [round(lo, 1), round(hi, 1)] if lo <= hi else None


# ---- Everything for one moment ----------------------------------------------------
def estimate(t: float, rh: float, clothing: str, model: PersonalModel | None = None) -> dict:
    model = model or PersonalModel()
    pmv, ppd = pmv_ppd(t, t, AIR_SPEED, rh, MET, CLO[clothing])
    personal = model.predict(pmv)
    return {
        "t": t, "rh": rh, "clothing": clothing, "clo": CLO[clothing],
        "clothing_assumed": clothing == "uncertain",
        "pmv_baseline": round(pmv, 2), "ppd_baseline": round(ppd, 1),
        "baseline_class": classify(pmv),
        "offset": round(model.offset, 3), "feedback_count": model.n,
        "pmv_personal": round(personal, 2), "personal_class": classify(personal),
        "band": comfort_band(rh, clothing, model.offset),
        "in_iso_range": (RANGES["t"][0] <= t <= RANGES["t"][1]
                         and vapour_pressure_pa(t, rh) <= RANGES["rh_pa"][1]),
    }


def score(records: list[dict]) -> dict:
    """Prospective 3-class accuracy and MAE on -1/0/+1 for baseline vs personal (T2.3)."""
    n = len(records)
    if not n:
        return {"n": 0}
    out = {"n": n}
    for name in ("baseline", "personal"):
        preds = [r[f"{name}_class"] for r in records]
        votes = [r["vote"] for r in records]
        out[f"{name}_accuracy"] = round(sum(p == v for p, v in zip(preds, votes)) / n, 3)
        out[f"{name}_mae"] = round(sum(abs(p - v) for p, v in zip(preds, votes)) / n, 3)
    return out


# ---- Self-test ----------------------------------------------------------------------
# ISO 7730:2005 Annex D, Table D.1 (ta, tr, var, rh, met, clo) -> PMV
ISO_TABLE = [
    (22.0, 22.0, 0.10, 60, 1.2, 0.5, -0.75),
    (27.0, 27.0, 0.10, 60, 1.2, 0.5, 0.77),
    (27.0, 27.0, 0.30, 60, 1.2, 0.5, 0.44),
    (23.5, 25.5, 0.10, 60, 1.2, 0.5, -0.01),
    (23.5, 25.5, 0.30, 60, 1.2, 0.5, -0.55),
    (19.0, 19.0, 0.10, 40, 1.2, 1.0, -0.60),
]


def _selftest():
    for ta, tr, v, rh, met, clo, want in ISO_TABLE:
        got = pmv_ppd(ta, tr, v, rh, met, clo)[0]
        assert abs(got - want) <= 0.02, (ta, tr, v, rh, met, clo, got, want)
    assert abs(pmv_ppd(22, 22, 0.1, 60, 1.2, 0.5)[1] - 16.9) < 0.5      # PPD row 1

    assert classify(-0.51) == COLD and classify(-0.5) == OK and classify(0.5) == OK
    assert classify(0.51) == WARM

    # Same room, same clothing: two people diverge after two votes each.
    t, rh = 21.5, 40.0
    base = baseline_pmv(t, rh, "none")
    assert classify(base) == COLD                       # no layer at 21.5 degC -> cold
    assert classify(baseline_pmv(t, rh, "outer")) == OK  # a layer fixes it
    ta, minh = PersonalModel(), PersonalModel()
    rec = []
    for _ in range(2):
        rec.append(ta.observe(COLD, base))
        rec.append(minh.observe(OK, base))
    assert ta.offset == 0.0                              # already agreed: no change
    assert minh.offset > 0.3 and classify(minh.predict(base)) == OK
    assert rec[1]["personal_class"] == COLD and rec[1]["offset_after"] > 0   # pre-update logged

    # Bands: personal offset shifts the band; a layer lowers it; offset clipping.
    b0 = comfort_band(rh, "none")
    bm = comfort_band(rh, "none", minh.offset)
    bo = comfort_band(rh, "outer")
    assert b0[0] < b0[1] and bm[0] < b0[0] and bo[0] < b0[0], (b0, bm, bo)
    lo_t, hi_t = b0
    assert classify(baseline_pmv(lo_t, rh, "none")) == OK and classify(baseline_pmv(hi_t, rh, "none")) == OK
    assert classify(baseline_pmv(lo_t - 0.1, rh, "none")) == COLD
    big = PersonalModel()
    for _ in range(100):
        big.observe(WARM, -3.0)
    assert big.offset == MAX_OFFSET
    assert PersonalModel.from_dict(minh.to_dict()).offset == minh.offset

    s = score(rec)
    assert s["n"] == 4 and s["baseline_accuracy"] == 0.5
    e = estimate(t, rh, "uncertain", minh)
    assert e["clothing_assumed"] and e["in_iso_range"] and e["band"]
    print(f"comfort OK: ISO 7730 table matched ({len(ISO_TABLE)} rows, tol 0.02); "
          f"band none={b0} outer={bo} minh(offset {minh.offset:+.2f})={bm}")


if __name__ == "__main__":
    _selftest()
