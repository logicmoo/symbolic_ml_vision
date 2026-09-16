"""Multi-frame object tracker keyed by clip.

Accumulates each frame's objects (as produced by the single-frame pipeline) and
replays them in order to maintain persistent entity identities across the whole
clip. A reappearing object re-binds to its remembered (occluded) entity instead
of being reported as brand new, so appearance/disappearance without movement is
read as occlusion / reveal rather than creation / destruction.

Reasoning lives here (Python), not in the browser. State is per-clip and in
memory only; nothing is written to disk.
"""

import threading

_LOCK = threading.Lock()
_CLIPS: dict[str, dict] = {}


def _parse_color(value: object):
    if not isinstance(value, str):
        return None
    text = value.lstrip("#")
    if len(text) != 6:
        return None
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return None


def _centroid(bounds):
    x, y, w, h = bounds
    return (x + w / 2, y + h / 2)


def _color_dist(a: object, b: object):
    ca, cb = _parse_color(a), _parse_color(b)
    if not ca or not cb:
        return None
    return sum((x - y) ** 2 for x, y in zip(ca, cb)) ** 0.5 / 441.673


# Thresholds for classifying a bound entity's change between frames.
_RECOLOR_MIN = 0.12   # normalized color distance (0..1) above which we call it recolored
_GROW_MIN = 1.2       # area ratio (now/prev) above which the silhouette grew (reveal)
_SHRINK_MAX = 0.83    # area ratio (now/prev) below which it shrank (further occlusion)
_BAR_ASPECT = 4.0     # elongated rectangle (long/short side) whose end can slide
_ANCHOR_TOL = 3       # px an edge may drift and still count as anchored (fixed end)
_EDGE_MIN_DELTA = 2   # px the free edge must move to register an anchored-edge event


def _anchored_edge(entity: dict, obj: dict):
    """An elongated entity with one fixed edge and one sliding edge. This is the raw,
    honest observation: the pixels show a bar whose free end extended or retracted. We do
    NOT decide here what it *means* -- an extend could be an object emerging from behind an
    occluder OR a HUD gauge filling; both look identical. Returns (event, delta) or None."""
    px, py, pw, ph = entity["bounds"]
    x, y, w, h = obj["bounds"]
    long_now, short_now = max(w, h), min(w, h)
    if short_now <= 0 or long_now / short_now < _BAR_ASPECT:
        return None
    if w >= h:  # horizontal: a vertical edge is fixed
        fixed = abs(x - px) <= _ANCHOR_TOL or abs((x + w) - (px + pw)) <= _ANCHOR_TOL
        delta = w - pw
    else:       # vertical: a horizontal edge is fixed
        fixed = abs(y - py) <= _ANCHOR_TOL or abs((y + h) - (py + ph)) <= _ANCHOR_TOL
        delta = h - ph
    if fixed and abs(delta) >= _EDGE_MIN_DELTA:
        return ("edge_extend" if delta > 0 else "edge_retract", delta)
    return None


def _near_border(bounds, width: float, height: float) -> bool | None:
    """Whether the bbox hugs a frame edge (HUD overlays usually do; world objects that
    emerge from an occluder usually do not). None when frame size is unknown."""
    if not width or not height:
        return None
    x, y, w, h = bounds
    mx, my = max(4.0, 0.03 * width), max(4.0, 0.03 * height)
    return x <= mx or y <= my or (width - (x + w)) <= mx or (height - (y + h)) <= my


def _edge_hypotheses(event: str, near_border) -> list[dict]:
    """Competing interpretations for an anchored-edge event, as hypotheses with rough
    confidences -- never asserted as fact. Border-anchored nudges toward a HUD gauge;
    interior nudges toward a world reveal/occlusion. Unknown border keeps it 50/50."""
    if event == "edge_extend":
        world_label = "reveal: object emerging from behind an occluder"
        gauge_label = "gauge fill: HUD bar increasing"
    else:
        world_label = "occlusion: object receding behind an occluder"
        gauge_label = "gauge deplete: HUD bar decreasing"
    adj = 0.0 if near_border is None else (0.2 if near_border else -0.2)
    world = round(max(0.05, min(0.95, 0.5 - adj)), 2)
    gauge = round(1 - world, 2)
    pair = [{"label": world_label, "confidence": world},
            {"label": gauge_label, "confidence": gauge}]
    pair.sort(key=lambda hyp: -hyp["confidence"])
    return pair


