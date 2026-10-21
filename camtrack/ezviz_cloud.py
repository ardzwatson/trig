"""EZVIZ cloud source: polls the camera's alarm list (via the unofficial pyezviz API) and
yields the alarm pictures as frames. Credentials come from env vars, never the UI/config:
  EZVIZ_ACCOUNT, EZVIZ_PASSWORD, EZVIZ_URL (region API host, default apiieu.ezvizlife.com)
A login token (incl. MFA result) is cached in <data dir>/ezviz_token.json."""
import json, os, time
import numpy as np
import cv2
import requests


class EzvizSource:
    def __init__(self, serial, token_path):
        self.serial, self.token_path = serial, token_path
        self.client, self.seen, self.seeded = None, set(), False
        self.last_poll, self.ok, self.error = 0.0, False, ""

    def _login(self):
        from pyezviz import EzvizClient
        from pyezviz.exceptions import EzvizAuthVerificationCode
        acct, pw = os.environ.get("EZVIZ_ACCOUNT"), os.environ.get("EZVIZ_PASSWORD")
        url = os.environ.get("EZVIZ_URL", "apiieu.ezvizlife.com")
        token = None
        if os.path.exists(self.token_path):
            token = json.load(open(self.token_path))
        if not token and not (acct and pw):
            raise RuntimeError("Set EZVIZ_ACCOUNT and EZVIZ_PASSWORD env vars")
        c = EzvizClient(acct, pw, url, token=token)
        try:
            tok = c.login()
        except EzvizAuthVerificationCode:
            raise RuntimeError("EZVIZ needs an MFA code: run `python3 -m camtrack.ezviz_login` once")
        json.dump(tok, open(self.token_path, "w"))
        self.client = c

    def step(self, poll_s):
        """Return a list of new BGR frames (possibly empty)."""
        now = time.time()
        if now - self.last_poll < poll_s:
            return []
        self.last_poll = now
        try:
            if self.client is None:
                self._login()
            data = self.client.get_alarminfo(self.serial, limit=5)
            alarms = data.get("alarms") or []
            new = [a for a in alarms if (a.get("alarmId") or a.get("picUrl")) not in self.seen]
            self.seen.update(a.get("alarmId") or a.get("picUrl") for a in alarms)
            if not self.seeded:          # first poll: remember history, don't alert on it
                self.seeded = True
                self.ok, self.error = True, ""
                return []
            frames = []
            for a in reversed(new):      # oldest first
                f = self._fetch(a.get("picUrl"))
                if f is not None:
                    frames.append(f)
            self.ok, self.error = True, ""
            return frames
        except Exception as e:
            self.ok, self.error = False, f"EZVIZ cloud: {e}"
            if "session" in str(e).lower() or "401" in str(e):
                self.client = None
            return []

    def _fetch(self, url):
        if not url:
            return None
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("alarm picture not decodable – turn off 'Image Encryption' for this camera in the EZVIZ app")
        return img
