"""Learned-scene composition and cached-result serving from crawler artifacts.

The crawler persists per-frame recognition (recognition.json + .pl/.metta sidecars) next to
each frame. This module lets the UI reuse those cached symbolic artifacts instead of
re-running the pipeline, and composes the WHOLE LEARNED SCENE across a recording:
darkness (the detected background) is an OCCLUDER, not an eraser — every foreground
region ever revealed stays in scene memory; pixels never revealed stay dark.

Cache validity: a cached frame result is usable only while it is newer than the source
stamp (source_epoch) and newer than the frame's reserved inputs (image.png, state.json).
The moment sources advance, every cached-derived image is invalid and callers fall back
to the live pipeline (or wait for the crawler to refresh the cache).
"""

import base64
import json
from io import BytesIO
from hashlib import sha256
from pathlib import Path

from frame_pipeline import source_epoch
from pipelines import rules_fingerprint

SEQUENCE_FAMILIES = ("recordings", "curated")

# Engine parameters the crawler runs with; cached results only answer for these.
CRAWLER_DEFAULTS = {"w_engine": "crack", "strong_edge_pct": 1, "old_strong_edge_pct": 25,
                    "upscale": 1, "crack_angle_tol": 40, "tolerance": 24}


def resolve_frame_dir(data_root: Path, sequence_id: str, frame_id: str) -> Path | None:
    """Resolve a sequence/frame to its directory, restricted to the two canonical families."""
    if not isinstance(sequence_id, str) or not isinstance(frame_id, str) or not frame_id.isdigit():
        return None
    if sequence_id.split("/", 1)[0] not in SEQUENCE_FAMILIES:
        return None
    root = data_root.resolve()
    try:
        frame_dir = (root / sequence_id / frame_id).resolve()
    except OSError:
        return None
    if not frame_dir.is_relative_to(root) or not frame_dir.is_dir():
        return None
    return frame_dir


def cached_recognition(frame_dir: Path) -> tuple[dict, float, bool] | None:
    """The frame's cached recognition.json. Caches are NEVER destroyed or refused for age.

    Returns (result, mtime, needs_reprocess). A cache is unusable (None) only when it is
    missing, unreadable, or older than the frame's reserved inputs (image.png/state.json
    changed — it no longer describes the input). needs_reprocess is ADVISORY: it is True
    only when the Prolog rule pack content has actually changed since the cache was
    written; consumers keep serving the cache and merely offer reprocessing.
    """
    cache = frame_dir / "recognition.json"
    if not cache.is_file():
        return None
    try:
        mtime = cache.stat().st_mtime
    except OSError:
        return None
    for name in ("image.png", "state.json"):
        source = frame_dir / name
        if source.is_file() and source.stat().st_mtime > mtime:
            return None
    try:
        result = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(result, dict) or result.get("schema_version") != 1:
        return None
    recorded = result.get("rules_fingerprint")
    if isinstance(recorded, str):
        needs_reprocess = recorded != rules_fingerprint()
    else:
        # Legacy cache without a fingerprint: advise reprocessing so it gains one.
        needs_reprocess = True
    return result, mtime, needs_reprocess


def _hex_rgb(color: str) -> tuple[int, int, int]:
    color = (color or "#000000").lstrip("#")
    try:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def _part_pixels(result: dict) -> dict:
    """Every region's pixels: {region_id: (color, [(x, y), ...])}. Works for both pipelines."""
    out = {}
    cv = result.get("opencv") or {}
    for part in cv.get("parts") or []:
        runs = part.get("pixelRuns") or []
        cells = [(x, y) for y, left, right in runs for x in range(left, right + 1)]
        out[part["id"]] = (part.get("color", "#000000"), cells)
    for part in (result.get("prolog") or {}).get("parts") or []:
        if part["id"] not in out and isinstance(part.get("cells"), list):
            out[part["id"]] = (part.get("color", "#000000"), [tuple(c) for c in part["cells"]])
    for obj in result.get("objects") or []:
        if obj["id"] not in out and isinstance(obj.get("cells"), list):
            out[obj["id"]] = (obj.get("color", "#000000"), [tuple(c) for c in obj["cells"]])
    return out


