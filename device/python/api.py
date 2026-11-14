"""Device local API for the dashboard (local only, labelled debug).  Owner: Tuan Anh (T3.2).

    GET  /state     dashboard snapshot
    POST /control   any subset of {"profile", "camera", "mode", "reset_pid", "clothing"}

Port 8000.  Bodies are checked with contracts.check_control().
"""
