"""Standalone hardware check, not production vision or presence detection.

Only scalar brightness statistics leave camera memory. Each measurement is
explicitly started by the operator. Calibration is intentionally not persisted.
"""
import glob
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

commands = queue.Queue()
lock = threading.Lock()
state = dict(camera="off", capture_open=False, level=None, samples={},
             threshold=None, error=None, measuring=None, frames=0)


def update(**values):
    with lock:
        state.update(values)


def snapshot():
    with lock:
        return json.loads(json.dumps(state))


def open_camera():
    paths = sorted(glob.glob('/dev/video*'))
    print('Camera devices:', paths, flush=True)
    for path in paths:
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        ok, _ = cap.read() if cap.isOpened() else (False, None)
        if ok:
            print('Capturing from', path, flush=True)
            return cap
        cap.release()
    raise RuntimeError('No readable camera; check USB hub, power and device access.')


def worker():
    cap = None
    dark_since = None
    measurement = None
    levels = []
    deadline = 0
    settle = 0
    try:
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                command = None
            if command:
                try:
                    if command == 'off':
                        if cap is not None:
                            cap.release()
                        cap = None
                        measurement = None
                        update(camera='off', capture_open=False, measuring=None, level=None)
                    else:
                        if cap is None:
                            cap = open_camera()
                        dark_since = None
                        update(camera='on', capture_open=True, error=None)
                        if command in ('normal', 'dark', 'hand', 'shutter'):
                            measurement = command
                            levels = []
                            settle = time.monotonic() + 2
                            deadline = settle + 3
                            update(measuring=command)
                except Exception as exc:
                    update(error=str(exc), camera='off', capture_open=False)
                    print('ERROR:', exc, flush=True)
            if cap is None:
                time.sleep(.05)
                continue
            ok, frame = cap.read()
            if not ok:
                cap.release()
                cap = None
                measurement = None
                update(camera='off', capture_open=False, measuring=None,
                       error='Camera stopped returning frames')
                continue
            now = time.monotonic()
            level = float(frame.mean())
            with lock:
                state['level'] = round(level, 3)
                state['frames'] += 1
            if measurement:
                if now >= settle:
                    levels.append(level)
                if now >= deadline and levels:
                    stats = dict(min=min(levels), mean=sum(levels)/len(levels), max=max(levels))
                    with lock:
                        state['samples'][measurement] = stats
                        samples = dict(state['samples'])
                    print('MEASURED', measurement, stats, flush=True)
                    measurement = None
                    cap.release()
                    cap = None
                    update(camera='off', capture_open=False, measuring=None, level=None)
                    if all(k in samples for k in ('normal', 'dark', 'shutter')):
                        lo = samples['shutter']['max']
                        hi = min(samples[k]['min'] for k in ('normal', 'dark'))
                        threshold = (lo + hi) / 2 if lo < hi else None
                        update(threshold=threshold, error=None if threshold else
                               'Brightness ranges overlap; improve shutter or lighting and repeat.')
                        print('THRESHOLD', threshold, flush=True)
                continue
            threshold = snapshot()['threshold']
            if threshold is not None and level < threshold:
                if dark_since is None:
                    dark_since = now
                if now - dark_since >= 3:
                    cap.release()
                    cap = None
                    update(camera='shutter', capture_open=False, level=None)
                    print('SHUTTER: camera released; explicit Camera on required.', flush=True)
            else:
                dark_since = None
    finally:
        if cap is not None:
            cap.release()


PAGE = b'''<!doctype html><meta charset="utf-8"><title>Camera kickoff check</title>
<style>body{font:18px system-ui;max-width:850px;margin:40px auto;padding:20px}button{padding:12px;margin:5px}pre{background:#eef2f4;padding:20px;white-space:pre-wrap}</style>
<h1>Camera shutter check</h1><p>LIVE brightness only. No images stored or transmitted. This is a test dashboard, not production vision.</p>
<p>Set each physical condition, then click its button. Hold it for 5 seconds. Capture stops after each measurement.</p>
<button onclick="send('normal')">Measure normal desk light</button>
<button onclick="send('dark')">Measure darkest room, shutter OPEN</button>
<button onclick="send('hand')">Measure hand over lens</button>
<button onclick="send('shutter')">Measure shutter CLOSED</button>
<p>Once a threshold appears: open shutter, click Camera on, then close shutter. Verify capture_open becomes false after about 3 seconds and the camera LED goes out. Reopening alone must not restart capture.</p>
<button onclick="send('on')">Camera on</button><button onclick="send('off')">Camera off</button>
<pre id="status">Loading...</pre><script>
async function send(action){let r=await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});if(!r.ok)alert(await r.text());}
setInterval(async()=>{try{statusBox.textContent=JSON.stringify(await(await fetch('/state')).json(),null,2)}catch(e){statusBox.textContent=String(e)}},500);
const statusBox=document.getElementById('status');</script>'''


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, data, kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/':
            return self.respond(200, PAGE, 'text/html; charset=utf-8')
        if self.path == '/state':
            return self.respond(200, json.dumps(snapshot()).encode())
        self.respond(404, b'{}')

    def do_POST(self):
        try:
            if self.path != '/control':
                raise ValueError('Unknown endpoint')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 128:
                raise ValueError('Invalid request size')
            action = json.loads(self.rfile.read(size)).get('action')
            if action not in ('normal', 'dark', 'hand', 'shutter', 'on', 'off'):
                raise ValueError('Unknown action')
            if snapshot()['measuring']:
                raise ValueError('Measurement in progress; wait until it finishes')
            if action == 'on' and snapshot()['threshold'] is None:
                raise ValueError('Calibrate normal, dark and shutter conditions first')
            commands.put(action)
            self.respond(202, b'{"queued":true}')
        except (ValueError, AttributeError) as exc:
            self.respond(400, json.dumps({'error':str(exc)}).encode())

    def log_message(self, *args):
        pass


threading.Thread(target=worker, daemon=True).start()
print('Camera check ready on port 8000. Capture is OFF until a measurement is requested.', flush=True)
ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
