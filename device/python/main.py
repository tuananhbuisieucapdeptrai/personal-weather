"""Main loop on the UNO Q Linux side.  Owner: Tuan Anh (T2.4, T3.1).

Wires the pieces together; never talks to the Bridge or camera directly:
  bridge_io.start(on_message) / bridge_io.send(msg)   (or tools/mocks.py with the same API)
  vision.start() / vision.stop() / vision.latest()    (or tools/mocks.py with the same API)
  comfort, suggest  -> decisions;  api -> dashboard;  summary -> hub
Contracts: docs/interfaces.md section 0.2, checked by contracts.py.
"""

# ---- TEMPORARY (kickoff, until T2.4): run the board check -----------------------
# Set RUN_BOARD_CHECK = False once items 1-3 of docs/kickoff-guide.md pass.
RUN_BOARD_CHECK = True

if __name__ == "__main__" and RUN_BOARD_CHECK:
    import time

    from arduino.app_utils import App

    import board_check

    _done = False

    def _loop():
        global _done
        if not _done:
            _done = True
            board_check.run()
        time.sleep(1)

    App.run(user_loop=_loop)
