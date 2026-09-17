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
    prior_predictions = payload.get("predictions") if isinstance(payload.get("predictions"), list) else None
    beliefs = payload.get("beliefs") if isinstance(payload.get("beliefs"), list) else None
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
                                 user_action=user_action, history=history,
                                 predictions=prior_predictions, beliefs=beliefs)
    return deduce_two_frames(current, previous, user_action=user_action, history=history,
                             predictions=prior_predictions, beliefs=beliefs)


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

RESERVED_INPUTS = ("image.png", "image.jpg", "image.jpeg", "state.json", "recording.json")

_GENERATED_NAMES = ("regions.pl", "groups.pl", "acceptance.pl", "turtles.pl", "context.pl",
                    "geometry.json", "recognition.json", "deductions.pl", "beliefs.json",
                    "induction.json", "induction.metta", "induction.pl")
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

def _event_type_key(event: dict) -> str:
    """Canonical type key for implication mining and prediction matching."""
    if event.get("category") == "action":
        return f"user_input({(event.get('args') or ['?'])[0].strip(chr(34))})"
    return event.get("type")


def _load_priors(recording: Path) -> dict:
    """Prior beliefs from the previous pass: the LAST frame's induction.json (induction only
    ever lives under frame dirs). Falls back to legacy locations (frame beliefs.json, then
    the old recording-root induction.json) so older stores keep working."""
    frame_dirs_sorted = sorted((child for child in recording.iterdir()
                                if child.is_dir() and child.name.isdigit()),
                               key=lambda path: int(path.name), reverse=True)
    candidates = [frame / name for frame in frame_dirs_sorted
                  for name in ("induction.json", "beliefs.json")]
    candidates.append(recording / "induction.json")  # legacy root layout
    for path in candidates:
        if not path.is_file():
            continue
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(prior, dict):
            return prior
    return {}


def _predict_next(priors: dict, events: list, matched_ids: set) -> list:
    """Predictions for the NEXT transition from prior beliefs and this transition's events.

    * next-frame implications: antecedent observed now => predict the consequent.
    * per-entity motion beliefs: constant_velocity => moved(e); static => stationary(e).
    Only beliefs with strength >= 0.6 predict; user input is never predicted.
    """
    predictions = []
    seen = set()

    def add(event, entity, source, tv):
        key = (event, entity)
        if key in seen or not tv or tv.get("strength", 0) < 0.6:
            return
        seen.add(key)
        predictions.append({"event": event, "entity": entity, "source": source,
                            "tv": {"strength": tv.get("strength"), "confidence": tv.get("confidence")}})

    kinds = {_event_type_key(ev) for ev in events
             if ev.get("category") in ("event", "relation", "action")}
    entity_events = [(ev["type"], ev["args"][0]) for ev in events
                     if ev.get("category") in ("event", "relation") and ev.get("args")]
    for imp in priors.get("implications") or []:
        if imp.get("delay") != 1:
            continue
        consequent = imp.get("consequent") or ""
        if consequent.startswith("user_input("):
            continue  # never predict the user's own input
        if imp.get("binding") == "entity":
            # DEDUCTION, entity-bound: A(e) observed now => predict B(e) next frame.
            for (etype, entity) in entity_events:
                if etype == imp.get("antecedent"):
                    add(consequent, entity,
                        f"implies({imp['antecedent']},{consequent},next_frame,entity)", imp.get("tv"))
            continue
        if imp.get("antecedent") not in kinds:
            continue
        source = f"implies({imp['antecedent']},{consequent},next_frame)"
        if imp.get("derived"):
            source += f",derived_via({imp.get('via', '?')})"
        add(consequent, None, source, imp.get("tv"))
    for guess in priors.get("guesses") or []:
        entity = guess.get("entity")
        if entity not in matched_ids:
            continue
        if guess.get("kind") == "constant_velocity":
            add("moved", entity, "constant_velocity", guess.get("tv"))
        elif guess.get("kind") == "static":
            add("stationary", entity, "static", guess.get("tv"))
    return predictions