def rebuild_images(result: dict) -> dict | None:
    """Reconstruct preview and debug_image PNGs (dropped from the cache) from cached facts."""
    try:
        from PIL import Image
        from pixels_to_regions import _draw_parts_debug
    except ImportError:
        return None
    width, height = result.get("width"), result.get("height")
    if type(width) is not int or type(height) is not int or not (0 < width <= 4096 and 0 < height <= 4096):
        return None
    pixels = _part_pixels(result)
    if not pixels:
        return None
    image = Image.new("RGB", (width, height))
    px = image.load()
    for color, cells in pixels.values():
        rgb = _hex_rgb(color)
        for x, y in cells:
            if 0 <= x < width and 0 <= y < height:
                px[x, y] = rgb
    parts = (result.get("prolog") or {}).get("parts") or []
    polygons = {p["id"]: {"outer": [tuple(pt) for pt in (p["polygons"][0] if p.get("polygons") else [])],
                          "holes": [[tuple(pt) for pt in ring] for ring in p.get("holes", [])]}
                for p in parts}
    midlines = {p["id"]: [[tuple(pt) for pt in line] for line in p.get("midlines", [])] for p in parts}
    fillpoints = {p["id"]: [tuple(pt) for pt in p.get("fillpoints", [])] for p in parts}
    preview = BytesIO()
    image.save(preview, format="PNG")
    debug = BytesIO()
    _draw_parts_debug(image, polygons, midlines, fillpoints).save(debug, format="PNG")
    return {"preview": base64.b64encode(preview.getvalue()).decode("ascii"),
            "debug_image": base64.b64encode(debug.getvalue()).decode("ascii")}


def cached_frame_result(payload: dict, data_root: Path) -> dict | None:
    """Serve /recognize from the crawler cache when the request matches it exactly.

    Requires: a recorded frame reference, crawler-default engine parameters, the same
    pipeline, and the payload image bytes hashing to the cached source sha256 (so an
    edited image can never be answered from the cache). Returns None to run live.
    """
    frame = payload.get("frame")
    if not isinstance(frame, dict):
        return None
    if payload.get("force_live"):
        return None  # explicit user re-run: bypass the cache, never delete it
    for key, default in CRAWLER_DEFAULTS.items():
        if payload.get(key, default) != default:
            return None
    frame_dir = resolve_frame_dir(data_root, frame.get("sequenceId"), frame.get("frameId"))
    if frame_dir is None:
        return None
    cached = cached_recognition(frame_dir)
    if cached is None:
        return None
    result, mtime, needs_reprocess = cached
    if result.get("pipeline") != payload.get("pipeline"):
        return None
    image = payload.get("image")
    if isinstance(image, dict) and isinstance(image.get("base64"), str):
        try:
            digest = sha256(base64.b64decode(image["base64"], validate=True)).hexdigest()
        except (ValueError, TypeError):
            return None
        if digest != (result.get("source") or {}).get("sha256"):
            return None
    images = rebuild_images(result)
    if images is None:
        return None
    result.update(images)
    result["cached"] = {"file": "recognition.json", "mtime": mtime,
                        "needsReprocess": needs_reprocess}
    return result


