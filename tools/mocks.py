"""Fake sensors, knob and vision.  Owner: Tuan Anh (T1.1).

Implements the SAME public API as device/python/bridge_io.py (start, send) and
device/python/vision.py (start, stop, latest), so main.py swaps one import.
Every message produced here must pass the checks in device/python/contracts.py.
Anything coming from mocks is shown as "MOCK INPUT" on the dashboard.
"""
