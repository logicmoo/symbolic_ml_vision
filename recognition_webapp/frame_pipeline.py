"""Headless per-recording processing shared by the web server and the standalone crawler.

Everything here is filesystem/Prolog/Python only: no JavaScript is involved in producing or
converting symbolic output. A recording is run frame-by-frame through the same pipeline the web
UI uses (recognition + cross-frame deductions), the results are written next to each frame as
Prolog/MeTTa/JSON, every ``.pl`` is guaranteed a ``.metta`` sidecar, and an inductive summary is
induced across the whole sequence.
"""

import base64
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
        relabel = lambda objs, m: [{**o, "id": m.get(o.get("id"), o.get("id")), "nativeId": o.get("id")} for o in objs]
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
                                 user_action=user_action)
    return deduce_two_frames(current, previous, user_action=user_action)


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

def induce(transitions: list[dict]) -> dict:
    """Generalise per-transition observations into inductive hypotheses about the sequence.

    Guesses (not certainties): entities with a single consistent motion vector across every
    transition they appear in, entities that never move, and events that recur.
    """
    vectors: dict[str, set] = {}
    seen: dict[str, int] = {}
    events: dict[str, int] = {}
    for step in transitions:
        for match in step.get("matches", []):
            entity = match.get("current")
            if entity is None:
                continue
            seen[entity] = seen.get(entity, 0) + 1
            vectors.setdefault(entity, set()).add((match.get("dx", 0), match.get("dy", 0)))
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
        vecs = vectors[entity]
        if len(vecs) == 1:
            dx, dy = next(iter(vecs))
            if dx == 0 and dy == 0:
                guesses.append({"kind": "static", "entity": entity, "support": seen[entity]})
            else:
                guesses.append({"kind": "constant_velocity", "entity": entity,
                                "dx": dx, "dy": dy, "support": seen[entity]})
        else:
            guesses.append({"kind": "variable_motion", "entity": entity,
                            "vectors": sorted(vecs), "support": seen[entity]})
    recurring = [{"kind": "recurring_event", "event": name, "count": count}
                 for name, count in sorted(events.items()) if count >= 2]
    return {"guesses": guesses, "recurring": recurring, "transitions": len(transitions)}


def _render_induction(recording_id: str, induction: dict, sources: list[str]) -> dict:
    """Render the inductive summary as MeTTa, Prolog, and JSON (all guesses, never facts)."""
    mt = ["; Inductive guesses across the whole sequence (predictions, not facts).",
          f"; sequence: {recording_id}"]
    for source in sources:  # aggregation provenance per the include-from/into convention
        mt.append(f";;; (did (include-from {source}))")
    pl = ["% Inductive guesses across the whole sequence (predictions, not facts).",
          f"% sequence: {recording_id}"]
    for guess in induction["guesses"]:
        if guess["kind"] == "constant_velocity":
            e, dx, dy, s = guess["entity"], guess["dx"], guess["dy"], guess["support"]
            mt.append(f"(guess (constant-velocity {e} (dxy {dx} {dy})) (support {s}))")
            pl.append(f"guess(constant_velocity({e}, {dx}, {dy}), support({s})).")
        elif guess["kind"] == "static":
            e, s = guess["entity"], guess["support"]
            mt.append(f"(guess (static {e}) (support {s}))")
            pl.append(f"guess(static({e}), support({s})).")
        else:
            e, s = guess["entity"], guess["support"]
            vecs = " ".join(f"(dxy {dx} {dy})" for dx, dy in guess["vectors"])
            mt.append(f"(guess (variable-motion {e} ({vecs})) (support {s}))")
            pl.append(f"guess(variable_motion({e}), support({s})).")
    for item in induction["recurring"]:
        mt.append(f"(guess (recurring-event {item['event']} (count {item['count']})))")
        pl.append(f"guess(recurring_event({item['event']}, {item['count']})).")
    payload = {"sequence": recording_id, **induction, "includeFrom": sources}
    return {
        "induction.metta": "\n".join(mt) + "\n",
        "induction.pl": "\n".join(pl) + "\n",
        "induction.json": json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
    }


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
            prev_result, prev_order = None, None
            continue

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
                previous_payload = {"objects": prev_result["objects"]}
                previous_groups = {"G": _group_members(prev_result, "G"), "W": _group_members(prev_result, "W")}
                previous_order = prev_order
            else:
                previous_payload = {"objects": []}
                previous_groups = {"G": [], "W": []}
                previous_order = -1
            try:
                deduced = deduce2_from_payload({
                    "sequenceId": recording_id,
                    "current": {"objects": result["objects"]},
                    "previous": previous_payload,
                    "currentGroups": {"G": _group_members(result, "G"), "W": _group_members(result, "W")},
                    "previousGroups": previous_groups,
                    "currentOrder": order, "previousOrder": previous_order,
                    "width": result["width"], "height": result["height"],
                    "userAction": context.get("incoming_action"),
                })
                transitions.append(deduced)
                if wrote_any or _needs([frame_dir / "deductions.pl", frame_dir / "deductions.metta"]):
                    for artifact in deduced.get("files", []):
                        if _write(frame_dir / artifact["name"], artifact["content"]):
                            produced.append({"recording": recording_id, "frame": frame_id,
                                             "file": (frame_dir / artifact["name"]).as_posix(),
                                             "kind": Path(artifact["name"]).suffix.lstrip(".")})
            except Exception as error:
                errors.append({"frame": frame_id, "stage": "deduce", "error": str(error)})

        prev_result, prev_order = result, order

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

    # Inductive guesses across the whole sequence.
    induction = induce(transitions)
    rendered = _render_induction(recording_id, induction, sorted(set(metta_sources)))
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
