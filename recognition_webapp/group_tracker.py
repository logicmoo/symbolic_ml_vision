"""Clip-stable group identities (g1, g2, w1, w2, ...).

Per-frame OpenCV/Prolog group ids are transient, like region r# ids. This tracker gives each
G/W group a stable number across the clip by matching a frame's groups to the groups it saw
before, using member-set overlap (Jaccard) over the stable entity e# ids. So "w3" means the
same working group from frame to frame as long as it keeps most of its members. Ids are kept
lowercase (g#, w#) to match the lowercase e# entity ids and to stay valid Prolog atoms.

State is per (clip, layer) and in memory only; nothing is written to disk. Reasoning lives
here (Python), never in the browser.
"""

import threading

_LOCK = threading.Lock()
_CLIPS: dict[str, dict] = {}


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _replay(frames: dict[int, list[frozenset]], upto: int, layer: str, min_j: float = 0.3) -> dict:
    """Assign stable ids by replaying frames in order and binding each frame's groups to the
    remembered group with the best member-set overlap."""
    entities: list[dict] = []  # {gid, members}
    next_id = 1
    per_frame: dict[int, list[str]] = {}
    for order in sorted(k for k in frames if k <= upto):
        groups = frames[order]
        scored = []
        for gi, gset in enumerate(groups):
            for ent in entities:
                j = _jaccard(gset, ent["members"])
                if j >= min_j:
                    scored.append((j, gi, ent["gid"], ent))
        scored.sort(key=lambda row: -row[0])
        used_g, used_e, bound = set(), set(), {}
        for j, gi, gid, ent in scored:
            if gi in used_g or gid in used_e:
                continue
            used_g.add(gi)
            used_e.add(gid)
            bound[gi] = ent
        ids = []
        for gi, gset in enumerate(groups):
            if gi in bound:
                ent = bound[gi]
                ent["members"] = gset
                ids.append(ent["gid"])
            else:
                gid = f"{layer.lower()}{next_id}"
                next_id += 1
                entities.append({"gid": gid, "members": gset})
                ids.append(gid)
        per_frame[order] = ids
    return per_frame


def track_groups(sequence_id: str, order: int, groups_by_layer: dict) -> dict:
    """Store one frame's groups (per layer, each a set/list of member e# ids) and return the
    stable gid for each group, in the same order as the input lists."""
    result = {}
    with _LOCK:
        for layer in ("G", "W"):
            sets = [frozenset(g) for g in (groups_by_layer or {}).get(layer, [])]
            key = f"{sequence_id}\x00{layer}"
            clip = _CLIPS.setdefault(key, {"frames": {}})
            clip["frames"][order] = sets
            per_frame = _replay(clip["frames"], order, layer)
            result[layer] = per_frame.get(order, [])
    return result


def group_mapping(sequence_id: str, order: int) -> dict:
    """Stable gids for a previously stored frame, per layer, in stored input order."""
    result = {}
    with _LOCK:
        for layer in ("G", "W"):
            key = f"{sequence_id}\x00{layer}"
            clip = _CLIPS.get(key)
            if not clip or order not in clip["frames"]:
                result[layer] = []
                continue
            per_frame = _replay(clip["frames"], order, layer)
            result[layer] = per_frame.get(order, [])
    return result


def reset_clip(sequence_id: str) -> None:
    with _LOCK:
        for key in [k for k in _CLIPS if k.split("\x00", 1)[0] == sequence_id]:
            _CLIPS.pop(key, None)
