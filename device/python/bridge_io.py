"""Linux <-> sketch over the App Lab Bridge.  Owner: Minh (M2.2).

Public API (frozen, see docs/interfaces.md "Python module interfaces"):

    start(on_message)  register Bridge handlers; on_message(dict) gets every
                       sketch -> Linux message as a contract dict
                       ({"t", "rh"} / {"knob": "turn", "pos"} / {"knob": "press"}).
                       Called from the Bridge thread: the callback must only enqueue.
    send(msg)          send one Linux -> sketch contract dict ({"face": ...} / {"beep": ...}).

main.py never imports the Bridge itself; tools/mocks.py implements the same two functions.
"""


def start(on_message):
    raise NotImplementedError("M2.2")


def send(msg):
    raise NotImplementedError("M2.2")
