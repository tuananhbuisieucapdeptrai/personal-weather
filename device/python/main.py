"""Main loop on the UNO Q Linux side.  Owner: Tuan Anh (T2.4, T3.1).

Wires the pieces together; never talks to the Bridge or camera directly:
  bridge_io.start(on_message) / bridge_io.send(msg)   (or tools/mocks.py with the same API)
  vision.start() / vision.stop() / vision.latest()    (or tools/mocks.py with the same API)
  comfort, suggest  -> decisions;  api -> dashboard;  summary -> hub
Contracts: docs/interfaces.md section 0.2, checked by contracts.py.
"""