def _classify(entity: dict, obj: dict, dx: int, dy: int, was_occluded: bool,
              width: float = 0.0, height: float = 0.0):
    """Returns (changes, hypotheses). changes are neutral observations; hypotheses hold
    the competing meanings of an anchored-edge event so nothing is over-claimed."""
    changes: list[str] = []
    hypotheses: list[dict] = []
    if was_occluded:
        changes.append("reappeared")
    cd = _color_dist(entity["color"], obj["color"])
    recolored = cd is not None and cd > _RECOLOR_MIN
    edge = _anchored_edge(entity, obj)
    if edge:
        # An anchored bar's edge slide is reported as the observed event; its meaning
        # (reveal / occlusion / gauge) is left to ranked hypotheses, not decided here.
        event, _delta = edge
        changes.append(event)
        hypotheses = _edge_hypotheses(event, _near_border(obj["bounds"], width, height))
        if recolored:
            changes.append("recolored")
        return changes, hypotheses
    if dx != 0 or dy != 0:
        changes.append("moved")
    if recolored:
        changes.append("recolored")
    prev_area = entity["area"]
    if prev_area > 0:
        ratio = obj["area"] / prev_area
        if ratio >= _GROW_MIN:
            changes.append("grew")
        elif ratio <= _SHRINK_MAX:
            changes.append("shrank")
    if not changes:
        changes.append("stationary")
    return changes, hypotheses


def _object(obj: object) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("Each object must be an object.")
    identifier = obj.get("id")
    shape = obj.get("shape_id")
    color = obj.get("color")
    area = obj.get("area")
    bounds = obj.get("bounds")
    if not isinstance(identifier, str) or not isinstance(shape, str) or not isinstance(color, str):
        raise ValueError("Object needs string id, shape_id, and color.")
    if type(area) not in (int, float) or not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError("Object needs numeric area and a 4-number bounds.")
    if any(type(value) not in (int, float) for value in bounds):
        raise ValueError("Object bounds must be numeric.")
    return {"id": identifier, "shape_id": shape, "color": color, "area": float(area), "bounds": list(bounds)}


def _score(obj: dict, entity: dict, diag: float) -> float:
    # Occlusion-tolerant: identity carries on COLOR + spatial continuity, so an
    # entity whose silhouette grows as parts are revealed (a dragon's tail finally
    # un-occluded) still binds to the same entity. Shape is only a soft bonus.
    same_shape = 1 if obj["shape_id"] == entity["shape_id"] else 0
    oc, ec = _parse_color(obj["color"]), _parse_color(entity["color"])
    color_score = (1 - sum((a - b) ** 2 for a, b in zip(oc, ec)) ** 0.5 / 441.673) if oc and ec else 0.0
    area_ratio = min(obj["area"], entity["area"]) / max(obj["area"], entity["area"]) if max(obj["area"], entity["area"]) else 0.0
    ox, oy = _centroid(obj["bounds"])
    ex, ey = _centroid(entity["bounds"])
    dist = ((ox - ex) ** 2 + (oy - ey) ** 2) ** 0.5
    proximity = max(0.0, 1 - dist / diag) if diag else 0.0
    return color_score * 2 + proximity * 1.5 + area_ratio * 1 + same_shape


