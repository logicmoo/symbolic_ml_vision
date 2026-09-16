"""Two-frame deduction: correspondence, movement, rotation, and occlusion.

Pure server-side reasoning (no rendering). Given the objects the single-frame pipeline
already produced for the current and previous frames -- optionally with their pixel masks
(``pixelRuns``) -- match each current object to its previous-frame counterpart and describe
the transform between them:

* movement   -- centroid shifted.
* rotation   -- centroid + area stable but the major-axis orientation changed (an elongated
                object turning in place). Detected from second-order image moments.
* occlusion  -- an object's visible pixels shrank or vanished AND its old location is now
                covered by a *different* object; reported as "occluded by X" rather than
                "removed". Detected from pixel coverage between the frames.

Everything here is a cross-frame inference, offered with the evidence, never asserted as a
certainty. Detection is math over the two images -- no rendering, no gold data.
"""

import base64
import json
import math

import numpy as np
import cv2
from frame_metta import _symbol


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


def _color_dist(a, b):
    ca, cb = _parse_color(a), _parse_color(b)
    if not ca or not cb:
        return 1.0
    return sum((x - y) ** 2 for x, y in zip(ca, cb)) ** 0.5 / 441.673


def _centroid(obj: dict):
    x, y, w, h = obj["bounds"]
    return (x + w / 2, y + h / 2)


def _runs(value: object):
    if not isinstance(value, list):
        return None
    runs = []
    for row in value:
        if isinstance(row, list) and len(row) == 3 and all(type(v) in (int, float) for v in row):
            y, l, r = int(row[0]), int(row[1]), int(row[2])
            if r >= l:
                runs.append((y, l, r))
    return runs or None


