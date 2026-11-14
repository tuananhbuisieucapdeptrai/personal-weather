"""The device application: one tick per second.  Owner: Tuan Anh (T2.4).

No side effects on import and no direct hardware access: it gets
  bridge  (bridge_io module or mocks.MockBridge)   start(on_message), send(msg)
  vision  (vision module or mocks.MockVision)      latest()   (start/stop via ControlState)
  control (api.ControlState)                       profile, mode, camera, clothing override
  clock   (time.time on the board; simulated time with mocks)
so the same code runs on the UNO Q and on a laptop. main.py builds it.

Per tick:
  1. drain the inbox (Bridge callbacks only enqueue): env -> smoothing; knob -> routed to
     whatever is on screen: follow-up question > suggestion > feedback
  2. vision + dashboard -> effective clothing, presence (camera; else recent knob use)
  3. active profile: comfort estimate, follow-up tick, suggestion engine (may offer)
  4. LED face (sent only on change), eye-off on camera off/shutter
  5. one C8 summary per profile -> hub (60 s heartbeat + on change, background thread)
get_state() is the dashboard's GET /state (labelled debug, local only).
"""
from __future__ import annotations

import collections
import json
import os
import queue
import threading

import comfort
import contracts
import evaluation
import sensing
import suggest
import summary

DISPLAY = {"tuananh": "Tuan Anh", "minh": "Minh"}     # local dashboard only, never sent
CLASS_FACE = {comfort.COLD: "snow", comfort.OK: "smile", comfort.WARM: "sun"}
FEEDBACK_IDLE_S = 20          # an unconfirmed feedback turn is abandoned after this
HOLD_AFTER_CONFIRM_S = 2      # keep the check mark visible
EYE_OFF_HOLD_S = 5
PRESENCE_FALLBACK_S = 30 * 60
QUIET_AFTER_OK_S = 5 * 60
REPORT_VALID_S = 10 * 60      # "I'm cold" right now beats the model's prediction for 10 min     # after an "OK" vote, no suggestion pops up and steals the knob
SUMMARY_HEARTBEAT_S = 60


class Profile:
    def __init__(self, name: str):
        self.name = name
        self.model = comfort.PersonalModel()
        self.engine = suggest.SuggestionEngine()
        self.experience = suggest.FixExperience()
        self.follow_up: suggest.FollowUp | None = None
        self.last_outcome: dict | None = None
        self.quiet_until = 0.0
        self.reported: tuple[int, float] | None = None     # (vote, at) from the knob
        self.decision: dict | None = None
        self.estimate: dict | None = None

    def to_dict(self):
        return {"model": self.model.to_dict(), "engine": self.engine.to_dict(),
                "experience": self.experience.to_dict(), "last_outcome": self.last_outcome}

    @classmethod
    def from_dict(cls, name, d):
        p = cls(name)
        p.model = comfort.PersonalModel.from_dict(d.get("model", {}))
        p.engine = suggest.SuggestionEngine.from_dict(d.get("engine", {}))
        p.experience = suggest.FixExperience.from_dict(d.get("experience", {}))
        p.last_outcome = d.get("last_outcome")
        return p


class SummarySender:
    """Posts summaries on a background thread so a slow hub never blocks the loop."""

    def __init__(self, post=summary.post_summary, url_fn=summary.hub_url):
        self._post, self._url_fn = post, url_fn
        self._q: queue.Queue = queue.Queue()
        self.status: dict[str, dict] = {}        # pid -> last attempt
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, msg: dict, at: float):
        self._q.put((msg, at))

    def _run(self):
        while True:
            msg, at = self._q.get()
            url, where = self._url_fn()
            if not url:
                self.status[msg["pid"]] = {"at": at, "result": "hub URL not configured", "msg": msg}
                continue
            try:
                code = self._post(msg, url)
                self.status[msg["pid"]] = {"at": at, "result": f"HTTP {code}", "msg": msg, "hub": url}
            except OSError as e:
                self.status[msg["pid"]] = {"at": at, "result": f"unreachable: {e}", "msg": msg, "hub": url}