def _replay(frames: dict[int, list[dict]], upto: int, diag: float,
            width: float = 0.0, height: float = 0.0, min_score: float = 2.0) -> dict:
    entities: list[dict] = []
    next_id = 1
    per_frame: list[dict] = []
    for order in sorted(k for k in frames if k <= upto):
        objects = frames[order]
        scored = []
        for obj in objects:
            for entity in entities:
                s = _score(obj, entity, diag)
                if s >= min_score:
                    scored.append((s, obj["id"], entity["eid"], obj, entity))
        scored.sort(key=lambda row: -row[0])
        used_obj, used_ent, bound = set(), set(), {}
        for s, oid, eid, obj, entity in scored:
            if oid in used_obj or eid in used_ent:
                continue
            used_obj.add(oid)
            used_ent.add(eid)
            bound[oid] = (entity, obj)
        frame_status = {}
        for obj in objects:
            if obj["id"] in bound:
                entity, _ = bound[obj["id"]]
                cx, cy = _centroid(obj["bounds"])
                ex, ey = _centroid(entity["bounds"])
                dx, dy = round(cx - ex), round(cy - ey)
                was_occluded = entity["status"] == "occluded"
                changes, hypotheses = _classify(entity, obj, dx, dy, was_occluded, width, height)
                cd = _color_dist(entity["color"], obj["color"])
                area_ratio = round(obj["area"] / entity["area"], 3) if entity["area"] else None
                # Primary status is the observed event; changes[] stacks them all and
                # hypotheses[] holds the competing meanings of an anchored-edge event.
                if was_occluded:
                    status = "reappeared"
                elif "edge_extend" in changes or "edge_retract" in changes:
                    status = "edge_extend" if "edge_extend" in changes else "edge_retract"
                elif "moved" in changes:
                    status = "moved"
                elif "recolored" in changes:
                    status = "recolored"
                elif "grew" in changes or "shrank" in changes:
                    status = "grew" if "grew" in changes else "shrank"
                else:
                    status = "stationary"
                entity.update(bounds=obj["bounds"], area=obj["area"], color=obj["color"],
                              status="visible", last_seen=order, current=obj["id"])
                frame_status[obj["id"]] = {"eid": entity["eid"], "status": status,
                                           "changes": changes, "hypotheses": hypotheses,
                                           "dx": dx, "dy": dy,
                                           "colorDist": round(cd, 3) if cd is not None else None,
                                           "areaRatio": area_ratio}
            else:
                entity = {"eid": f"e{next_id}", "shape_id": obj["shape_id"], "color": obj["color"],
                          "area": obj["area"], "bounds": obj["bounds"], "status": "visible",
                          "last_seen": order, "first_seen": order, "current": obj["id"]}
                next_id += 1
                entities.append(entity)
                frame_status[obj["id"]] = {"eid": entity["eid"], "status": "new",
                                           "changes": ["new"], "hypotheses": [], "dx": 0, "dy": 0,
                                           "colorDist": None, "areaRatio": None}
        present = {b[0]["eid"] for b in bound.values()} | {fs["eid"] for fs in frame_status.values()}
        for entity in entities:
            if entity["eid"] not in present and entity["status"] != "occluded":
                entity["status"] = "occluded"
        per_frame.append({"order": order, "status": frame_status})
    return {"entities": entities, "frames": per_frame}