def _moments(runs):
    """Second-order image moments over a pixel mask given as (y, left, right) runs.
    Returns centroid, orientation (radians, major axis) and eccentricity (0=round,
    ->1 elongated). Uses closed-form run sums so it stays cheap for big blobs."""
    count = sum_x = sum_y = sum_x2 = sum_y2 = sum_xy = 0
    for y, l, r in runs:
        n = r - l + 1
        sx = (r * (r + 1) // 2) - ((l - 1) * l // 2)
        sx2 = (r * (r + 1) * (2 * r + 1) // 6) - ((l - 1) * l * (2 * l - 1) // 6)
        count += n
        sum_x += sx
        sum_x2 += sx2
        sum_y += n * y
        sum_y2 += n * y * y
        sum_xy += y * sx
    if count == 0:
        return None
    cx, cy = sum_x / count, sum_y / count
    mu20 = sum_x2 / count - cx * cx
    mu02 = sum_y2 / count - cy * cy
    mu11 = sum_xy / count - cx * cy
    theta = 0.5 * math.atan2(2 * mu11, mu20 - mu02)
    common = ((mu20 - mu02) ** 2 + 4 * mu11 * mu11) ** 0.5
    l1 = (mu20 + mu02 + common) / 2
    l2 = (mu20 + mu02 - common) / 2
    ecc = (1 - l2 / l1) ** 0.5 if l1 > 1e-9 and l2 >= 0 else 0.0
    return {"cx": cx, "cy": cy, "theta": theta, "ecc": ecc, "count": count}


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
    record = {"id": identifier, "shape_id": shape, "color": color, "area": float(area),
              "bounds": bounds, "runs": _runs(obj.get("pixelRuns")),
              "nativeId": obj.get("nativeId") if isinstance(obj.get("nativeId"), str) else identifier}
    record["moments"] = _moments(record["runs"]) if record["runs"] else None
    return record


def _frame(frame: object) -> list[dict]:
    if not isinstance(frame, dict) or not isinstance(frame.get("objects"), list):
        raise ValueError("Each frame must contain an objects list.")
    return [_object(obj) for obj in frame["objects"]]


def _wrap_deg(theta_rad: float) -> float:
    """Orientation is defined mod 180 deg (an axis, not a vector); wrap to (-90, 90]."""
    deg = math.degrees(theta_rad)
    while deg <= -90:
        deg += 180
    while deg > 90:
        deg -= 180
    return deg


def _occupancy(objects: list[dict]):
    """Map each occupied pixel to its object's id + color, for coverage tests."""
    owner = {}
    for obj in objects:
        if not obj["runs"]:
            continue
        for y, l, r in obj["runs"]:
            for x in range(l, r + 1):
                owner[(x, y)] = (obj["id"], obj["color"])
    return owner


def _coverage_by_other(subject: dict, owner: dict):
    """Fraction of a subject object's pixels covered in the other frame by a differently
    coloured object, plus the object that covers the most. Evidence for occlusion/reveal."""
    if not subject["runs"] or not owner:
        return 0.0, None
    total = covered = 0
    by = {}
    for y, l, r in subject["runs"]:
        for x in range(l, r + 1):
            total += 1
            hit = owner.get((x, y))
            if hit and _color_dist(subject["color"], hit[1]) > 0.12:
                covered += 1
                by[hit[0]] = by.get(hit[0], 0) + 1
    if not total:
        return 0.0, None
    top = max(by.items(), key=lambda kv: kv[1])[0] if by else None
    return covered / total, top


_BG_BGR = (37, 23, 16)  # dark backdrop (#101725) in OpenCV BGR order


def _hex_bgr(hex_color: str):
    c = _parse_color(hex_color)
    return (c[2], c[1], c[0]) if c else (0, 0, 0)


def _paint(arr, objects, native_ids):
    """Paint the given objects' pixel masks (by native r# id) into a BGR image array."""
    for obj in objects:
        if obj["nativeId"] not in native_ids or not obj["runs"]:
            continue
        bgr = _hex_bgr(obj["color"])
        for y, l, r in obj["runs"]:
            if 0 <= y < arr.shape[0]:
                arr[y, max(0, l):min(arr.shape[1], r + 1)] = bgr


def _encode_png(arr):
    ok, buffer = cv2.imencode(".png", arr)
    return ("data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")) if ok else None


def _compose_layers(curr, prev, matches, width, height):
    """Build the Layer 0 (complete background) and Layer 1 (movers) images in Python, so a
    merged background object exists server-side even when no browser/JS is available to
    composite it. Layer 0 = union of the stationary parts from both frames (the mover
    removed, the area it occupied filled from the other frame); Layer 1 = the movers."""
    stationary_curr = {m["currentNative"] for m in matches if m["dx"] == 0 and m["dy"] == 0}
    stationary_prev = {m["previousNative"] for m in matches if m["dx"] == 0 and m["dy"] == 0}
    mover_curr = {m["currentNative"] for m in matches if m["dx"] != 0 or m["dy"] != 0}

    layer0 = np.empty((height, width, 3), np.uint8)
    layer0[:] = _BG_BGR
    _paint(layer0, prev, stationary_prev)   # fill from previous frame first...
    _paint(layer0, curr, stationary_curr)   # ...then the current stationary parts on top

    layer1 = np.empty((height, width, 3), np.uint8)
    layer1[:] = _BG_BGR
    _paint(layer1, curr, mover_curr)

    return {"layer0Image": _encode_png(layer0), "layer1Image": _encode_png(layer1),
            "width": width, "height": height}


def _group_deductions(current_groups, previous_groups, move_by, occluded_e):
    """Group-level deductions matched by STABLE group id (G1, W2, ... assigned by the group
    tracker). current_groups / previous_groups are lists of {id, layer, members:[e#]}.
    Reports group movement (shared member motion), gained/lost members, and occlusion."""
    results = []
    prev_by_id = {g["id"]: (g, set(g["members"])) for g in (previous_groups or [])}
    cur_ids = set()
    for g in (current_groups or []):
        gid = g["id"]
        cur_ids.add(gid)
        cs = set(g["members"])
        prev = prev_by_id.get(gid)
        if prev is None:
            results.append({"layer": g["layer"], "id": gid, "members": sorted(cs),
                            "moved": None, "lost": [], "gained": sorted(cs),
                            "occludedMembers": [], "new": True})
            continue
        ps = prev[1]
        persist = cs & ps
        lost = sorted(ps - cs)
        gained = sorted(cs - ps)
        moves = {move_by.get(e, (0, 0)) for e in persist}
        moved = next(iter(moves)) if len(moves) == 1 and next(iter(moves)) != (0, 0) else None
        occl = [(e, occluded_e.get(e)) for e in lost if occluded_e.get(e)]
        results.append({"layer": g["layer"], "id": gid, "members": sorted(cs),
                        "moved": list(moved) if moved else None, "lost": lost,
                        "gained": gained, "occludedMembers": occl})
    for g in (previous_groups or []):
        if g["id"] in cur_ids:
            continue
        ps = set(g["members"])
        results.append({"layer": g["layer"], "id": g["id"], "members": [],
                        "moved": None, "lost": sorted(ps), "gained": [],
                        "occludedMembers": [(e, occluded_e.get(e)) for e in ps if occluded_e.get(e)],
                        "gone": True})
    return results


def _emit_files(matches, appeared, disappeared, current_order, previous_order, groups=None, suggestions=None, explanations=None) -> list:
    """Emit the cross-frame deductions as MeTTa and Prolog files, using ONLY stable e#
    identities (r# never appears). Hypotheses are written as hypothesis/typed facts with
    confidences so consumers keep them as predictions, not certainties."""
    co = current_order if current_order is not None else "curr"
    po = previous_order if previous_order is not None else "prev"
    # MeTTa list literal: ([] a b c) for a proper list of member ids.
    def mlist(items):
        return "([]" + ("" if not items else " " + " ".join(items)) + ")"
    pl, mt = [], []
    pl.append(f"% Cross-frame deductions: frame {po} -> frame {co}.")
    pl.append("% Identities are stable e# (clip-tracked). Per-frame OpenCV r# are NOT used here.")
    pl.append("% Predictions/hypotheses are not facts; confidences are rough.")
    mt.append(f"; Cross-frame deductions: frame {po} -> frame {co}.")
    mt.append("; Stable e# identities only. Hypotheses carry confidences; they are not facts.")
    def hypothesis(entity, value):
        label = value["label"]
        pl.append(f"hypothesis({entity}, {json.dumps(label, ensure_ascii=False)}, confidence({value['confidence']}), frame({co})).")
        symbol = _symbol(label) if label else '""'
        mt.append(f"(hypothesis {entity} {symbol} (confidence {value['confidence']}) (frame {co}))")
    for m in matches:
        e = m["current"]
        if m["dx"] or m["dy"]:
            pl.append(f"moved({e}, dx({m['dx']}), dy({m['dy']}), from_frame({po}), to_frame({co})).")
            mt.append(f"(moved {e} (dx {m['dx']}) (dy {m['dy']}) (from {po}) (to {co}))")
        if m.get("rotationDeg") is not None and "rotated" in m.get("transform", ""):
            pl.append(f"rotated({e}, degrees({m['rotationDeg']}), frame({co})).")
            mt.append(f"(rotated {e} (degrees {m['rotationDeg']}) (frame {co}))")
        if m.get("occludedBy"):
            pl.append(f"occluded({e}, by({m['occludedBy']}), coverage({m['coverage']}), frame({co})).")
            mt.append(f"(occluded {e} (by {m['occludedBy']}) (coverage {m['coverage']}) (frame {co}))")
        if m["dx"] == 0 and m["dy"] == 0 and not m.get("rotationDeg") and not m.get("occludedBy"):
            pl.append(f"stationary({e}, frame({co})).")
            mt.append(f"(stationary {e} (frame {co}))")
        for h in m.get("hypotheses", []):
            hypothesis(e, h)
    for d in disappeared:
        e = d["previous"]
        pl.append(f"gone({e}, last_frame({po})).")
        mt.append(f"(gone {e} (last-frame {po}))")
        for h in d.get("hypotheses", []):
            hypothesis(e, h)
    for a in appeared:
        e = a["current"]
        pl.append(f"appeared({e}, frame({co})).")
        mt.append(f"(appeared {e} (frame {co}))")
        for h in a.get("hypotheses", []):
            hypothesis(e, h)
    for g in (groups or []):
        gid, members = g["id"], ", ".join(g["members"])
        if g.get("gone"):
            pl.append(f"group_gone({gid}, last_frame({po})).")
            mt.append(f"(group-gone {gid} (last-frame {po}))")
        elif g.get("new"):
            pl.append(f"group_new({gid}, members([{members}]), frame({co})).")
            mt.append(f"(group-new {gid} (members {mlist(g['members'])}) (frame {co}))")
        else:
            layer = g["layer"].lower()  # lowercase so it is a Prolog atom, not a variable
            pl.append(f"group({gid}, layer({layer}), members([{members}]), frame({co})).")
            mt.append(f"(group {gid} (layer {layer}) (members {mlist(g['members'])}) (frame {co}))")
            if g.get("moved"):
                pl.append(f"group_moved({gid}, dx({g['moved'][0]}), dy({g['moved'][1]}), frame({co})).")
                mt.append(f"(group-moved {gid} (dx {g['moved'][0]}) (dy {g['moved'][1]}) (frame {co}))")
        for e in g.get("gained", []):
            pl.append(f"group_gained_member({gid}, {e}, frame({co})).")
            mt.append(f"(group-gained-member {gid} {e} (frame {co}))")
        for e in g.get("lost", []):
            pl.append(f"group_lost_member({gid}, {e}, frame({co})).")
            mt.append(f"(group-lost-member {gid} {e} (frame {co}))")
        for e, occ in g.get("occludedMembers", []):
            pl.append(f"group_member_occluded({gid}, {e}, by({occ}), frame({co})).")
            mt.append(f"(group-member-occluded {gid} {e} (by {occ}) (frame {co}))")
    for s in (suggestions or []):
        members = ", ".join(s["members"])
        reason = s.get("reason", "co_behaving")
        if reason == "moved_together":
            pl.append(f"suggested_group([{members}], reason(moved_together), dx({s['dx']}), dy({s['dy']}), frame({co})).  % no G/W backs this co-moving set")
            mt.append(f"(suggested-group (members {mlist(s['members'])}) (reason moved-together) (dx {s['dx']}) (dy {s['dy']}) (frame {co}))")
        elif reason == "gone_together":
            pl.append(f"suggested_group([{members}], reason(gone_together), occluded_by({s['occludedBy']}), frame({co})).  % no G/W backs this co-disappearing set")
            mt.append(f"(suggested-group (members {mlist(s['members'])}) (reason gone-together) (occluded-by {s['occludedBy']}) (frame {co}))")
        elif reason == "revealed_together":
            pl.append(f"suggested_group([{members}], reason(revealed_together), revealed_from({s['revealedFrom']}), frame({co})).  % now un-occluded: assign a new W/G and read its turtle")
            mt.append(f"(suggested-group (members {mlist(s['members'])}) (reason revealed-together) (revealed-from {s['revealedFrom']}) (frame {co}))")
    for x in (explanations or []):
        mover, pivot, deg = x["entity"], x["by"], x["degrees"]
        # Logical formulation: a rigid pivot's rotation entails a nearby part's apparent
        # translation, so the part has no independent motion.
        pl.append("% Rule: rotation of a rigid pivot entails a nearby part's apparent translation.")
        pl.append(f"apparent_move_explained({mover}, {pivot}, {co}) :- rotated({pivot}, degrees({deg}), frame({co})), moved({mover}, _, _, _, frame({co})), near({mover}, {pivot}, frame({co})).")
        pl.append(f"near({mover}, {pivot}, frame({co})).")
        pl.append(f"\\+ independent_motion({mover}, frame({co})) :- apparent_move_explained({mover}, {pivot}, {co}).  % move is a consequence, not its own action")
        mt.append("; Rule: rotation of a rigid pivot entails a nearby part's apparent translation.")
        mt.append(f"(= (apparent-move-explained {mover} {pivot} {co}) (and (rotated {pivot} (degrees {deg}) (frame {co})) (moved {mover} (frame {co})) (near {mover} {pivot} (frame {co}))))")
        mt.append(f"(near {mover} {pivot} (frame {co}))")
        mt.append(f"(implies (apparent-move-explained {mover} {pivot} {co}) (not (independent-motion {mover} (frame {co}))))")
    return [
        {"name": "deductions.metta", "content": "\n".join(mt) + "\n", "media_type": "text/plain; charset=utf-8"},
        {"name": "deductions.pl", "content": "\n".join(pl) + "\n", "media_type": "text/plain; charset=utf-8"},
    ]


def deduce_two_frames(current: object, previous: object, *, width: object = None,
                      height: object = None, current_order: object = None,
                      previous_order: object = None, current_groups: object = None,
                      previous_groups: object = None, min_score: float = 1.5) -> dict:
    curr = _frame(current)
    prev = _frame(previous)
    scored = []
    for c in curr:
        for p in prev:
            same_shape = 1 if c["shape_id"] == p["shape_id"] else 0
            color_dist = _color_dist(c["color"], p["color"])
            area_ratio = min(c["area"], p["area"]) / max(c["area"], p["area"]) if max(c["area"], p["area"]) else 0.0
            cx, cy = _centroid(c)
            px, py = _centroid(p)
            proximity = 1 - min(1.0, ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 / 200.0)
            # Correspondence leans on colour + area + proximity so a rotated or partly
            # occluded object (whose shape_id may change) still binds to its prior self.
            score = same_shape * 1.5 + (1 - color_dist) * 2 + area_ratio + proximity
            scored.append((score, same_shape, area_ratio, color_dist, c, p))
    scored.sort(key=lambda row: -row[0])
    curr_owner = _occupancy(curr)
    prev_owner = _occupancy(prev)
    used_c, used_p, matches = set(), set(), []
    for score, same_shape, area_ratio, color_dist, c, p in scored:
        if score < min_score or c["id"] in used_c or p["id"] in used_p:
            continue
        used_c.add(c["id"])
        used_p.add(p["id"])
        cx, cy = _centroid(c)
        px, py = _centroid(p)
        dx, dy = round(cx - px), round(cy - py)
        dist = (dx * dx + dy * dy) ** 0.5
        directions = []
        if dx < -1:
            directions.append(f"left {-dx}")
        elif dx > 1:
            directions.append(f"right {dx}")
        if dy < -1:
            directions.append(f"up {-dy}")
        elif dy > 1:
            directions.append(f"down {dy}")

        rotation_deg = None
        if c["moments"] and p["moments"] and c["moments"]["ecc"] >= 0.6 and p["moments"]["ecc"] >= 0.6:
            rotation_deg = round(_wrap_deg(c["moments"]["theta"] - p["moments"]["theta"]), 1)

        coverage, occluder = _coverage_by_other(p, curr_owner)
        rotated = rotation_deg is not None and abs(rotation_deg) >= 10 and dist <= 3 and 0.8 <= area_ratio <= 1.25
        occluded = area_ratio < 0.85 and coverage >= 0.25

        transforms = []
        if dist > 2 and not rotated:
            transforms.append("moved " + ", ".join(directions) + " px" if directions else "moved")
        if rotated:
            transforms.append(f"rotated {rotation_deg:+.0f}\u00b0")
        if occluded:
            transforms.append(f"partly occluded by {occluder}" if occluder else "partly occluded")
        elif area_ratio >= 1.2 and dist <= 3:
            transforms.append("grew / revealed")
        if not transforms:
            transforms.append("stationary")

        hypotheses = []
        if rotated:
            hypotheses.append({"label": "rotation in place", "confidence": 0.6})
            hypotheses.append({"label": "shape changed by (un)occlusion", "confidence": 0.4})
        if occluded:
            hypotheses.append({"label": f"occluded by {occluder}" if occluder else "occluded", "confidence": 0.6})
            hypotheses.append({"label": "shrank / partially left frame", "confidence": 0.4})

        matches.append({
            "current": c["id"], "previous": p["id"], "sameShape": bool(same_shape),
            "currentNative": c["nativeId"], "previousNative": p["nativeId"],
            "color": c["color"], "dx": dx, "dy": dy,
            "level": 0 if (dx == 0 and dy == 0) else 1,
            "movement": ("moved " + ", ".join(directions) + " px") if directions else "stationary",
            "transform": ", ".join(transforms),
            "rotationDeg": rotation_deg, "occludedBy": occluder if occluded else None,
            "coverage": round(coverage, 3),
            "cx": round(cx, 1), "cy": round(cy, 1),
            "areaRatio": round(area_ratio, 3), "score": round(score, 3),
            "hypotheses": hypotheses,
        })

    disappeared = []
    for p in prev:
        if p["id"] in used_p:
            continue
        coverage, occluder = _coverage_by_other(p, curr_owner)
        px, py = _centroid(p)
        disappeared.append({
            "previous": p["id"], "previousNative": p["nativeId"], "color": p["color"],
            "cx": round(px, 1), "cy": round(py, 1),
            "occludedBy": occluder if coverage >= 0.4 else None, "coverage": round(coverage, 3),
            "hypotheses": (
                [{"label": f"occluded by {occluder}", "confidence": 0.6},
                 {"label": "removed / left the frame", "confidence": 0.4}]
                if coverage >= 0.4 else
                [{"label": "removed / left the frame", "confidence": 0.5},
                 {"label": "occluded (no clear occluder found)", "confidence": 0.5}]
            ),
        })

    appeared = []
    for c in curr:
        if c["id"] in used_c:
            continue
        coverage, revealer = _coverage_by_other(c, prev_owner)
        cx, cy = _centroid(c)
        appeared.append({
            "current": c["id"], "currentNative": c["nativeId"], "color": c["color"],
            "cx": round(cx, 1), "cy": round(cy, 1),
            "revealedFrom": revealer if coverage >= 0.4 else None, "coverage": round(coverage, 3),
            "hypotheses": (
                [{"label": f"revealed from behind {revealer}", "confidence": 0.6},
                 {"label": "newly spawned", "confidence": 0.4}]
                if coverage >= 0.4 else
                [{"label": "newly spawned", "confidence": 0.5},
                 {"label": "emerged from an edge/occluder", "confidence": 0.5}]
            ),
        })

    result = {"matches": matches, "appeared": appeared, "disappeared": disappeared}
    # Publish per-entity bounds for both frames (keyed by stable e#) so the UI can highlight
    # a token's location on the current image, or on the previous image when it is gone.
    result["entityBounds"] = {c["id"]: c["bounds"] for c in curr}
    result["prevEntityBounds"] = {p["id"]: p["bounds"] for p in prev}
    if type(width) in (int, float) and type(height) in (int, float) and width > 0 and height > 0:
        result["layers"] = _compose_layers(curr, prev, matches, int(width), int(height))
    # A rigid object's rotation can EXPLAIN a neighbour's apparent move (the neighbour didn't
    # move on its own -- the object turned). Link a moved entity to a nearby rotating one.
    rotated = [m for m in matches if m.get("rotationDeg") and abs(m["rotationDeg"]) >= 10]
    explanations = []
    for m in matches:
        if (m["dx"] or m["dy"]) and not m.get("rotationDeg"):
            for r in rotated:
                dist = ((m["cx"] - r["cx"]) ** 2 + (m["cy"] - r["cy"]) ** 2) ** 0.5
                if dist <= 80:
                    explanations.append({"entity": m["current"], "by": r["current"],
                                         "kind": "rotation", "degrees": r["rotationDeg"]})
                    break
    result["explanations"] = explanations
    # Group-level deductions matched by stable group id.
    move_by = {m["current"]: (m["dx"], m["dy"]) for m in matches}
    occluded_e = {d["previous"]: d.get("occludedBy") for d in disappeared if d.get("occludedBy")}
    groups = _group_deductions(current_groups, previous_groups, move_by, occluded_e)
    result["groups"] = groups
    # Co-moving / co-disappearing sets with no backing G/W group -> suggested groups.
    # These are feedback signals: the grouping/W algorithm may want to add such a group.
    prev_group_sets = [set(g["members"]) for g in (previous_groups or [])]
    suggestions = []
    moved_vecs = {}
    for m in matches:
        if m["dx"] or m["dy"]:
            moved_vecs.setdefault((m["dx"], m["dy"]), []).append(m["current"])
    group_moved_vecs = {tuple(g["moved"]) for g in groups if g.get("moved")}
    for (dx, dy), members in moved_vecs.items():
        if len(members) >= 2 and (dx, dy) not in group_moved_vecs:
            suggestions.append({"members": sorted(members), "reason": "moved_together", "dx": dx, "dy": dy})
    # Entities that disappeared together behind the same occluder should likely be one group.
    gone_by_occ = {}
    for d in disappeared:
        if d.get("occludedBy"):
            gone_by_occ.setdefault(d["occludedBy"], []).append(d["previous"])
    for occ, members in gone_by_occ.items():
        s = set(members)
        if len(s) >= 2 and not any(s <= ps for ps in prev_group_sets):
            suggestions.append({"members": sorted(s), "reason": "gone_together", "occludedBy": occ})
    # Symmetric: entities revealed together (the occluder moved away) are one object finally
    # visible -> promote to a new W/G and read its turtle to identify the real shape.
    cur_group_sets = [set(g["members"]) for g in (current_groups or [])]
    revealed_by = {}
    for a in appeared:
        if a.get("revealedFrom"):
            revealed_by.setdefault(a["revealedFrom"], []).append(a["current"])
    for rev, members in revealed_by.items():
        s = set(members)
        if len(s) >= 2 and not any(s <= cs for cs in cur_group_sets):
            suggestions.append({"members": sorted(s), "reason": "revealed_together", "revealedFrom": rev})
    result["suggestedGroups"] = suggestions
    result["files"] = _emit_files(matches, appeared, disappeared, current_order, previous_order, groups, suggestions, explanations)
    return result
