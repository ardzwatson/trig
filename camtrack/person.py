"""Person detection (YOLOv8n ONNX via onnxruntime) and torso appearance matching."""
import os
import cv2
import numpy as np

SIZE = 640


class PersonDetector:
    def __init__(self, path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name

    def __call__(self, frame, conf=0.45):
        """Return list of (x, y, w, h, score) pixel boxes of people."""
        H, W = frame.shape[:2]
        scale = SIZE / max(H, W)
        nh, nw = int(round(H * scale)), int(round(W * scale))
        canvas = np.full((SIZE, SIZE, 3), 114, np.uint8)
        canvas[:nh, :nw] = cv2.resize(frame, (nw, nh))
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self.sess.run(None, {self.inp: blob})[0]
        return decode(out, conf, scale, W, H)


def decode(out, conf, scale, W, H):
    """YOLOv8 output (1, 84, N): cx, cy, w, h, then 80 class scores; class 0 = person."""
    p = out[0].T
    scores = p[:, 4]                      # person is class 0
    keep = scores >= conf
    p, scores = p[keep], scores[keep]
    if not len(p):
        return []
    boxes = []
    for (cx, cy, w, h) in p[:, :4]:
        x, y = (cx - w / 2) / scale, (cy - h / 2) / scale
        x0, y0 = max(0, x), max(0, y)
        boxes.append([int(x0), int(y0), int(min(W - x0, w / scale)), int(min(H - y0, h / scale))])
    idx = cv2.dnn.NMSBoxes(boxes, scores.tolist(), conf, 0.5)
    return [(*boxes[i], float(scores[i])) for i in np.array(idx).flatten()]


def torso(frame, box):
    """Crop the upper-body band of a person box (where a jacket/top is)."""
    x, y, w, h = box[:4]
    y0, y1 = y + int(h * 0.15), y + int(h * 0.60)
    x0, x1 = x + int(w * 0.10), x + int(w * 0.90)
    return frame[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]


def hist(img):
    """2-D hue/saturation histogram, ignoring dark/grey pixels so background doesn't dominate."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (0, 40, 40), (180, 255, 255))
    if cv2.countNonZero(m) < 20:
        return None
    h = cv2.calcHist([hsv], [0, 1], m, [30, 8], [0, 180, 0, 256])
    cv2.normalize(h, h, 1.0, 0, cv2.NORM_L1)
    return h


def similarity(h1, h2):
    """Histogram intersection, 0..1 (1 = identical colour distribution)."""
    if h1 is None or h2 is None:
        return 0.0
    return float(cv2.compareHist(h1, h2, cv2.HISTCMP_INTERSECT))


class References:
    """Reference photos of the garment, stored on disk, merged into one histogram."""
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.reload()

    def reload(self):
        hs = []
        for fn in sorted(os.listdir(self.folder)):
            img = cv2.imread(os.path.join(self.folder, fn))
            if img is None:
                continue
            H, W = img.shape[:2]
            hh = hist(img[int(H * .15):int(H * .85), int(W * .15):int(W * .85)])  # centre crop
            if hh is not None:
                hs.append(hh)
        self.count = len(hs)
        self.hist = None
        if hs:
            self.hist = np.mean(hs, axis=0).astype(np.float32)
            cv2.normalize(self.hist, self.hist, 1.0, 0, cv2.NORM_L1)

    def add(self, data):
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("not an image")
        n = len(os.listdir(self.folder))
        if n >= 10:
            raise ValueError("max 10 reference images")
        cv2.imwrite(os.path.join(self.folder, f"ref{n:02d}.jpg"), img)
        self.reload()

    def clear(self):
        for fn in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, fn))
        self.reload()