def track_frame(sequence_id: object, order: object, objects: object, width: object = None,
                height: object = None, channel: object = "frame") -> dict:
    if not isinstance(sequence_id, str) or not sequence_id:
        raise ValueError("A sequenceId string is required.")
    if type(order) is not int or order < 0:
        raise ValueError("order must be a non-negative integer.")
    if not isinstance(objects, list):
        raise ValueError("objects must be a list.")
    if not isinstance(channel, str) or not channel:
        raise ValueError("channel must be a non-empty string.")
    parsed = [_object(obj) for obj in objects]
    # Each (sequence, channel) is an independent memory stream, so the raw frame,
    # layer 0 (background) and layer 1 (movers) each keep their own prev-vs-current
    # identity history without cross-contaminating.
    key = f"{sequence_id}\x00{channel}"
    with _LOCK:
        clip = _CLIPS.setdefault(key, {"frames": {}, "diag": 0.0, "width": 0.0, "height": 0.0})
        clip["frames"][order] = parsed
        if type(width) in (int, float) and type(height) in (int, float) and width > 0 and height > 0:
            clip["diag"] = (width ** 2 + height ** 2) ** 0.5
            clip["width"], clip["height"] = float(width), float(height)
        diag = clip["diag"]
        if not diag:
            extent = 0.0
            for frame_objs in clip["frames"].values():
                for obj in frame_objs:
                    x, y, w, h = obj["bounds"]
                    extent = max(extent, x + w, y + h)
            diag = (2 * extent ** 2) ** 0.5 or 1.0
        replay = _replay(clip["frames"], order, diag, clip.get("width", 0.0), clip.get("height", 0.0))
    entities = replay["entities"]
    this_frame = next((f for f in replay["frames"] if f["order"] == order), {"status": {}})
    status_by_current = this_frame["status"]
    present, occluded = [], []
    for entity in entities:
        record = {"eid": entity["eid"], "color": entity["color"], "shape_id": entity["shape_id"],
                  "firstSeen": entity["first_seen"], "lastSeen": entity["last_seen"],
                  "bounds": [round(v) for v in entity["bounds"]]}
        if entity["last_seen"] == order:
            current = entity.get("current")
            info = status_by_current.get(current, {})
            present.append({**record, "current": current, "status": info.get("status", "visible"),
                            "changes": info.get("changes", []), "hypotheses": info.get("hypotheses", []),
                            "dx": info.get("dx", 0), "dy": info.get("dy", 0),
                            "colorDist": info.get("colorDist"), "areaRatio": info.get("areaRatio")})
        else:
            gone = order - entity["last_seen"]
            # "Once occluded, you die" -- a disappearance MAY mean the entity was removed
            # (death) rather than merely occluded. We cannot tell them apart from absence
            # alone, so both are offered as hypotheses (correlation, not confirmed cause);
            # a later reappearance would retire the death hypothesis.
            hyps = [
                {"label": "occluded: still present but hidden behind something", "confidence": 0.5},
                {"label": "removed: entity destroyed / died (no reappearance yet)", "confidence": 0.5},
            ]
            occluded.append({**record, "framesSinceSeen": gone, "hypotheses": hyps})
    # Stack the present entities into layers by change kind so the UI can show one
    # layer per phenomenon (moved / recolored / grew / shrank / reappeared / new /
    # stationary). An entity can appear in more than one layer (a mover that also
    # recolors), which is exactly the "more than background/moved" generalization.
    order_kinds = ("new", "reappeared", "edge_extend", "edge_retract",
                   "moved", "recolored", "grew", "shrank", "stationary")
    layers = []
    for kind in order_kinds:
        eids = [p["eid"] for p in present if kind in (p["changes"] or [p["status"]])]
        if eids:
            layers.append({"kind": kind, "entities": eids})
    if occluded:
        layers.append({"kind": "occluded", "entities": [o["eid"] for o in occluded]})
    return {
        "sequenceId": sequence_id, "order": order, "channel": channel,
        "entityCount": len(entities), "present": present, "occluded": occluded,
        "layers": layers,
    }


def mapping(sequence_id: str, order: int, channel: str = "frame") -> dict:
    """Return the stable {native_id -> entity_id} map for one stored frame, so callers can
    relabel per-frame OpenCV region ids (r#) with clip-stable identities (e#). Empty when
    the frame hasn't been tracked yet."""
    key = f"{sequence_id}\x00{channel}"
    with _LOCK:
        clip = _CLIPS.get(key)
        if not clip or order not in clip["frames"]:
            return {}
        diag = clip.get("diag") or 0.0
        if not diag:
            extent = 0.0
            for frame_objs in clip["frames"].values():
                for obj in frame_objs:
                    x, y, w, h = obj["bounds"]
                    extent = max(extent, x + w, y + h)
            diag = (2 * extent ** 2) ** 0.5 or 1.0
        replay = _replay(clip["frames"], order, diag, clip.get("width", 0.0), clip.get("height", 0.0))
    frame = next((f for f in replay["frames"] if f["order"] == order), None)
    if not frame:
        return {}
    return {native_id: info["eid"] for native_id, info in frame["status"].items()}


def reset_clip(sequence_id: str, channel: str | None = None) -> None:
    with _LOCK:
        if channel is None:
            for key in [k for k in _CLIPS if k.split("\x00", 1)[0] == sequence_id]:
                _CLIPS.pop(key, None)
        else:
            _CLIPS.pop(f"{sequence_id}\x00{channel}", None)
