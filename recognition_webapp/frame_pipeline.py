"""Headless per-recording processing shared by the web server and the standalone crawler.

Everything here is filesystem/Prolog/Python only: no JavaScript is involved in producing or
converting symbolic output. A recording is run frame-by-frame through the same pipeline the web
UI uses (recognition + cross-frame deductions), the results are written next to each frame as
Prolog/MeTTa/JSON, every ``.pl`` is guaranteed a ``.metta`` sidecar, and an inductive summary is
induced across the whole sequence.
"""

import base64
from datetime import datetime, timezone
import json
import re
from pathlib import Path

from pipelines import run_pipeline
from tracker import track_frame, mapping as tracker_mapping
from group_tracker import track_groups
from two_frame import deduce_two_frames
from source_syntax import analyze_source

ROOT = Path(__file__).resolve().parent
# Source files whose modification time defines "the latest source update" the crawler watches:
# the Python package here plus the Prolog rule pack (prolog/omega_vision).
PACK_PROLOG_DIR = ROOT.parent / "prolog" / "omega_vision" / "prolog" / "omega_vision"


def source_epoch(root: Path = ROOT) -> float:
    """Newest modification time across the pipeline source files (crawler freshness clock)."""
    latest = 0.0
    for path in list(root.glob("*.py")) + list(PACK_PROLOG_DIR.glob("*.pl")):
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def deduce2_from_payload(payload: object) -> dict:
    """Cross-frame deduction with clip-stable e# identities. Shared by /omega_vision/api/v1/deduce2 and the crawler.

    Relabels both frames' objects with the tracker's stable ids before deducing, so matches,
    occluders, and reveals all reference stable ids (the per-frame r# is kept as nativeId).
    """
    if not isinstance(payload, dict):
        raise ValueError("A JSON object with current and previous frames is required.")
    current = payload.get("current")
    previous = payload.get("previous")
    sequence_id = payload.get("sequenceId")
    current_order = payload.get("currentOrder")
    previous_order = payload.get("previousOrder")
    user_action = payload.get("userAction")
    history = payload.get("history") if isinstance(payload.get("history"), dict) else None
    if (isinstance(sequence_id, str) and sequence_id and type(current_order) is int
            and type(previous_order) is int and isinstance(current, dict) and isinstance(previous, dict)):
        width, height = payload.get("width"), payload.get("height")
        # previousOrder -1 is the virtual EMPTY frame before frame 0: nothing to
        # track there, so the first real frame deduces pure appearances.
        virtual_previous = previous_order < 0
        if not virtual_previous:
            track_frame(sequence_id, previous_order, previous.get("objects") or [], width, height)
        track_frame(sequence_id, current_order, current.get("objects") or [], width, height)
        cmap = tracker_mapping(sequence_id, current_order)
        pmap = {} if virtual_previous else tracker_mapping(sequence_id, previous_order)
        relabel = lambda objs, m: [{**o, "id": m.get(o.get("id"), o.get("id")), "nativeId": o.get("id"),
                                    "adjacent_to": [m.get(x, x) for x in (o.get("adjacent_to") or [])]}
                                   for o in objs]
        current = {"objects": relabel(current.get("objects") or [], cmap)}
        previous = {"objects": relabel(previous.get("objects") or [], pmap)}
        map_groups = lambda gs, m: {layer: [sorted({m.get(r, r) for r in members})
                                            for members in (gs or {}).get(layer, [])]
                                    for layer in ("G", "W")}
        cur_groups = map_groups(payload.get("currentGroups"), cmap)
        prev_groups = map_groups(payload.get("previousGroups"), pmap)
        prev_gids = {} if virtual_previous else track_groups(sequence_id, previous_order, prev_groups)
        cur_gids = track_groups(sequence_id, current_order, cur_groups)

        def _with_ids(groups, gids):
            out = []
            for layer in ("G", "W"):
                for i, members in enumerate(groups.get(layer, [])):
                    gid = gids.get(layer, [])[i] if i < len(gids.get(layer, [])) else f"{layer.lower()}?"
                    out.append({"id": gid, "layer": layer, "members": members})
            return out

        return deduce_two_frames(current, previous, width=width, height=height,
                                 current_order=current_order, previous_order=previous_order,
                                 current_groups=_with_ids(cur_groups, cur_gids),
                                 previous_groups=_with_ids(prev_groups, prev_gids),
                                 user_action=user_action, history=history)
    return deduce_two_frames(current, previous, user_action=user_action, history=history)


