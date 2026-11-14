"""Minimal comfort summary -> hub.  Owner: Tuan Anh (T3.3).

POST http://<hub>:8080/summary with exactly the spec C8 shape (contracts.check_summary()).
One summary per profile; heartbeat every 60 s, plus immediately when anything changes.
Persistent pseudonymous pid per profile ("p-" + 4 hex), resettable from the dashboard.
"""
