"""Suggestion engine and fix experience.  Owner: Tuan Anh (T2.1, T2.2).

- Mode-aware (spec section 2): heating / cooling / unknown.
- Responses: "Do it" (knob +1), "Not now" (knob 0), "Not possible for me" (knob -1).
- At most one suggestion every 15 minutes.
- Beta(1, 1) per person and fix; updates only after "Do it" + an actual follow-up
  response. Missing follow-up = unknown. "Not possible" never updates it.
"""