# --- recording discovery -------------------------------------------------------------------

def find_recordings(recordings_root: Path) -> list[Path]:
    """Every recording directory (contains recording.json) under the recordings root.

    Prunes aggressively: once a directory has a recording.json it is a recording and we do NOT
    descend into its (numeric) frame directories or their generated output files, so discovery stays
    fast even after the crawler has written thousands of .pl/.metta/.json files.
    """
    import os
    if not recordings_root.is_dir():
        return []
    found = []
    for dirpath, dirnames, filenames in os.walk(recordings_root):
        if "recording.json" in filenames:
            found.append(Path(dirpath))
            dirnames[:] = []  # do not descend into frame directories
            continue
        # Never walk into per-frame directories or hidden control dirs.
        dirnames[:] = [d for d in dirnames if not d.isdigit() and not d.startswith(".")]
    return sorted(found)


def frame_dirs(recording: Path) -> list[Path]:
    """Ordered numeric frame directories that carry an image.png."""
    dirs = [child for child in recording.iterdir()
            if child.is_dir() and child.name.isdigit() and (child / "image.png").is_file()]
    return sorted(dirs, key=lambda path: int(path.name))


def _image_b64(frame_dir: Path) -> str:
    return base64.b64encode((frame_dir / "image.png").read_bytes()).decode("ascii")


def _group_members(result: dict, layer: str) -> list[list[str]]:
    return [group["members"] for group in result.get("group_layers", {}).get(layer, [])]


# --- stable identities (r# -> e#) ------------------------------------------------------------
# Persisted artifacts and the UI mostly show clip-stable e# entity ids instead of per-frame
# OpenCV r# region ids. Foreground regions are relabelled through the tracker; regions the
# tracker does not follow (background) keep their r# — hence "mostly".

_REGION_TOKEN = re.compile(r"\br(\d+)\b")


def _relabel_text(text: str, mapping: dict) -> str:
    return _REGION_TOKEN.sub(lambda match: mapping.get(match.group(0), match.group(0)), text)


def _relabel_value(value, mapping: dict):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_relabel_value(item, mapping) for item in value]
    if isinstance(value, dict):
        return {(mapping.get(key, key) if isinstance(key, str) else key): _relabel_value(item, mapping)
                for key, item in value.items()}
    return value


def stabilize_result(result: dict, sequence_id: str, order: int) -> dict:
    """Relabel a pipeline result's per-frame r# ids with clip-stable e# ids, in place.

    Tracks the frame (idempotent for identical input), then rewrites the structured views
    and the textual artifacts. Each object keeps its per-frame id as nativeId; the applied
    map is exposed as stable_ids. Unmapped regions (background) keep their r#.
    """
    track_frame(sequence_id, order, result.get("objects") or [],
                result.get("width"), result.get("height"))
    mapping = tracker_mapping(sequence_id, order)
    if not mapping:
        return result
    native_of = {stable: native for native, stable in mapping.items()}
    for key in ("objects", "prolog", "group_layers", "opencv", "repeated_shapes"):
        if result.get(key) is not None:
            result[key] = _relabel_value(result[key], mapping)
    for obj in result.get("objects") or []:
        obj["nativeId"] = native_of.get(obj["id"], obj["id"])
    for artifact in result.get("artifacts") or []:
        if isinstance(artifact.get("content"), str):
            artifact["content"] = _relabel_text(artifact["content"], mapping)
    if isinstance(result.get("metta"), dict) and isinstance(result["metta"].get("content"), str):
        result["metta"]["content"] = _relabel_text(result["metta"]["content"], mapping)
    prolog = result.get("prolog")
    if isinstance(prolog, dict):
        for key in ("facts", "group_facts", "turtle_facts"):
            if isinstance(prolog.get(key), str):
                prolog[key] = _relabel_text(prolog[key], mapping)
    result["stable_ids"] = mapping
    return result