class App:
    def __init__(self, bridge, vision, control, clock, state_dir: str, inputs: str = "live",
                 accelerated: bool = False, sender=None):
        self.bridge, self.vision, self.control, self.clock = bridge, vision, control, clock
        self.inputs, self.accelerated = inputs, accelerated
        self.labels = (["MOCK INPUT"] if inputs == "mock" else ["LIVE"]) + (["ACCELERATED"] if accelerated else [])
        # Demo speed (labelled ACCELERATED): anti-nagging timers shortened so the loop can be
        # shown repeatedly. Office values: 15 min between suggestions, 5 min quiet, 4 h block.
        self.quiet_after_ok_s = 20 if accelerated else QUIET_AFTER_OK_S
        if accelerated:
            suggest.MIN_GAP_S = 60
            suggest.NOT_POSSIBLE_HOLD_S = 120
        self.state_dir = state_dir
        self._profiles_path = os.path.join(state_dir, "profiles.json")
        self.profiles = self._load_profiles()
        self.log = evaluation.FeedbackLog(os.path.join(state_dir, "feedback_log.jsonl"))
        self.env = sensing.EnvFilter()
        self.inbox: queue.Queue = queue.Queue()
        self.sender = sender if sender is not None else SummarySender()
        self.events: collections.deque = collections.deque(maxlen=40)
        self._lock = threading.RLock()
        # interaction state
        self.response_picker: suggest.ResponsePicker | None = None
        self.feedback_picker: suggest.FeedbackPicker | None = None
        self.feedback_since = 0.0
        self.hold_until = 0.0
        self.last_face: dict | None = None
        self.last_knob_at: float | None = None
        self.camera_prev: str | None = None
        self.vision_now: dict = {"present": None, "clothing": "uncertain", "conf": None, "camera": "off"}
        self.presence = (False, "none")
        self.clothing = ("uncertain", "camera")
        self.active_name = control.profile
        self._sent: dict[str, tuple[dict, float]] = {}   # pid -> (summary, sent_at)

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        self.bridge.start(self.inbox.put)     # callback only enqueues (Bridge thread)
        self._event("started", inputs=self.inputs, labels=self.labels)

    def tick(self) -> None:
        with self._lock:
            now = self.clock()
            self._switch_profile_if_needed(now)
            while True:
                try:
                    msg = self.inbox.get_nowait()
                except queue.Empty:
                    break
                self._handle(msg, now)
            self._update(now)

    # ---------------------------------------------------------------- helpers
    @property
    def active(self) -> Profile:
        return self.profiles[self.active_name]

    def _event(self, kind, **kw):
        self.events.append({"at": self.clock(), "event": kind, **kw})

    def _send(self, msgs):
        for m in msgs:
            self.bridge.send(m)
            if "face" in m:
                self.last_face = m

    def _set_face(self, msg):
        if msg != self.last_face:
            self._send([msg])

    def _load_profiles(self):
        try:
            with open(self._profiles_path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        return {n: Profile.from_dict(n, raw.get(n, {})) for n in contracts.PROFILES}

    def _save(self):
        os.makedirs(self.state_dir, exist_ok=True)
        tmp = self._profiles_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({n: p.to_dict() for n, p in self.profiles.items()}, f)
        os.replace(tmp, self._profiles_path)

    def _env_ok(self, now):
        r = self.env.reading(now)
        return r if r["t"] is not None and not r["stale"] else None

    # ---------------------------------------------------------------- input
    def _switch_profile_if_needed(self, now):
        if self.control.profile != self.active_name:
            self._event("profile_switch", frm=self.active_name, to=self.control.profile)
            self.active_name = self.control.profile
            self.feedback_picker = None
            self.response_picker = None if self.active.engine.active is None else suggest.ResponsePicker()

    def _handle(self, msg, now):
        if "t" in msg:
            self.env.update(msg, now)
            return
        self.last_knob_at = now
        p = self.active
        fu = p.follow_up if p.follow_up and p.follow_up.state == "asking" else None
        if fu:
            kind, picker = "follow_up", fu.picker
        elif p.engine.active is not None:
            self.response_picker = self.response_picker or suggest.ResponsePicker()
            kind, picker = "suggestion", self.response_picker
        else:
            if self.feedback_picker is None:
                self.feedback_picker, self.feedback_since = suggest.FeedbackPicker(), now
                # Ordinary "how do you feel" vote: the knob rests on OK, so a single press
                # without turning means OK (people press once). Bump protection stays for
                # suggestion answers and the "did it help?" follow-up.
                self.feedback_picker.previewed = True
            kind, picker = "feedback", self.feedback_picker
        if msg["knob"] == "turn":
            self._send(picker.on_turn(msg["pos"]))
            if kind == "feedback":
                self.feedback_since = now
            return
        answer, msgs = picker.on_press()
        self._send(msgs)
        if answer is None:
            return
        self.hold_until = now + HOLD_AFTER_CONFIRM_S
        if kind == "feedback":
            self.feedback_picker = None
            self._record_feedback(p, answer, now)
        elif kind == "suggestion":
            self.response_picker = None
            rec = p.engine.respond(now, answer)
            self._event("suggestion_response", profile=p.name, response=answer, fix=rec["fix"],
                        energy_role=rec["energy_role"])
            if rec["follow_up"]:
                p.follow_up = suggest.FollowUp(rec, self.clothing[0], now, accelerated=self.accelerated)
            self._save()
        else:
            env = self._env_ok(now)
            if env is None:
                self._event("follow_up_vote_ignored", reason="no fresh temperature")
                return
            out = fu.complete(now, answer, env["t"], env["rh"], self.clothing[0], p.model, p.experience)
            p.reported = (answer, now)
            self.log.append(p.name, out["comfort_record"], "follow_up", now, self.labels, self.clothing[0])
            self._finish_follow_up(p, out)

    def _record_feedback(self, p, vote, now):
        env = self._env_ok(now)
        if env is None:
            self._event("feedback_ignored", profile=p.name, reason="no fresh temperature")
            return
        rec = p.model.observe(vote, comfort.baseline_pmv(env["t"], env["rh"], self.clothing[0]))
        self.log.append(p.name, rec, "feedback", now, self.labels, self.clothing[0])
        p.reported = (vote, now)
        if vote == comfort.OK:
            p.quiet_until = now + self.quiet_after_ok_s
        self._event("feedback", profile=p.name, vote=vote, offset=rec["offset_after"])
        self._save()

    def _finish_follow_up(self, p, out):
        p.last_outcome = {k: v for k, v in out.items() if k != "comfort_record"}
        p.follow_up = None
        self._event("follow_up_done", profile=p.name, result=out["result"], action=out["action_check"])
        self._save()

    # ---------------------------------------------------------------- per tick
    def _update(self, now):
        vis = self.vision.latest()
        self.vision_now = vis
        self.clothing = self.control.effective_clothing(vis["clothing"])
        if vis["present"] is not None:
            self.presence = (vis["present"], "camera")
        else:
            recent = self.last_knob_at is not None and now - self.last_knob_at < PRESENCE_FALLBACK_S
            self.presence = (recent, "knob_activity")
        self._camera_transition(vis["camera"], now)

        if self.feedback_picker and now - self.feedback_since > FEEDBACK_IDLE_S:
            self.feedback_picker = None
            self._event("feedback_abandoned")

        env = self.env.reading(now)
        fresh = env["t"] is not None and not env["stale"]
        for p in self.profiles.values():
            is_active = p.name == self.active_name
            if p.engine.expire(now):
                if is_active:
                    self.response_picker = None
                self._event("suggestion_no_response", profile=p.name)
            if is_active and p.engine.active is not None and p.follow_up is None:
                self._accept_by_action(p, now)
            if p.follow_up and p.follow_up.state != "done":
                msgs = p.follow_up.tick(now, *self.clothing) if is_active else []
                if msgs:
                    self._send(msgs)
                    self._event("follow_up_ask", profile=p.name, action=p.follow_up.action_check)
            if p.follow_up and p.follow_up.state == "done":
                self._finish_follow_up(p, p.follow_up.outcome)
            if not fresh:
                p.estimate, p.decision = None, None
                continue
            clothing = self.clothing[0] if is_active else "uncertain"
            present = self.presence[0] if is_active else False
            p.estimate = comfort.estimate(env["t"], env["rh"], clothing, p.model)
            reported = (p.reported[0] if p.reported and now - p.reported[1] < REPORT_VALID_S
                        and is_active else None)
            if reported is not None:              # interfaces.md: a fresh knob report overrides
                p.estimate["model_class"] = p.estimate["personal_class"]
                p.estimate["personal_class"] = reported
                p.estimate["from_report"] = True
            p.decision = p.engine.evaluate(
                now, env["t"], env["rh"], clothing, p.model, self.control.mode, present=present,
                follow_up_pending=bool(p.follow_up), env_stale=False, reported_class=reported)
            busy = (self.feedback_picker is not None or now < self.hold_until or now < p.quiet_until
                    or (p.follow_up is not None and p.follow_up.state == "asking"))
            if is_active and p.decision["offer"] and not busy:
                self._send(p.engine.offer(now, p.decision["offer"]))
                self.response_picker = suggest.ResponsePicker()
                self._event("suggestion_offered", profile=p.name, fix=p.decision["offer"]["fix"],
                            energy_role=p.decision["offer"]["energy_role"])
        self._update_face(now)
        self._summaries(now, fresh)

    def _accept_by_action(self, p, now):
        """Acting counts as answering: while a suggestion is on screen, if the CAMERA sees the
        suggested change (e.g. no layer -> layer; already stable in vision), treat it as "Do it".
        A dashboard setting does not count. The follow-up still asks; silence stays 'unknown'."""
        fix = suggest.FIXES[p.engine.active["fix"]]
        if self.clothing != (fix["to"], "camera"):
            return
        rec = p.engine.respond(now, suggest.DO_IT)
        self.response_picker = None
        p.follow_up = suggest.FollowUp(rec, fix["from"], now, accelerated=self.accelerated)
        self.hold_until = now + HOLD_AFTER_CONFIRM_S
        self._send([{"face": "check"}, {"beep": "chirp"}])
        self._event("suggestion_response", profile=p.name, response=suggest.DO_IT, fix=rec["fix"],
                    energy_role=rec["energy_role"], by="camera")
        self._save()

    def _camera_transition(self, camera, now):
        if camera != self.camera_prev:
            if camera in ("off", "shutter") and self.camera_prev is not None:
                self._send([{"face": "eye_off"}, {"beep": "low"}])
                self.hold_until = now + EYE_OFF_HOLD_S
            self._event("camera", status=camera)
            self.camera_prev = camera

    def _update_face(self, now):
        p = self.active
        if now < self.hold_until or self.feedback_picker is not None or p.engine.active is not None:
            return
        if p.follow_up is not None and p.follow_up.state == "asking":
            return
        if not self.presence[0]:
            self._set_face({"face": "off"})
        elif p.estimate is not None:
            self._set_face({"face": CLASS_FACE[p.estimate["personal_class"]]})

    def _summaries(self, now, fresh):
        if not fresh:
            return
        pids = self.control.snapshot()["pids"]
        for name, p in self.profiles.items():
            if p.estimate is None or p.decision is None:
                continue
            msg = {"pid": pids[name], "present": bool(p.decision is not None and name == self.active_name
                                                      and self.presence[0]),
                   "mode": self.control.mode, "band_now": p.estimate["band"],
                   "state": p.estimate["personal_class"], "unresolved": p.decision["unresolved"]}
            if p.decision["band_with_fix"] is not None:
                msg["band_with_fix"] = p.decision["band_with_fix"]
            contracts.check_summary(msg)
            last = self._sent.get(name)
            if last is None or last[0] != msg or now - last[1] >= SUMMARY_HEARTBEAT_S:
                self._sent[name] = (msg, now)
                self.sender.send(msg, now)

    # ---------------------------------------------------------------- dashboard
    def get_state(self) -> dict:
        with self._lock:
            now = self.clock()
            ctl = self.control.snapshot()
            people = {}
            for name, p in self.profiles.items():
                fu = p.follow_up
                people[name] = {
                    "display": DISPLAY.get(name, name), "active": name == self.active_name,
                    "pid": ctl["pids"][name], "estimate": p.estimate, "decision": p.decision,
                    "suggestion_on_screen": p.engine.active,
                    "follow_up": None if fu is None else {
                        "state": fu.state, "fix": fu.fix, "due_in_s": round(fu.due_in(now), 1),
                        "action_check": fu.action_check, "labels": fu.labels},
                    "last_follow_up": p.last_outcome,
                    "experience": {f: {"text": p.experience.describe(f, DISPLAY.get(name, name)),
                                       **p.experience.estimate(f)} for f in suggest.FIXES},
                    "evaluation": self.log.report(name),
                    "summary_sent": self._sent.get(name, (None,))[0],
                }
            status = getattr(self.sender, "status", {})
            return {
                "debug": True, "inputs": self.inputs, "labels": self.labels, "time": now,
                "env": self.env.reading(now), "vision": self.vision_now,
                "vision_diag": (self.vision.diagnostics() if hasattr(self.vision, "diagnostics") else None),
                "presence": {"present": self.presence[0], "source": self.presence[1]},
                "clothing": {"value": self.clothing[0], "source": self.clothing[1],
                             "label": "CLOTHING: SET MANUALLY" if self.clothing[1] == "manual" else None},
                "control": ctl, "face": self.last_face,
                "interaction": ("follow_up" if self.active.follow_up and self.active.follow_up.state == "asking"
                                else "suggestion" if self.active.engine.active
                                else "feedback" if self.feedback_picker else "idle"),
                "people": people,
                "assumptions": comfort.ASSUMPTIONS,
                "hub": {"url": summary.hub_url()[0], "last_results": {pid: {k: v for k, v in s.items() if k != "msg"}
                                                                       for pid, s in status.items()}},
                "privacy_receipt": {
                    "sent": [m for m, _ in self._sent.values()],
                    "network_metadata": "the device's local network address is visible to the hub",
                    "stored_on_device": ["feedback log (state/feedback_log.jsonl)",
                                         "model values, fix experience (state/profiles.json)",
                                         "pseudonyms (state/pids.json)"],
                    "images": f"processed in memory, never stored or sent; camera status: {self.vision_now['camera']}",
                    "training_images": "collected only in a separate, consented session; deleted after the event",
                },
                "events": list(self.events)[-20:],
            }
