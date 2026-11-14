"""Camera -> presence, clothing, camera status.  Owner: Minh (M1.4, M2.4, M3.1).

Public API (frozen, see docs/interfaces.md "Python module interfaces"):

    start()    start the camera worker (camera status "on")
    stop()     stop capture completely; the process/thread really stops (status "off")
    latest()   newest vision dict, never blocks:
               {"present": true, "clothing": "outer", "conf": 0.86, "camera": "on"}

Images are processed in memory only: never written to disk, never sent.
Dark frames for ~3 s -> stop capture by itself and report camera "shutter".
"""


def start():
    raise NotImplementedError("M3.1")


def stop():
    raise NotImplementedError("M3.1")


def latest():
    raise NotImplementedError("M3.1")
