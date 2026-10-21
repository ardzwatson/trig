import argparse, json, os, time, secrets
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import cv2
from .config import Config
from .tracker import Tracker
from . import detector, notify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = TRK = TOKEN = None
EVENTS_DIR = os.path.join(ROOT, "events")


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def _authed(self, q):
        if not TOKEN:
            return True
        if q.get("token", [""])[0] == TOKEN:
            return True
        return f"token={TOKEN}" in self.headers.get("Cookie", "")

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if not self._authed(q):
            return self._send(401, b"token required", "text/plain")
        extra = {"Set-Cookie": f"token={TOKEN}; Path=/; SameSite=Strict"} if TOKEN else None
        if u.path == "/":
            return self._send(200, open(os.path.join(ROOT, "ui", "index.html"), "rb").read(), "text/html", extra)
        if u.path == "/api/state":
            return self._send(200, {"config": CFG.public(), "status": TRK.status, "events": list(TRK.events)[::-1], "refs": TRK.refs.count})
        if u.path == "/stream.mjpg":
            return self._stream()
        if u.path.startswith("/events/"):
            p = os.path.join(EVENTS_DIR, os.path.basename(u.path))
            if os.path.isfile(p):
                return self._send(200, open(p, "rb").read(), "image/jpeg")
        self._send(404, b"not found", "text/plain")

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last = None
        try:
            while True:
                j = TRK.jpeg
                if j is not None and j is not last:
                    last = j
                    self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(j) + j + b"\r\n")
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if not self._authed(q):
            return self._send(401, {"error": "token required"})
        n = int(self.headers.get("Content-Length") or 0)
        self._raw = self.rfile.read(n)
        body = json.loads(self._raw or b"{}") if u.path != "/api/reference" else {}
        if u.path == "/api/config":
            if "***" in str(body.get("source", "")):
                body.pop("source")      # UI echoed the masked URL – keep the stored one
            CFG.update(body)
            return self._send(200, {"config": CFG.public()})
        if u.path == "/api/pick":       # click on video -> learn that colour
            f = TRK.frame_copy()
            if f is None:
                return self._send(409, {"error": "no frame yet"})
            h, s, v = detector.sample_hsv(f, body["x"], body["y"])
            CFG.update({"hue": h, "sat_min": max(40, int(s * 0.5)), "val_min": max(40, int(v * 0.4))})
            return self._send(200, {"config": CFG.public(), "picked": [h, s, v]})
        if u.path == "/api/reference":   # raw image bytes in body
            try:
                TRK.refs.add(self._raw)
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            return self._send(200, {"count": TRK.refs.count})
        if u.path == "/api/reference/clear":
            TRK.refs.clear()
            return self._send(200, {"count": 0})
        if u.path == "/api/test-notify":
            ok, info = notify.send(CFG.snapshot(), "Test from camtrack", "If you can read this, notifications work.")
            return self._send(200, {"ok": ok, "info": info})
        self._send(404, {"error": "not found"})


def main():
    global CFG, TRK, TOKEN
    ap = argparse.ArgumentParser(description="EZVIZ colour tracker")
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach the UI from your phone (set --token too)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--token", default=os.environ.get("CAMTRACK_TOKEN", ""))
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--source", help="override camera source for this run (RTSP URL or video file)")
    a = ap.parse_args()
    TOKEN = a.token
    CFG = Config(a.config)
    if a.source:
        CFG.update({"source": a.source})
    TRK = Tracker(CFG, EVENTS_DIR)
    if a.host != "127.0.0.1" and not TOKEN:
        TOKEN = secrets.token_urlsafe(8)
        print(f"No --token given; generated one: {TOKEN}")
    print(f"UI: http://{a.host if a.host != '0.0.0.0' else 'localhost'}:{a.port}/" + (f"?token={TOKEN}" if TOKEN else ""))
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