def learned_scene(data_root: Path, sequence_id: str, upto: int | None = None,
                  static_only: bool = False) -> dict:
    """Compose the whole scene a recording has LEARNED across its frames.

    Darkness only OCCLUDES, it never erases. Two evidence modes:

    * Aperture recordings (RGBA frames with transparent pixels, e.g. spotlight tests):
      alpha 255 marks OBSERVED pixels — including observed black — so scene memory is the
      union of every aperture's contents. Alpha 0 stays unknown darkness.
    * Opaque recordings: the cached recognition's foreground regions are painted into
      scene memory; the detected background acts as the occluding darkness.

    With static_only, the composition keeps ONLY entities that never moved across the
    frames seen: the static scenery as it slowly got unoccluded. Every entity whose
    stable identity was ever seen at a different position is excluded entirely.
    (Aperture recordings carry no entity ownership, so static_only is ignored there.)

    Caches are never destroyed: frames whose cached recognition was written under older
    Prolog rules are still composed and listed in framesAwaitingReprocess (advisory);
    only unusable caches (missing/unreadable/older than reserved inputs) are skipped and
    reported in framesStale. Nothing is recomputed here.
    """
    from PIL import Image
    if not isinstance(sequence_id, str) or sequence_id.split("/", 1)[0] not in SEQUENCE_FAMILIES:
        raise ValueError("Scene sequence must be under recordings/ or curated/.")
    root = data_root.resolve()
    recording = (root / sequence_id).resolve()
    if not recording.is_relative_to(root) or not recording.is_dir():
        raise ValueError("Unknown recording.")
    frames = sorted((child for child in recording.iterdir()
                     if child.is_dir() and child.name.isdigit() and (child / "image.png").is_file()),
                    key=lambda path: int(path.name))
    if upto is not None:
        # Belief state AS OF a frame: compose only what had been seen up to (and including)
        # that frame, so stepping through a recording shows the belief evolving.
        frames = [frame for frame in frames if int(frame.name) <= upto]
    if not frames:
        raise ValueError("The recording has no frames.")
    width = height = None
    scene = None
    darkness = (13, 17, 26)
    aperture_mode = False
    frames_used, frames_stale, frames_awaiting = [], [], []
    origins: dict = {}   # stable entity id -> first seen (x, y) origin
    moved: set = set()   # stable ids seen at more than one position (movables)
    for frame_dir in frames:
        cached = cached_recognition(frame_dir)
        if cached is None:
            frames_stale.append(frame_dir.name)
            continue
        result, _, awaiting = cached
        if awaiting:
            # Processed artifacts are KEPT: an advanced source stamp only means the
            # crawler will reprocess; the learned scene never goes dark meanwhile.
            frames_awaiting.append(frame_dir.name)
        with Image.open(frame_dir / "image.png") as png:
            has_alpha = png.mode in ("RGBA", "LA", "PA")
            rgba = png.convert("RGBA") if has_alpha else None
            if width is None:
                aperture_mode = has_alpha and rgba.getextrema()[3][0] == 0
                if aperture_mode:
                    width, height = rgba.size
                else:
                    width, height = result.get("width"), result.get("height")
                    if type(width) is not int or type(height) is not int:
                        raise ValueError("Cached recognition lacks frame dimensions.")
                scene = [[None] * width for _ in range(height)]
            if aperture_mode:
                if rgba is None or rgba.size != (width, height):
                    frames_stale.append(frame_dir.name)
                    continue
                px = rgba.load()
                for y in range(height):
                    for x in range(width):
                        r, g, b, a = px[x, y]
                        if a:  # observed through the aperture, observed black included
                            scene[y][x] = (r, g, b)
                frames_used.append(frame_dir.name)
                continue
        if (result.get("width"), result.get("height")) != (width, height):
            frames_stale.append(frame_dir.name)
            continue
        background = set((result.get("prolog") or {}).get("background") or [])
        pixels = _part_pixels(result)
        bg_colors = [color for rid, (color, _) in pixels.items() if rid in background]
        if bg_colors:
            darkness = _hex_rgb(bg_colors[0])
        stable_ids = result.get("stable_ids") or {}
        foreground = [(stable_ids.get(rid, rid), _hex_rgb(color), cells)
                      for rid, (color, cells) in pixels.items() if rid not in background]
        # Track movement by STABLE identity: an entity whose origin ever changes is a
        # movable, never part of the static scenery layer.
        for sid, _, cells in foreground:
            if not cells:
                continue
            origin = (min(x for x, _ in cells), min(y for _, y in cells))
            if sid in origins and origins[sid] != origin:
                moved.add(sid)
            origins.setdefault(sid, origin)
        # PURGE on observed absence: an opaque frame observes EVERY pixel. Wherever this
        # frame shows background (not covered by any foreground entity), remembered content
        # was seen to be gone - a removed wall must not haunt the scene. Memory survives
        # only under pixels currently covered by a foreground entity (genuine occlusion).
        covered = set()
        for _, _, cells in foreground:
            covered.update((x, y) for x, y in cells)
        for y in range(height):
            row = scene[y]
            for x in range(width):
                if row[x] is not None and (x, y) not in covered:
                    row[x] = None
        for rid, rgb, cells in foreground:
            for x, y in cells:
                if 0 <= x < width and 0 <= y < height:
                    scene[y][x] = (rgb, rid)
        frames_used.append(frame_dir.name)
    if scene is None:
        raise ValueError("No fresh cached recognition for this recording yet; the crawler "
                         "must (re)process it before the learned scene can be composed.")
    if static_only and not aperture_mode:
        # Static scenery only: drop every pixel owned by an entity that ever moved.
        for y in range(height):
            row = scene[y]
            for x in range(width):
                value = row[x]
                if value is not None and len(value) == 2 and isinstance(value[1], str) and value[1] in moved:
                    row[x] = None
    if aperture_mode:
        darkness = (0, 0, 0)
    image = Image.new("RGB", (width, height), darkness)
    px = image.load()
    revealed = 0
    for y in range(height):
        row = scene[y]
        for x in range(width):
            value = row[x]
            if value is not None:
                # symbolic cells carry (rgb, owner-id); aperture cells carry plain rgb
                px[x, y] = value[0] if len(value) == 2 and isinstance(value[1], str) else value
                revealed += 1
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    induction = None
    # Induction lives under frame dirs: serve the belief state AS OF the composed range
    # (last frame ≤ upto), falling back to the legacy recording-root file for old stores.
    frame_candidates = sorted((child for child in recording.iterdir()
                               if child.is_dir() and child.name.isdigit()
                               and (upto is None or int(child.name) <= upto)),
                              key=lambda path: int(path.name), reverse=True)
    for candidate in [frame / "induction.json" for frame in frame_candidates] + [recording / "induction.json"]:
        if not candidate.is_file():
            continue
        try:
            induction = json.loads(candidate.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError):
            continue
    return {
        "sequenceId": sequence_id, "width": width, "height": height,
        "mode": "aperture" if aperture_mode else "symbolic",
        "scene": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "framesUsed": frames_used, "framesStale": frames_stale,
        "framesAwaitingReprocess": frames_awaiting,
        "revealedPixels": revealed, "coverage": round(revealed / (width * height), 4),
        "stillOccluded": width * height - revealed,
        "staticOnly": static_only, "movedEntities": sorted(moved),
        "induction": induction, "sourceEpoch": source_epoch(),
    }
