"""Tri-state pixel diff between two consecutive frames.

Given the previous and current frame, classify every pixel as STABLE (unchanged),
APPEARED (empty before, occupied now) or DISAPPEARED (occupied before, empty now),
with a fourth CHANGED bucket for pixels that stayed occupied but changed colour.

This is a deliberately cheap, image-level stage the downstream reasoner can hypothesise
over before any entity binding: "what stayed the same" is the layer-0 evidence, while
appeared / disappeared regions feed the reveal-vs-occlusion and spawn-vs-removal
questions. Nothing is asserted as cause here -- each region carries competing hypotheses
with rough confidences, exactly like the tracker.

Imaging lives in Python (numpy + OpenCV), never in the browser.
"""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image
import cv2


def _decode(data: object) -> np.ndarray:
    if not isinstance(data, str) or not data:
        raise ValueError("Each frame must be a base64 PNG string.")
    raw = base64.b64decode(data, validate=False)
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.asarray(image, dtype=np.uint8)


def _background(prev: np.ndarray, cur: np.ndarray) -> np.ndarray:
    # The "empty" colour is the single most common pixel across both frames; a HUD or
    # world backdrop dominates the pixel count, so this is a robust, assumption-light
    # notion of emptiness without needing an external background plate.
    rows = np.concatenate([prev.reshape(-1, 3), cur.reshape(-1, 3)], axis=0)
    colors, counts = np.unique(rows, axis=0, return_counts=True)
    return colors[int(np.argmax(counts))].astype(np.int16)


def _regions(mask: np.ndarray, min_area: int, limit: int = 40) -> list[dict]:
    count, _labels, stats, _cent = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, count):  # 0 is the background label
        x, y, w, h, area = (int(v) for v in stats[i])
        if area >= min_area:
            out.append({"bounds": [x, y, w, h], "area": area})
    out.sort(key=lambda r: -r["area"])
    return out[:limit]


def _hypotheses(kind: str) -> list[dict]:
    # Image-level regions are ambiguous by nature; offer the competing readings ranked,
    # never a single asserted cause (correlation is not physical cause).
    if kind == "appeared":
        return [{"label": "reveal: previously-occluded content now visible", "confidence": 0.5},
                {"label": "spawn: new object created", "confidence": 0.5}]
    if kind == "disappeared":
        return [{"label": "occlusion: content now hidden behind something", "confidence": 0.5},
                {"label": "removal: object destroyed / left the frame", "confidence": 0.5}]
    return [{"label": "recolor: same content changed colour in place", "confidence": 0.5},
            {"label": "overlap: different content now occupies the pixels", "confidence": 0.5}]


def diff_frames(current: object, previous: object, tolerance: object = 40) -> dict:
    cur = _decode(current)
    prev = _decode(previous)
    if prev.shape != cur.shape:
        prev = cv2.resize(prev, (cur.shape[1], cur.shape[0]), interpolation=cv2.INTER_NEAREST)
    if type(tolerance) not in (int, float) or tolerance < 0:
        raise ValueError("tolerance must be a non-negative number.")
    tol2 = float(tolerance) ** 2

    bg = _background(prev, cur)
    prev_i = prev.astype(np.int16)
    cur_i = cur.astype(np.int16)
    prev_fg = np.sum((prev_i - bg) ** 2, axis=2) > tol2
    cur_fg = np.sum((cur_i - bg) ** 2, axis=2) > tol2
    same_color = np.sum((prev_i - cur_i) ** 2, axis=2) <= tol2

    appeared = (~prev_fg) & cur_fg
    disappeared = prev_fg & (~cur_fg)
    changed = prev_fg & cur_fg & (~same_color)
    stable = ~(appeared | disappeared | changed)

    # Build a readable tri-state image: shape detail is preserved via luminance so the
    # developer can still see WHAT changed, tinted by category.
    cur_lum = cur_i.mean(axis=2)
    prev_lum = prev_i.mean(axis=2)
    out = np.zeros_like(cur, dtype=np.uint8)
    grey = np.clip(cur_lum * 0.5, 0, 255).astype(np.uint8)
    out[stable] = np.stack([grey, grey, grey], axis=2)[stable]
    ca = np.clip(cur_lum / 255.0, 0.25, 1.0)
    cp = np.clip(prev_lum / 255.0, 0.25, 1.0)
    out[appeared] = np.stack([(40 * ca), (230 * ca), (120 * ca)], axis=2).astype(np.uint8)[appeared]
    out[disappeared] = np.stack([(235 * cp), (70 * cp), (70 * cp)], axis=2).astype(np.uint8)[disappeared]
    out[changed] = np.stack([(240 * ca), (210 * ca), (70 * ca)], axis=2).astype(np.uint8)[changed]

    ok, buffer = cv2.imencode(".png", cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("Could not encode the diff image.")
    image_b64 = base64.b64encode(buffer.tobytes()).decode("ascii")

    total = int(cur.shape[0] * cur.shape[1])
    min_area = max(6, total // 20000)  # ignore single-pixel noise; scale-relative
    counts = {
        "stable": int(stable.sum()), "appeared": int(appeared.sum()),
        "disappeared": int(disappeared.sum()), "changed": int(changed.sum()), "total": total,
    }
    regions = {
        "appeared": [{**r, "hypotheses": _hypotheses("appeared")} for r in _regions(appeared, min_area)],
        "disappeared": [{**r, "hypotheses": _hypotheses("disappeared")} for r in _regions(disappeared, min_area)],
        "changed": [{**r, "hypotheses": _hypotheses("changed")} for r in _regions(changed, min_area)],
    }
    return {
        "width": int(cur.shape[1]), "height": int(cur.shape[0]),
        "background": [int(v) for v in bg], "tolerance": float(tolerance),
        "counts": counts, "regions": regions,
        "image": "data:image/png;base64," + image_b64,
    }