# --- input/output contract -------------------------------------------------------------------
# RESERVED INPUTS are the recording's source evidence. The pipeline NEVER writes or deletes
# them. GENERATED names are the only files this pipeline creates; any cleanup must remove
# only names matching the generated manifest and must leave everything else untouched.

RESERVED_INPUTS = ("image.png", "image.jpg", "image.jpeg", "state.json")

_GENERATED_NAMES = ("regions.pl", "groups.pl", "acceptance.pl", "turtles.pl", "context.pl",
                    "geometry.json", "recognition.json", "deductions.pl",
                    "induction.json", "induction.metta")
_GENERATED_PATTERNS = (re.compile(r"^frame-[A-Za-z0-9_.-]+\.metta$"),
                       re.compile(r"^(regions|groups|acceptance|turtles|context|deductions)\.metta$"))


def is_reserved_input(path: Path) -> bool:
    return path.name.lower() in RESERVED_INPUTS


def is_generated(path: Path) -> bool:
    """True only for files this pipeline itself produces. Reserved inputs are never generated."""
    if is_reserved_input(path):
        return False
    name = path.name
    return name in _GENERATED_NAMES or any(p.match(name) for p in _GENERATED_PATTERNS)


def clean_generated(recording: Path, *, dry_run: bool = True) -> list[Path]:
    """Delete (or list, when dry_run) ONLY the files this pipeline generated in a recording.

    Never touches reserved inputs (image.png/.jpg, state.json), documentation, or any file
    the pipeline did not produce. Directories are never removed.
    """
    victims = [p for p in sorted(recording.rglob("*")) if p.is_file() and is_generated(p)]
    if not dry_run:
        for path in victims:
            path.unlink()
    return victims


def _frame_context(frame_dir: Path) -> dict:
    """Scalar input evidence from the frame's reserved state.json (commands, level, game state)."""
    state_path = frame_dir / "state.json"
    if not state_path.is_file():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(state, dict):
        return {}
    return {key: value for key, value in state.items()
            if isinstance(key, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key)
            and (isinstance(value, (str, bool)) or type(value) in (int, float))}


# --- output writing ------------------------------------------------------------------------