def _tv(positives: int, total: int) -> dict:
    """NARS/PLN-style truth value from counted evidence: strength is the positive-evidence
    ratio, confidence grows with total evidence (evidential horizon k = 1)."""
    strength = positives / total if total else 0.0
    return {"strength": round(strength, 4), "confidence": round(total / (total + 1), 4),
            "positives": positives, "negatives": total - positives}


def induce(transitions: list[dict], priors: dict | None = None) -> dict:
    """Generalise per-transition observations into inductive hypotheses about the sequence.

    Every guess carries counted evidence and a truth value: strength = share of
    observations supporting the pattern, confidence = evidence volume n/(n+1).
    Contradicting observations lower strength instead of silently discarding the guess.
    Prior beliefs (the previous induction pass) pool their implication evidence into the
    new counts, and every prediction they issued is scored into predictionOutcomes.
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
    implications = _induce_implications(transitions, priors)
    outcomes = [p for step in transitions for p in step.get("predictions", [])]
    confirmed = sum(1 for p in outcomes if p.get("outcome") == "confirmed")
    prediction_outcomes = {"tested": len(outcomes), "confirmed": confirmed,
                           "accuracy": round(confirmed / len(outcomes), 4) if outcomes else None}
    # Aggregate the per-transition abduced explanations into ranked abducibles.
    abduced: dict = {}
    for step in transitions:
        for h in step.get("abductions", []):
            key = (h.get("hypothesis"), h.get("explains"), h.get("when"))
            entry = abduced.setdefault(key, {"count": 0, "tv": h.get("tv") or {}})
            entry["count"] += 1
    abductions = [{"kind": "abduction", "hypothesis": a, "explains": b, "when": when,
                   "count": entry["count"], "tv": entry["tv"]}
                  for (a, b, when), entry in abduced.items()]
    abductions.sort(key=lambda item: (-item["count"], item["hypothesis"]))
    return {"guesses": guesses, "recurring": recurring, "implications": implications,
            "abductions": abductions[:30],
            "predictionOutcomes": prediction_outcomes, "transitions": total_transitions}


def _induce_implications(transitions: list[dict], priors: dict | None = None) -> list[dict]:
    """Induce implications BETWEEN event types from their co-occurrence across transitions.

    For every pair of observed event/relation/action types: same-transition implication
    A => B and next-transition implication A => B(t+1), each with a counted-evidence truth
    value (strength = P(B|A), confidence = n/(n+1) over occurrences of A). States are
    excluded (too common to be informative). PRIOR beliefs pool their evidence into the
    new counts (bounded per pair), so beliefs accumulate across crawler passes instead of
    resetting. Bounded to the strongest 40.
    """
    frames = []
    for step in transitions:
        kinds = {_event_type_key(ev) for ev in step.get("events", [])
                 if ev.get("category") in ("event", "relation", "action")}
        frames.append(kinds)
    if len(frames) < 2:
        return []
    from collections import Counter
    occur: Counter = Counter()
    together: Counter = Counter()
    successive: Counter = Counter()
    occur_frames: dict = {}
    together_frames: dict = {}
    successive_frames: dict = {}
    for index, kinds in enumerate(frames):
        for a in kinds:
            occur[a] += 1
            occur_frames.setdefault(a, []).append(index)
            for b in kinds:
                if a != b:
                    together[(a, b)] += 1
                    together_frames.setdefault((a, b), []).append(index)
            if index + 1 < len(frames):
                for b in frames[index + 1]:
                    if a != b:
                        successive[(a, b)] += 1
                        successive_frames.setdefault((a, b), []).append(index)
    # Prior evidence pooling: the previous pass's counted evidence joins this pass's,
    # capped per pair so no single history dominates forever. Derived (deduced) rules
    # never pool as observational evidence.
    prior_evidence = {}
    for imp in (priors or {}).get("implications") or []:
        if imp.get("derived"):
            continue
        tv = imp.get("tv") or {}
        pos, neg = tv.get("positives"), tv.get("negatives")
        if type(pos) is int and type(neg) is int:
            key = (imp.get("antecedent"), imp.get("consequent"), imp.get("delay"),
                   imp.get("binding"))
            prior_evidence[key] = (min(pos, 100), min(pos + neg, 100))
    implications = []
    total_frames = len(frames)
    for (counter, count_frames, delay) in ((together, together_frames, 0),
                                           (successive, successive_frames, 1)):
        for (a, b), count in counter.items():
            n = occur[a]
            if n < 2:
                continue
            base_rate = occur[b] / total_frames
            prior_pos, prior_n = prior_evidence.get((a, b, delay, None), (0, 0))
            tv = _tv(count + prior_pos, n + prior_n)
            # Informativeness gates: the consequent must not be near-universal (base rate),
            # knowing A must actually raise the odds of B (lift), and user input is never a
            # consequent (it is exogenous; the interesting direction is user_input => effect).
            if (tv["strength"] < 0.5 or base_rate >= 0.95 or tv["strength"] < base_rate * 1.2
                    or b.startswith("user_input(")):
                continue
            implications.append({"kind": "implication", "antecedent": a, "consequent": b,
                                 "delay": delay, "support": n + prior_n,
                                 "lift": round(tv["strength"] / base_rate, 2) if base_rate else None,
                                 "tv": tv,
                                 "evidence": {
                                     "antecedentFrames": sorted(set(occur_frames.get(a, [])))[:20],
                                     "supportFrames": sorted(set(count_frames.get((a, b), [])))[:20],
                                     "misses": n - count,
                                     "consequentBaseRate": round(base_rate, 4),
                                     "priorEvidence": [prior_pos, prior_n],
                                 }})
    # ENTITY-BOUND induction: A(e) => B(e) for the same entity, a sharper causal rule than
    # type-level co-occurrence (e.g. collision(e) => bounce(e), not just collision => bounce).
    entity_frames = []
    for step in transitions:
        bound = set()
        for ev in step.get("events", []):
            if ev.get("category") in ("event", "relation") and ev.get("args"):
                bound.add((ev["type"], ev["args"][0]))
        entity_frames.append(bound)
    e_occur: Counter = Counter()
    e_together: Counter = Counter()
    e_successive: Counter = Counter()
    e_occur_frames: dict = {}
    e_together_frames: dict = {}
    e_successive_frames: dict = {}
    e_witnesses: dict = {}
    for index, bound in enumerate(entity_frames):
        for (ta, ea) in bound:
            e_occur[ta] += 1
            e_occur_frames.setdefault(ta, []).append(index)
            for (tb, eb) in bound:
                if ea == eb and ta != tb:
                    e_together[(ta, tb)] += 1
                    e_together_frames.setdefault((ta, tb), []).append(index)
                    e_witnesses.setdefault((ta, tb, 0), set()).add(ea)
            if index + 1 < len(entity_frames):
                for (tb, eb) in entity_frames[index + 1]:
                    if ea == eb and ta != tb:
                        e_successive[(ta, tb)] += 1
                        e_successive_frames.setdefault((ta, tb), []).append(index)
                        e_witnesses.setdefault((ta, tb, 1), set()).add(ea)
    for (counter, count_frames, delay) in ((e_together, e_together_frames, 0),
                                           (e_successive, e_successive_frames, 1)):
        for (a, b), count in counter.items():
            n = e_occur[a]
            if n < 2:
                continue
            base_rate = occur.get(b, 0) / total_frames
            prior_pos, prior_n = prior_evidence.get((a, b, delay, "entity"), (0, 0))
            tv = _tv(count + prior_pos, n + prior_n)
            if (tv["strength"] < 0.5 or base_rate >= 0.95 or tv["strength"] < base_rate * 1.2
                    or b.startswith("user_input(")):
                continue
            implications.append({"kind": "implication", "antecedent": a, "consequent": b,
                                 "delay": delay, "binding": "entity",
                                 "support": n + prior_n,
                                 "lift": round(tv["strength"] / base_rate, 2) if base_rate else None,
                                 "tv": tv,
                                 "evidence": {
                                     "antecedentFrames": sorted(set(e_occur_frames.get(a, [])))[:20],
                                     "supportFrames": sorted(set(count_frames.get((a, b), [])))[:20],
                                     "misses": n - count,
                                     "consequentBaseRate": round(base_rate, 4),
                                     "priorEvidence": [prior_pos, prior_n],
                                     "witnesses": sorted(e_witnesses.get((a, b, delay), set()))[:8],
                                 }})
    implications.sort(key=lambda item: (-item["tv"]["strength"] * item["tv"]["confidence"],
                                        item["antecedent"], item["consequent"], item["delay"]))
    # De-noise: definitional tautologies, duplicate bindings, and mirrored pairs.
    # 1. A detector-entailed consequent is no discovery (attached is DEFINED as persisting
    #    contact; bounce is DEFINED over moving entities; formation EMITS member_added).
    definitional = {
        "attached": {"contact"}, "carry": {"attached", "contact", "co_move", "moved"},
        "collision": {"contact"}, "blocked": {"contact"},
        "group_formed": {"member_added"}, "member_added": {"group_formed"},
        "group_dissolved": {"member_removed"}, "member_removed": {"group_dissolved"},
        "scaled": {"area_changed"}, "deformed": {"shape_changed"},
        "bounce": {"moved"}, "turned": {"moved"}, "continue": {"moved"},
        "accelerated": {"moved"}, "decelerated": {"moved"}, "start": {"moved"},
        "entered": {"appeared"},
    }
    implications = [imp for imp in implications
                    if imp["consequent"] not in definitional.get(imp["antecedent"], ())]
    # 2. The sharper entity-bound rule supersedes its type-level duplicate.
    entity_keys = {(imp["antecedent"], imp["consequent"], imp["delay"])
                   for imp in implications if imp.get("binding") == "entity"}
    implications = [imp for imp in implications if imp.get("binding") == "entity"
                    or (imp["antecedent"], imp["consequent"], imp["delay"]) not in entity_keys]
    # 3. Mirrored pairs (A=>B and B=>A) keep only the more informative direction.
    best: dict = {}
    for imp in implications:
        key = (frozenset((imp["antecedent"], imp["consequent"])), imp["delay"], imp.get("binding"))
        current = best.get(key)
        rank = ((imp.get("lift") or 0), imp["tv"]["strength"], imp["tv"]["confidence"])
        if current is None or rank > ((current.get("lift") or 0), current["tv"]["strength"], current["tv"]["confidence"]):
            best[key] = imp
    implications = sorted(best.values(),
                          key=lambda item: (-item["tv"]["strength"] * item["tv"]["confidence"],
                                            item["antecedent"], item["consequent"], item["delay"]))
    implications = implications[:60]
    # DEDUCTION chains (syllogism): strong A=>B and B=>C derive A=>C with NARS-style
    # composed truth (s = sA*sB, discounted confidence). Derived rules predict but never
    # pool back as observational evidence.
    implications.extend(_derive_chains(implications))
    return implications


def _derive_chains(implications: list[dict]) -> list[dict]:
    strong = [imp for imp in implications
              if not imp.get("derived") and not imp.get("binding")
              and imp["tv"]["strength"] >= 0.8 and imp["tv"]["confidence"] >= 0.7]
    existing = {(imp["antecedent"], imp["consequent"], imp["delay"]) for imp in implications}
    derived = []
    for first in strong:
        for second in strong:
            if first["consequent"] != second["antecedent"]:
                continue
            a, c = first["antecedent"], second["consequent"]
            delay = first["delay"] + second["delay"]
            if a == c or delay > 1 or (a, c, delay) in existing:
                continue
            tv1, tv2 = first["tv"], second["tv"]
            strength = round(tv1["strength"] * tv2["strength"], 4)
            confidence = round(tv1["confidence"] * tv2["confidence"] * 0.9, 4)
            if strength < 0.5:
                continue
            derived.append({"kind": "implication", "antecedent": a, "consequent": c,
                            "delay": delay, "support": min(first["support"], second["support"]),
                            "derived": "deduction",
                            "via": first["consequent"],
                            "evidence": {
                                "premise1": f"{first['antecedent']}=>{first['consequent']} (delay {first['delay']}) tv {tv1['strength']}/{tv1['confidence']}",
                                "premise2": f"{second['antecedent']}=>{second['consequent']} (delay {second['delay']}) tv {tv2['strength']}/{tv2['confidence']}",
                                "rule": "NARS deduction: s=s1*s2, c=c1*c2*0.9",
                            },
                            "tv": {"strength": strength, "confidence": confidence,
                                   "positives": 0, "negatives": 0}})
            existing.add((a, c, delay))
    derived.sort(key=lambda item: -item["tv"]["strength"] * item["tv"]["confidence"])
    return derived[:20]


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
        binding = ", entity_bound" if imp.get("binding") == "entity" else ""
        derived = f", derived(deduction, via({imp['via']}))" if imp.get("derived") else ""
        mt.append(f"(guess (implies {a.replace('_', '-').replace('(', ' ').replace(')', '')} "
                  f"{b.replace('_', '-').replace('(', ' ').replace(')', '')} ({when.replace('_', '-')}"
                  f"{' entity-bound' if imp.get('binding') == 'entity' else ''}"
                  f"{' derived' if imp.get('derived') else ''})) (tv {s} {c}) (support {n}))")
        pl.append(f"guess(implies({a}, {b}, {when}{binding}{derived}), tv({s}, {c}), support({n})).")
        why = imp.get("evidence") or {}
        if imp.get("derived"):
            reason = f"deduced from [{why.get('premise1')}] and [{why.get('premise2')}] by {why.get('rule')}"
        else:
            hits = why.get("supportFrames", [])
            reason = (f"{a} observed at transitions {why.get('antecedentFrames', [])}; "
                      f"{b} followed at {hits} ({len(hits)} hits, {why.get('misses', 0)} misses); "
                      f"base rate of {b} = {why.get('consequentBaseRate')}, lift {imp.get('lift')}; "
                      f"prior evidence {why.get('priorEvidence')}")
            witnesses = why.get("witnesses")
            if witnesses:
                reason += f"; witnessed by entities {witnesses}"
        pl.append(f"%   why: {reason}")
        mt.append(f"; why: {reason}")
    for h in induction.get("abductions", []):
        s, c = tv_of(h)
        mt.append(f"(guess (abducible {h['hypothesis'].replace('_', '-')} (explains {h['explains'].replace('_', '-')}) "
                  f"(when {h['when'].replace('_', '-')})) (tv {s} {c}) (count {h['count']}))")
        pl.append(f"guess(abducible({h['hypothesis']}, explains({h['explains']}), when({h['when']})), tv({s}, {c}), count({h['count']})).")
    outcomes = induction.get("predictionOutcomes") or {}
    if outcomes.get("tested"):
        mt.append(f"(prediction-outcomes (tested {outcomes['tested']}) (confirmed {outcomes['confirmed']}) (accuracy {outcomes['accuracy']}))")
        pl.append(f"prediction_outcomes({outcomes['tested']}, {outcomes['confirmed']}, {outcomes['accuracy']}).")
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
                            "binding": imp.get("binding"), "derived": imp.get("derived"),
                            "support": imp.get("support"),
                            "tv": [tv.get("strength"), tv.get("confidence")]})
        for h in block.get("abductions") or []:
            tv = h.get("tv") or {}
            entries.append({"kind": "abduction", "hypothesis": h.get("hypothesis"),
                            "explains": h.get("explains"), "when": h.get("when"),
                            "count": h.get("count"),
                            "tv": [tv.get("strength"), tv.get("confidence")]})
        return entries

    if digest(previous) == digest(induction):
        return history
    revision = {"inducedAt": previous.get("inducedAt"),
                "transitions": previous.get("transitions"),
                "predictionOutcomes": previous.get("predictionOutcomes"),
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
    pending_snapshot = None
    # Prior beliefs (previous induction pass) drive next-frame predictions and pool their
    # evidence into this pass's implications.
    priors = _load_priors(recording)
    pending_predictions: list = []
    prev_event_kinds: list = []
    # Strong observational beliefs feed per-transition abduction inside the deducer.
    abduction_beliefs = [imp for imp in priors.get("implications") or []
                         if not imp.get("binding") and not imp.get("derived")
                         and (imp.get("tv") or {}).get("strength", 0) >= 0.7][:30]
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
                                "previousVelocities": prev_velocities,
                                "previousEventKinds": prev_event_kinds},
                    "predictions": pending_predictions,
                    "beliefs": abduction_beliefs,
                })
                transitions.append(deduced)
                # Feed the next transition's cross-frame detectors (bounce, start/end,
                # reappeared): current velocities and every stable entity seen so far.
                prev_velocities = {m["current"]: [m["dx"], m["dy"]] for m in deduced.get("matches", [])}
                known_entities.update(prev_velocities)
                known_entities.update(a["current"] for a in deduced.get("appeared", []))
                prev_event_kinds = sorted({_event_type_key(ev) for ev in deduced.get("events", [])
                                           if ev.get("category") in ("event", "relation", "action")})
                # Issue next-frame predictions from prior beliefs given what just happened.
                pending_predictions = _predict_next(priors, deduced.get("events", []),
                                                    set(prev_velocities))
                # TUTORIAL belief snapshot: what has been induced from the transitions seen
                # SO FAR (no prior passes pooled in) - a student stepping to this frame sees
                # only beliefs whose evidence has already happened. Written after the
                # sidecar pass below as this frame's induction.json/.pl/.metta.
                snapshot = induce(transitions)
                snapshot["upto"] = order
                last_snapshot = snapshot
                pending_snapshot = snapshot
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
        frame_metta_sources = []
        for pl_path in sorted(frame_dir.glob("*.pl")):
            if pl_path.name == "induction.pl":
                continue  # induction is rendered below, never sidecar-converted
            try:
                metta_path, wrote, diagnostics = ensure_metta_sidecar(pl_path)
                metta_sources.append(metta_path.relative_to(recording).as_posix())
                frame_metta_sources.append(metta_path.name)
                if wrote:
                    produced.append({"recording": recording_id, "frame": frame_id,
                                     "file": metta_path.as_posix(), "kind": "metta",
                                     "from": pl_path.name,
                                     "diagnostics": [d for d in diagnostics if d["severity"] == "error"]})
            except Exception as error:
                errors.append({"frame": frame_id, "stage": "metta-sidecar",
                               "file": pl_path.name, "error": str(error)})

        # INDUCTION LIVES UNDER THE FRAME, never at the recording root: this frame's
        # induction.json/.pl/.metta hold the beliefs accumulated over transitions 0..N
        # (with per-frame revision history from earlier passes).
        if pending_snapshot is not None:
            snapshot = dict(pending_snapshot)
            snapshot["inducedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            history = _induction_history(frame_dir, snapshot)
            rendered = _render_induction(recording_id, snapshot, sorted(frame_metta_sources), history)
            for name, text in rendered.items():
                if _write(frame_dir / name, text):
                    produced.append({"recording": recording_id, "frame": frame_id,
                                     "file": (frame_dir / name).as_posix(),
                                     "kind": Path(name).suffix.lstrip(".")})
            for name in sorted(frame_metta_sources):
                try:
                    _mark_included_into(frame_dir / name, "induction.metta")
                except OSError:
                    continue
            legacy = frame_dir / "beliefs.json"  # superseded by frame-level induction.json
            if legacy.is_file() and is_generated(legacy):
                try:
                    legacy.unlink()
                except OSError:
                    pass
            pending_snapshot = None

    # No recording-root induction: knowledge only ever builds frame to frame, so the final
    # belief state is the LAST frame's induction files. Obsolete root-level induction
    # artifacts from earlier layouts are removed (they are our own generated files).
    for legacy in ("induction.json", "induction.pl", "induction.metta", "beliefs.json"):
        path = recording / legacy
        if path.is_file() and is_generated(path):
            try:
                path.unlink()
            except OSError:
                pass

    final_beliefs = dict(last_snapshot) if last_snapshot is not None else induce(transitions)
    return {"recording": recording_id, "path": recording.as_posix(), "frames": len(frames),
            "produced": produced, "errors": errors, "induction": final_beliefs}
