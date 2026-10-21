import json, os, threading

DEFAULTS = {
    "source": "",                 # rtsp://admin:<verification code>@<camera-ip>:554/h264/ch1/main/av_stream
    "hue": 0, "hue_tol": 10, "sat_min": 100, "val_min": 60,
    "min_area_pct": 2.0,          # blob must cover this % of the frame
    "confirm_frames": 3,          # consecutive hits before alerting (kills flicker)
    "cooldown_s": 60,             # min seconds between notifications
    "process_fps": 4,
    "roi": None,                  # [x, y, w, h] normalised
    "require_person": False,       # only alert when the colour is on a detected person
    "person_conf": 0.45,
    "ref_threshold": 0.45,        # reference-photo similarity needed (0..1)
    "torso_cover_pct": 25,        # no reference photos: % of torso that must match the colour
    "enabled": True,              # tracking on/off
    "view": "live",               # live | mask
    "ntfy_server": "https://ntfy.sh",
    "ntfy_topic": "",
    "ntfy_priority": 4,
    "label": "Target colour",
}
SECRET_KEYS = ("source",)


class Config:
    def __init__(self, path):
        self.path, self.lock = path, threading.Lock()
        self.data = dict(DEFAULTS)
        if os.path.exists(path):
            with open(path) as f:
                self.data.update(json.load(f))

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    def update(self, patch):
        with self.lock:
            for k, v in patch.items():
                if k in DEFAULTS:
                    self.data[k] = v
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)

    def public(self):
        d = self.snapshot()
        src = d["source"]
        d["source_set"] = bool(src)
        if "@" in src:  # never send the camera password to the browser
            scheme, rest = src.split("://", 1)
            d["source"] = f"{scheme}://***@{rest.split('@', 1)[1]}"
        return d