def _lf(text: str) -> bytes:
    """Normalise any line endings to LF and encode as UTF-8 bytes (never CRLF, on any platform)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _write(path: Path, text: str) -> bool:
    """Write LF-normalised bytes only when the on-disk bytes differ; return True when (re)written.

    Byte comparison (not text) so a file that is currently CRLF is rewritten as LF even when its
    decoded text is unchanged -- this heals any pre-existing CRLF outputs on the next pass.
    """
    if is_reserved_input(path):
        raise ValueError(f"Refusing to overwrite reserved input {path.name}; "
                         "image.* and state.json are source evidence, never pipeline output.")
    data = _lf(text)
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def ensure_metta_sidecar(pl_path: Path) -> tuple[Path, bool, list]:
    """Guarantee a .metta next to a .pl (Python conversion only). Returns (path, wrote, diagnostics)."""
    metta_path = pl_path.with_suffix(".metta")
    analysis = analyze_source({"name": pl_path.name, "text": pl_path.read_text(encoding="utf-8")})
    wrote = _write(metta_path, analysis["formats"]["metta"])
    return metta_path, wrote, analysis["diagnostics"]


def _trim_result(result: dict) -> dict:
    """Drop heavy base64 image blobs before persisting recognition.json."""
    return {key: value for key, value in result.items() if key not in ("preview", "debug_image")}


# --- inductive guesses ---------------------------------------------------------------------

def _tv(positives: int, total: int) -> dict:
    """NARS/PLN-style truth value from counted evidence: strength is the positive-evidence
    ratio, confidence grows with total evidence (evidential horizon k = 1)."""
    strength = positives / total if total else 0.0
    return {"strength": round(strength, 4), "confidence": round(total / (total + 1), 4),
            "positives": positives, "negatives": total - positives}


def induce(transitions: list[dict]) -> dict:
    """Generalise per-transition observations into inductive hypotheses about the sequence.

    Every guess carries counted evidence and a truth value: strength = share of
    observations supporting the pattern, confidence = evidence volume n/(n+1).
    Contradicting observations lower strength instead of silently discarding the guess.
    """
    from collections import Counter
    vectors: dict[str, Counter] = {}
    seen: dict[str, int] = {}
    events: dict[str, int] = {}
    for step in transitions:
        for match in step.get("matches", []):
            entity = match.get("current")
            if entity is None:
                continue
            seen[entity] = seen.get(entity, 0) + 1
            vectors.setdefault(entity, Counter())[(match.get("dx", 0), match.get("dy", 0))] += 1
        for appeared in step.get("appeared", []):
            events["appeared"] = events.get("appeared", 0) + 1
            if appeared.get("revealedFrom"):
                events["revealed"] = events.get("revealed", 0) + 1
        for gone in step.get("disappeared", []):
            events["disappeared"] = events.get("disappeared", 0) + 1
            if gone.get("occludedBy"):
                events["occluded"] = events.get("occluded", 0) + 1

    guesses = []
    for entity in sorted(vectors):
        counts = vectors[entity]
        total = sum(counts.values())
        (dom_vec, dom_count), = counts.most_common(1)
        tv = _tv(dom_count, total)
        if dom_vec == (0, 0):
            guesses.append({"kind": "static", "entity": entity, "support": total, "tv": tv,
                            **({"exceptions": sorted(v for v in counts if v != (0, 0))}
                               if len(counts) > 1 else {})})
        elif len(counts) == 1:
            guesses.append({"kind": "constant_velocity", "entity": entity,
                            "dx": dom_vec[0], "dy": dom_vec[1], "support": total, "tv": tv})
        else:
            guesses.append({"kind": "variable_motion", "entity": entity,
                            "dominant": list(dom_vec), "vectors": sorted(counts),
                            "vectorCounts": {f"{dx},{dy}": count for (dx, dy), count in sorted(counts.items())},
                            "support": total, "tv": tv})
    total_transitions = len(transitions)
    recurring = [{"kind": "recurring_event", "event": name, "count": count,
                  "tv": _tv(min(count, total_transitions), total_transitions)}
                 for name, count in sorted(events.items()) if count >= 2]
    implications = _induce_implications(transitions)
    return {"guesses": guesses, "recurring": recurring, "implications": implications,
            "transitions": total_transitions}


def _induce_implications(transitions: list[dict]) -> list[dict]:
    """Induce implications BETWEEN event types from their co-occurrence across transitions.

    For every pair of observed event/relation/action types: same-transition implication
    A => B and next-transition implication A => B(t+1), each with a counted-evidence truth
    value (strength = P(B|A), confidence = n/(n+1) over occurrences of A). States are
    excluded (too common to be informative). Bounded to the strongest 40.
    """
    def type_key(event):
        if event.get("category") == "action":
            return f"user_input({(event.get('args') or ['?'])[0].strip(chr(34))})"
        return event.get("type")

    frames = []
    for step in transitions:
        kinds = {type_key(ev) for ev in step.get("events", [])
                 if ev.get("category") in ("event", "relation", "action")}
        frames.append(kinds)
    if len(frames) < 2:
        return []
    from collections import Counter
    occur: Counter = Counter()
    together: Counter = Counter()
    successive: Counter = Counter()
    for index, kinds in enumerate(frames):
        for a in kinds:
            occur[a] += 1
            for b in kinds:
                if a != b:
                    together[(a, b)] += 1
            if index + 1 < len(frames):
                for b in frames[index + 1]:
                    if a != b:
                        successive[(a, b)] += 1
    implications = []
    for (counter, delay) in ((together, 0), (successive, 1)):
        for (a, b), count in counter.items():
            n = occur[a]
            if n < 2:
                continue
            tv = _tv(count, n)
            if tv["strength"] < 0.5:
                continue
            implications.append({"kind": "implication", "antecedent": a, "consequent": b,
                                 "delay": delay, "support": n, "tv": tv})
    implications.sort(key=lambda item: (-item["tv"]["strength"] * item["tv"]["confidence"],
                                        item["antecedent"], item["consequent"], item["delay"]))
    return implications[:40]


def _render_induction(recording_id: str, induction: dict, sources: list[str],
                      history: list | None = None) -> dict:
    """Render the inductive summary as MeTTa, Prolog, and JSON (all guesses, never facts).

    Every guess carries tv(Strength, Confidence) from counted evidence. Prior induction
    revisions are preserved in the JSON history so beliefs stay historical, never erased.
    """
    def tv_of(item):
        tv = item.get("tv") or {}
        return tv.get("strength", 0.0), tv.get("confidence", 0.0)

    mt = ["; Inductive guesses across the whole sequence (predictions, not facts).",
          "; Every guess carries (tv strength confidence) from counted evidence.",
          f"; sequence: {recording_id}"]
    for source in sources:  # aggregation provenance per the include-from/into convention
        mt.append(f";;; (did (include-from {source}))")
    pl = ["% Inductive guesses across the whole sequence (predictions, not facts).",
          "% Every guess carries tv(Strength, Confidence) from counted evidence.",
          f"% sequence: {recording_id}"]
    for guess in induction["guesses"]:
        s, c = tv_of(guess)
        if guess["kind"] == "constant_velocity":
            e, dx, dy, n = guess["entity"], guess["dx"], guess["dy"], guess["support"]
            mt.append(f"(guess (constant-velocity {e} (dxy {dx} {dy})) (tv {s} {c}) (support {n}))")
            pl.append(f"guess(constant_velocity({e}, {dx}, {dy}), tv({s}, {c}), support({n})).")
        elif guess["kind"] == "static":
            e, n = guess["entity"], guess["support"]
            mt.append(f"(guess (static {e}) (tv {s} {c}) (support {n}))")
            pl.append(f"guess(static({e}), tv({s}, {c}), support({n})).")
        else:
            e, n = guess["entity"], guess["support"]
            dom = guess.get("dominant") or [0, 0]
            vecs = " ".join(f"(dxy {dx} {dy})" for dx, dy in guess["vectors"])
            mt.append(f"(guess (variable-motion {e} (dominant (dxy {dom[0]} {dom[1]})) ({vecs})) (tv {s} {c}) (support {n}))")
            pl.append(f"guess(variable_motion({e}, dominant({dom[0]}, {dom[1]})), tv({s}, {c}), support({n})).")
    for item in induction["recurring"]:
        s, c = tv_of(item)
        mt.append(f"(guess (recurring-event {item['event']} (count {item['count']})) (tv {s} {c}))")
        pl.append(f"guess(recurring_event({item['event']}, {item['count']}), tv({s}, {c})).")
    for imp in induction.get("implications", []):
        s, c = tv_of(imp)
        a, b, delay, n = imp["antecedent"], imp["consequent"], imp["delay"], imp["support"]
        when = "same_frame" if delay == 0 else "next_frame"
        mt.append(f"(guess (implies {a.replace('_', '-').replace('(', ' ').replace(')', '')} "
                  f"{b.replace('_', '-').replace('(', ' ').replace(')', '')} ({when.replace('_', '-')})) (tv {s} {c}) (support {n}))")
        pl.append(f"guess(implies({a}, {b}, {when}), tv({s}, {c}), support({n})).")
    if history:
        mt.append(f"; {len(history)} earlier induction revisions kept in induction.json")
        pl.append(f"% {len(history)} earlier induction revisions kept in induction.json")
    payload = {"sequence": recording_id, **induction, "includeFrom": sources,
               "history": history or []}
    return {
        "induction.metta": "\n".join(mt) + "\n",
        "induction.pl": "\n".join(pl) + "\n",
        "induction.json": json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
    }


def _induction_history(recording: Path, induction: dict) -> list:
    """Prior induction revisions, kept historical: the previous file's beliefs are appended
    as a compact revision (entity/kind/tv/support) whenever the new beliefs differ. Bounded
    to the most recent 12 revisions; nothing is ever silently rewritten away."""
    previous_path = recording / "induction.json"
    if not previous_path.is_file():
        return []
    try:
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(previous, dict):
        return []
    history = previous.get("history") if isinstance(previous.get("history"), list) else []

    def digest(block: dict) -> list:
        entries = []
        for guess in block.get("guesses") or []:
            tv = guess.get("tv") or {}
            entries.append({"kind": guess.get("kind"), "entity": guess.get("entity"),
                            "support": guess.get("support"),
                            "tv": [tv.get("strength"), tv.get("confidence")]})
        for item in block.get("recurring") or []:
            tv = item.get("tv") or {}
            entries.append({"kind": "recurring_event", "event": item.get("event"),
                            "count": item.get("count"),
                            "tv": [tv.get("strength"), tv.get("confidence")]})
        for imp in block.get("implications") or []:
            tv = imp.get("tv") or {}
            entries.append({"kind": "implication", "antecedent": imp.get("antecedent"),
                            "consequent": imp.get("consequent"), "delay": imp.get("delay"),
                            "support": imp.get("support"),
                            "tv": [tv.get("strength"), tv.get("confidence")]})
        return entries

    if digest(previous) == digest(induction):
        return history
    revision = {"inducedAt": previous.get("inducedAt"),
                "transitions": previous.get("transitions"),
                "beliefs": digest(previous)}
    return (history + [revision])[-12:]


INCLUDE_INTO_PREFIX = ";;; (did (include-into "


def _mark_included_into(path: Path, target_rel: str) -> None:
    """Idempotently record on a source .metta that it was aggregated into `target_rel`."""
    marker = f"{INCLUDE_INTO_PREFIX}{target_rel}))"
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    path.write_bytes(_lf(marker + "\n" + text))


# --- per-recording processing --------------------------------------------------------------

def process_recording(recording: Path, *, pipeline: str = "prolog", stamp_epoch: float | None = None,
                      force: bool = False) -> dict:
    """Run every frame, persist outputs next to each frame, ensure .metta sidecars, and induce.

    A frame is (re)processed when forced, when its outputs are missing, or when any output is
    older than `stamp_epoch` (the crawler's source-freshness clock). Returns a record listing the
    produced files, per-frame errors, and the inductive summary.
    """
    if pipeline not in ("prolog", "opencv"):
        raise ValueError("pipeline must be 'prolog' or 'opencv'.")
    recordings_root = recording
    while recordings_root.name != "recordings" and recordings_root.parent != recordings_root:
        recordings_root = recordings_root.parent
    recording_id = recording.relative_to(recordings_root.parent).as_posix()

    frames = frame_dirs(recording)
    produced: list[dict] = []
    errors: list[dict] = []
    transitions: list[dict] = []
    prev_result = None
    prev_order = None
    prev_raw = None
    known_entities: set = set()
    prev_velocities: dict = {}
    metta_sources: list[str] = []

    def _needs(paths: list[Path]) -> bool:
        if force:
            return True
        for path in paths:
            if not path.exists():
                return True
            if stamp_epoch is not None and path.stat().st_mtime < stamp_epoch:
                return True
        return False

    for order, frame_dir in enumerate(frames):
        frame_id = frame_dir.name
        context = _frame_context(frame_dir)
        expected = [frame_dir / name for name in (
            "regions.pl", "groups.pl", "acceptance.pl", "turtles.pl",
            f"frame-{frame_id}.metta", "geometry.json", "recognition.json")]
        if context:
            expected.append(frame_dir / "context.pl")
        try:
            result = run_pipeline({"pipeline": pipeline, "image": {"base64": _image_b64(frame_dir)},
                                   "frame": {"sequenceId": recording_id, "frameId": frame_id},
                                   "context": context})
        except Exception as error:  # keep crawling the rest of the sequence
            errors.append({"frame": frame_id, "stage": "recognize", "error": str(error)})
            prev_result, prev_order, prev_raw = None, None, None
            continue

        # Keep the raw per-frame view for the deducer (it applies the tracker map itself),
        # then persist and display clip-stable e# identities everywhere else.
        raw = {"objects": [dict(obj) for obj in result["objects"]],
               "G": _group_members(result, "G"), "W": _group_members(result, "W")}
        try:
            stabilize_result(result, recording_id, order)
        except Exception as error:
            errors.append({"frame": frame_id, "stage": "stabilize", "error": str(error)})

        wrote_any = _needs(expected)
        if wrote_any:
            for artifact in result["artifacts"]:
                if _write(frame_dir / artifact["name"], artifact["content"]):
                    produced.append({"recording": recording_id, "frame": frame_id,
                                     "file": (frame_dir / artifact["name"]).as_posix(),
                                     "kind": Path(artifact["name"]).suffix.lstrip(".")})
            _write(frame_dir / "recognition.json",
                   json.dumps(_trim_result(result), ensure_ascii=True, indent=2) + "\n")
            produced.append({"recording": recording_id, "frame": frame_id,
                             "file": (frame_dir / "recognition.json").as_posix(), "kind": "json"})

        # Cross-frame deductions vs the previous frame (stable e# identities).
        # The frame before frame 0 is a virtual EMPTY frame at order -1, so every
        # object in the first frame is deduced as an appearance.
        if prev_result is not None or order == 0:
            if prev_result is not None:
                previous_payload = {"objects": prev_raw["objects"]}
                previous_groups = {"G": prev_raw["G"], "W": prev_raw["W"]}
                previous_order = prev_order
            else:
                previous_payload = {"objects": []}
                previous_groups = {"G": [], "W": []}
                previous_order = -1
            try:
                deduced = deduce2_from_payload({
                    "sequenceId": recording_id,
                    "current": {"objects": raw["objects"]},
                    "previous": previous_payload,
                    "currentGroups": {"G": raw["G"], "W": raw["W"]},
                    "previousGroups": previous_groups,
                    "currentOrder": order, "previousOrder": previous_order,
                    "width": result["width"], "height": result["height"],
                    "userAction": context.get("incoming_action"),
                    "history": {"knownEntities": sorted(known_entities),
                                "previousVelocities": prev_velocities},
                })
                transitions.append(deduced)
                # Feed the next transition's cross-frame detectors (bounce, start/end,
                # reappeared): current velocities and every stable entity seen so far.
                prev_velocities = {m["current"]: [m["dx"], m["dy"]] for m in deduced.get("matches", [])}
                known_entities.update(prev_velocities)
                known_entities.update(a["current"] for a in deduced.get("appeared", []))
                if wrote_any or _needs([frame_dir / "deductions.pl", frame_dir / "deductions.metta"]):
                    for artifact in deduced.get("files", []):
                        if _write(frame_dir / artifact["name"], artifact["content"]):
                            produced.append({"recording": recording_id, "frame": frame_id,
                                             "file": (frame_dir / artifact["name"]).as_posix(),
                                             "kind": Path(artifact["name"]).suffix.lstrip(".")})
            except Exception as error:
                errors.append({"frame": frame_id, "stage": "deduce", "error": str(error)})

        prev_result, prev_order, prev_raw = result, order, raw

        # Guarantee a .metta sidecar for every .pl in this frame directory.
        for pl_path in sorted(frame_dir.glob("*.pl")):
            try:
                metta_path, wrote, diagnostics = ensure_metta_sidecar(pl_path)
                metta_sources.append(metta_path.relative_to(recording).as_posix())
                if wrote:
                    produced.append({"recording": recording_id, "frame": frame_id,
                                     "file": metta_path.as_posix(), "kind": "metta",
                                     "from": pl_path.name,
                                     "diagnostics": [d for d in diagnostics if d["severity"] == "error"]})
            except Exception as error:
                errors.append({"frame": frame_id, "stage": "metta-sidecar",
                               "file": pl_path.name, "error": str(error)})

    # Inductive guesses across the whole sequence, with counted-evidence truth values and
    # the prior revision preserved in the historical record.
    induction = induce(transitions)
    induction["inducedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    history = _induction_history(recording, induction)
    rendered = _render_induction(recording_id, induction, sorted(set(metta_sources)), history)
    for name, text in rendered.items():
        path = recording / name
        if _write(path, text):
            produced.append({"recording": recording_id, "frame": None,
                             "file": path.as_posix(), "kind": Path(name).suffix.lstrip(".")})
    # Record the reverse include-into marker on each aggregated source .metta.
    for rel in sorted(set(metta_sources)):
        try:
            _mark_included_into(recording / rel, "../induction.metta")
        except OSError:
            continue

    return {"recording": recording_id, "path": recording.as_posix(), "frames": len(frames),
            "produced": produced, "errors": errors, "induction": induction}
