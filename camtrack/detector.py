"""Colour-blob detection in HSV. Pure functions, no I/O."""
import cv2
import numpy as np


def hsv_ranges(cfg):
    """Return list of (lo, hi) uint8 arrays; two ranges when hue wraps around 0/180."""
    h, s, v = cfg["hue"], cfg["sat_min"], cfg["val_min"]
    tol = cfg["hue_tol"]
    lo_h, hi_h = h - tol, h + tol
    hi = 255
    if lo_h < 0:
        return [(np.array([0, s, v]), np.array([hi_h, hi, hi])),
                (np.array([180 + lo_h, s, v]), np.array([180, hi, hi]))]
    if hi_h > 180:
        return [(np.array([lo_h, s, v]), np.array([180, hi, hi])),
                (np.array([0, s, v]), np.array([hi_h - 180, hi, hi]))]
    return [(np.array([lo_h, s, v]), np.array([hi_h, hi, hi]))]


def roi_mask(shape, roi):
    """roi = [x, y, w, h] normalised 0..1, or None."""
    m = np.zeros(shape[:2], np.uint8)
    if not roi:
        m[:] = 255
        return m
    H, W = shape[:2]
    x, y, w, h = roi
    m[int(y * H):int((y + h) * H), int(x * W):int((x + w) * W)] = 255
    return m


def detect(frame, cfg):
    """Return (mask, boxes, best_area_pct). Boxes are pixel (x, y, w, h)."""
    blur = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in hsv_ranges(cfg):
        mask |= cv2.inRange(hsv, lo, hi)
    mask &= roi_mask(frame.shape, cfg.get("roi"))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total = frame.shape[0] * frame.shape[1]
    min_px = cfg["min_area_pct"] / 100.0 * total
    boxes, best = [], 0.0
    for c in cnts:
        a = cv2.contourArea(c)
        if a >= min_px:
            boxes.append(cv2.boundingRect(c))
            best = max(best, a / total * 100)
    return mask, boxes, best


def sample_hsv(frame, nx, ny, r=4):
    """Median HSV around a normalised point – used for click-to-pick."""
    H, W = frame.shape[:2]
    x, y = int(nx * W), int(ny * H)
    patch = frame[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    return [int(v) for v in np.median(hsv, axis=0)]
