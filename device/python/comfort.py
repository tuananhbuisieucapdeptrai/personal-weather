"""Comfort estimate.  Owner: Tuan Anh (T1.2, T1.3, T2.3).

- PMV baseline (ISO 7730) from measured t, rh with declared assumed inputs:
  radiant = air temperature, still air, seated activity,
  clothing outer -> ~1.0 clo, none -> ~0.6 clo.
  pythermalcomfort if it installs on the board, else a hand-written function.
- 3 classes: PMV < -0.5 cold (-1), -0.5..+0.5 OK (0), > +0.5 warm (+1).
- Personal offset: one per-person bias, updated after each feedback.
- Comfort band: temperatures where the offset-corrected prediction is OK.
- Prospective evaluation: log baseline and personal class BEFORE each update.
"""
