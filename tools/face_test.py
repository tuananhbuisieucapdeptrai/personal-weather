"""M2.1 App Lab entry point: observable LED/buzzer sequence, no camera access.

Copy beside bridge_io.py/contracts.py as main.py, or use build_face_app.ps1.
Acknowledgments prove receipt only. Minh must verify pixels and sound physically.
"""
import time
import threading
import bridge_io

STEPS = [
 ('Smile', {'face':'smile'}, 4), ('Sun / warm', {'face':'sun'}, 4),
 ('Snowflake / cold', {'face':'snow'}, 4),
 ('Blink layer PLUS', {'face':'suggest_layer_on'}, 5),
 ('Blink layer MINUS', {'face':'suggest_layer_off'}, 5),
 ('Feedback LEFT', {'face':'feedback','pos':-1}, 4),
 ('Feedback DOT', {'face':'feedback','pos':0}, 4),
 ('Feedback RIGHT', {'face':'feedback','pos':1}, 4),
 ('DO text', {'face':'text','text':'DO'}, 4),
 ('NO text', {'face':'text','text':'NO'}, 4),
 ('LATER scroll', {'face':'text','text':'LATER'}, 10),
 ('Check mark', {'face':'check'}, 4),
 ('Eye-off for 3 seconds THEN bottom-right dot', {'face':'eye_off'}, 7),
 ('Blank', {'face':'off'}, 4),
 ('Chirp', {'beep':'chirp'}, 3), ('Chime', {'beep':'chime'}, 3),
 ('Low beep', {'beep':'low'}, 3),
 ('Smile; turn and press knob to verify responsiveness', {'face':'smile'}, 12)
]
lock = threading.Lock()
readings = 0
knob_events = 0
last_env = None
hardware = None
last_health = None
ack = None


def on_hardware(thermo, knob, buzzer):
    global hardware, last_health
    with lock:
        hardware = (bool(thermo), bool(knob), bool(buzzer))
        last_health = time.monotonic()


def on_ack(count):
    global ack
    with lock:
        ack = int(count)


def receive(msg):
    global readings, knob_events, last_env
    with lock:
        if 't' in msg:
            readings += 1
            last_env = time.monotonic()
        if 'knob' in msg:
            knob_events += 1


def run():
    from arduino.app_utils import App
    bridge_io.start(receive, extra_handlers={
        'hw_status': on_hardware, 'face_ack': on_ack,
        'knob_raw': lambda *args: None, 'knob_config': lambda *args: None})
    print('FACE CHECK diagnostics v4. Watch the physical UNO Q matrix; this app has NO web server.', flush=True)
    def probe():
        from arduino.app_utils import Bridge
        while True:
            try:
                stage = Bridge.call('face_check_stage', timeout=2)
                print(f'SKETCH startup_stage={stage}', flush=True)
            except Exception as exc:
                print(f'SKETCH probe failed: {type(exc).__name__}: {exc}', flush=True)
            time.sleep(5)
    threading.Thread(target=probe, daemon=True).start()
    index = 0
    deadline = time.monotonic() + 3
    finished = False
    started = False
    next_health_report = time.monotonic() + 5
    def loop():
        nonlocal index, deadline, finished, next_health_report, started
        now = time.monotonic()
        if now >= next_health_report:
            with lock:
                health_age = None if last_health is None else round(now-last_health, 1)
                print(f'HEALTH thermo/knob/buzzer={hardware}; beacon_age_s={health_age}; '
                      f'face_ack={ack}; env_messages={readings}; knob_events={knob_events}; '
                      f'invalid_messages={bridge_io.dropped}', flush=True)
            next_health_report = now + 5
        if not started:
            with lock:
                ready = (hardware == (True, True, True) and last_health is not None
                         and now-last_health < 5 and last_env is not None and now-last_env < 5)
            if not ready:
                time.sleep(.02)
                return
            started = True
            deadline = now + 3
            print('All modules found and live environment received; starting sequence in 3 seconds.', flush=True)
        if now >= deadline and not finished:
            if index == len(STEPS):
                finished = True
                with lock:
                    print(f'Sequence finished: {readings} environment messages, {knob_events} knob events.', flush=True)
                print('Manual acceptance required: all icons/text/orientation, blink, eye-off transition and 3 sounds. No automatic visual PASS.', flush=True)
            else:
                label, msg, seconds = STEPS[index]
                bridge_io.send(msg)
                print(f'{index+1}/{len(STEPS)} WATCH: {label} ({seconds}s)', flush=True)
                with lock:
                    if index and (last_env is None or now-last_env > 5):
                        print('WARNING: environment readings stale during face sequence', flush=True)
                index += 1
                deadline = now + seconds
        time.sleep(.02)
    App.run(user_loop=loop)


if __name__ == '__main__':
    run()
