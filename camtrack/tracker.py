import os, threading, time, json, collections
import cv2
from . import detector, notify, person
from .ezviz_cloud import EzvizSource


class Tracker:
    def __init__(self, cfg, events_dir):
        self.cfg, self.events_dir = cfg, events_dir
        os.makedirs(events_dir, exist_ok=True)
        self.lock = threading.Lock()
        self.latest = None            # newest raw frame (BGR)
        self.jpeg = None              # newest annotated JPEG
        self.status = {"connected": False, "match": False, "area_pct": 0.0, "fps": 0.0, "last_error": ""}
        self.events = collections.deque(maxlen=50)
        self._load_events()
        self.hits, self.last_alert = 0, 0.0
        self.model_path = os.path.join(os.path.dirname(events_dir), "models", "person.onnx")
        self.persons = person.PersonDetector(self.model_path) if os.path.exists(self.model_path) else None
        self.refs = person.References(os.path.join(os.path.dirname(events_dir), "references"))
        self.status["person_model"] = self.persons is not None
        self._src = None
        self._ez, self.still = None, False
        self.token_path = os.environ.get("EZVIZ_TOKEN_PATH", os.path.join(os.path.dirname(events_dir), "ezviz_token.json"))
        threading.Thread(target=self._grab, daemon=True).start()
        threading.Thread(target=self._process, daemon=True).start()

    def _load_events(self):
        p = os.path.join(self.events_dir, "events.jsonl")
        if os.path.exists(p):
            for line in open(p).read().splitlines()[-50:]:
                self.events.append(json.loads(line))

    # --- capture: always keep only the newest frame so we never lag behind the camera
    def _grab(self):
        cap, src = None, None
        while True:
            conf = self.cfg.snapshot()
            want = conf["source"]
            if want.startswith("ezviz://"):      # cloud mode: alarm pictures, not a live stream
                serial = want[8:]
                if self._ez is None or self._ez.serial != serial:
                    self._ez = EzvizSource(serial, self.token_path)
                for fr in self._ez.step(conf["ezviz_poll_s"]):
                    with self.lock:
                        self.latest, self.still = fr, True
                self.status.update(connected=self._ez.ok, last_error=self._ez.error)
                time.sleep(1); continue
            if want != src or cap is None:
                if cap: cap.release()
                src, cap = want, None
                if not want:
                    self.status.update(connected=False, last_error="No camera source set")
                    time.sleep(1); continue
                os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
                cap = cv2.VideoCapture(want, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    self.status.update(connected=False, last_error="Cannot open stream (check IP, RTSP enabled, verification code)")
                    cap = None; time.sleep(3); continue
            ok, frame = cap.read()
            if not ok:
                # file sources: loop; live sources: reconnect
                if os.path.exists(src):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0); time.sleep(0.03); continue
                self.status.update(connected=False, last_error="Stream dropped, reconnecting")
                cap.release(); cap = None; time.sleep(2); continue
            with self.lock:
                self.latest = frame
            self.status.update(connected=True, last_error="")
            if os.path.exists(src):
                time.sleep(1 / 25)

    # --- detection loop
    def _process(self):
        t_prev = time.time()
        while True:
            c = self.cfg.snapshot()
            time.sleep(1.0 / max(1, c["process_fps"]))
            with self.lock:
                frame = None if self.latest is None else self.latest.copy()
            if frame is None:
                continue
            cloud = c["source"].startswith("ezviz://")
            if cloud:                             # stills arrive rarely: process each exactly once
                if not self.still:
                    continue
                self.still = False
            h = frame.shape[0]
            if h > 540:  # detect on a downscaled copy; plenty for colour blobs
                s = 540 / h
                frame = cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            mask, boxes, best = detector.detect(frame, c)
            if c["require_person"] and (self.persons or self.refs.count):
                boxes, best = self._person_match(frame, mask, c)
            match = bool(boxes) and c["enabled"]
            self.hits = (c["confirm_frames"] if match else 0) if cloud else (self.hits + 1 if match else 0)
            now = time.time()
            self.status.update(match=match, area_pct=round(best, 2), fps=round(1 / max(now - t_prev, 1e-3), 1))
            t_prev = now

            vis = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) if c["view"] == "mask" else frame.copy()
            self._draw(vis, boxes, c)
            ok, buf = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                self.jpeg = buf.tobytes()

            if self.hits >= c["confirm_frames"] and now - self.last_alert >= c["cooldown_s"]:
                self.last_alert = now
                self._alert(frame, boxes, best, c)

    def _person_match(self, frame, mask, c):
        """Keep only people whose torso matches the reference photos (or the picked colour)."""
        if not self.persons:
            self.status["last_error"] = "require_person is on but models/person.onnx is missing"
            return [], 0.0
        hits, best = [], 0.0
        for b in self.persons(frame, c["person_conf"]):
            x, y, w, h = b[:4]
            if self.refs.count:
                score = person.similarity(person.hist(person.torso(frame, b)), self.refs.hist)
                ok, pct = score >= c["ref_threshold"], score * 100
            else:
                t = person.torso(mask[:, :, None], b)
                pct = 100.0 * cv2.countNonZero(t) / max(1, t.size)
                ok = pct >= c["torso_cover_pct"]
            if ok:
                hits.append((x, y, w, h)); best = max(best, pct)
        return hits, best

    def _draw(self, vis, boxes, c):
        H, W = vis.shape[:2]
        if c.get("roi"):
            x, y, w, h = c["roi"]
            cv2.rectangle(vis, (int(x*W), int(y*H)), (int((x+w)*W), int((y+h)*H)), (255, 200, 0), 1)
        for (x, y, w, h) in boxes:
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(vis, c["label"], (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

    def _alert(self, frame, boxes, best, c):
        snap = frame.copy()
        self._draw(snap, boxes, c)
        ok, buf = cv2.imencode(".jpg", snap, [cv2.IMWRITE_JPEG_QUALITY, 85])
        jpeg = buf.tobytes()
        ts = time.strftime("%Y%m%d-%H%M%S")
        fn = f"{ts}.jpg"
        with open(os.path.join(self.events_dir, fn), "wb") as f:
            f.write(jpeg)
        sent, info = notify.send(c, f"{c['label']} spotted", time.strftime("%H:%M:%S") + f" – {best:.1f}% of frame", jpeg)
        ev = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "file": fn, "area_pct": round(best, 2), "notified": sent, "info": info}
        self.events.append(ev)
        with open(os.path.join(self.events_dir, "events.jsonl"), "a") as f:
            f.write(json.dumps(ev) + "\n")

    def frame_copy(self):
        with self.lock:
            return None if self.latest is None else self.latest.copy()
