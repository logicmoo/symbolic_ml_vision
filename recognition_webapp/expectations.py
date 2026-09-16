"""Human-only frame guidance from authored evaluation data, never pipeline input."""

import json
import re

from demos import DemoCatalog


def _color(value) -> str:
    if isinstance(value, list) and len(value) == 3 and all(type(channel) is int and 0 <= channel <= 255 for channel in value):
        return "#" + bytes(value).hex()
    return str(value)


def _position(value) -> str:
    return "(" + ", ".join(str(item) for item in value) + ")" if isinstance(value, list) else str(value)


def _objects(frame: dict) -> list[dict]:
    objects = []
    for obj in frame.get("authoredObjects", []):
        mask = obj.get("mask")
        size = [len(mask[0]), len(mask)] if isinstance(mask, list) and mask else obj.get("size")
        area = sum(row.count("1") for row in mask) if isinstance(mask, list) and mask else None
        position = obj.get("position")
        if position is None and "x" in obj and "y" in obj:
            position = [obj["x"], obj["y"]]
        objects.append({
            "entity": obj.get("entity", "unnamed"), "color": _color(obj.get("color")),
            "position": position, "size": size, "area": area, "visible": obj.get("visible"),
        })
    return objects


def _object_lines(frame: dict, previous: dict | None) -> tuple[list[str], list[str]]:
    before = {obj["entity"]: obj for obj in _objects(previous)} if previous else {}
    lines, changes = [], []
    for obj in _objects(frame):
        details = [obj["color"]]
        if obj["position"] is not None:
            details.append(f"at pixel {_position(obj['position'])}")
        if obj["size"] is not None:
            details.append(f"{obj['size'][0]} x {obj['size'][1]} extent")
        if obj["area"] is not None:
            details.append(f"{obj['area']} occupied pixels")
        if obj["visible"] is False:
            details.append("authored as not visible")
        elif obj["visible"] is True:
            details.append("authored as visible")
        lines.append(f"{obj['entity']}: " + "; ".join(details) + ".")
        old = before.get(obj["entity"])
        if old:
            delta = []
            if old["position"] != obj["position"]:
                delta.append(f"position {_position(old['position'])} to {_position(obj['position'])}")
            if old["size"] != obj["size"]:
                delta.append(f"extent {_position(old['size'])} to {_position(obj['size'])}")
            if old["color"] != obj["color"]:
                delta.append(f"color {old['color']} to {obj['color']}")
            if old["area"] is not None and obj["area"] is not None:
                delta.append(
                    f"area unchanged at {obj['area']} pixels" if old["area"] == obj["area"]
                    else f"area {old['area']} to {obj['area']} pixels"
                )
            if delta:
                changes.append(f"{obj['entity']}, compared with frame {previous['frameId']}: " + "; ".join(delta) + ".")
    return lines, changes


def _state_lines(frame: dict, previous: dict | None) -> list[str]:
    lines = []
    for key, label in (
        ("actor", "Actor grid position"), ("authoredPosition", "Authored actor pixel position"),
        ("authoredActorPosition", "Authored actor pixel position"), ("apertureCenter", "Visible aperture center"),
    ):
        if key in frame:
            lines.append(f"{label}: {_position(frame[key])}.")
    for name, position in frame.get("crates", {}).items():
        lines.append(f"Crate {name}: grid position {_position(position)}.")
    for key, noun, positive, negative in (
        ("plateOccupancy", "Plate", "occupied", "not occupied"),
        ("doorOpen", "Door", "open", "closed"),
    ):
        for name, value in frame.get(key, {}).items():
            text = positive if value is True else negative if value is False else str(value)
            line = f"{noun} {name}: {text}"
            old = previous.get(key, {}).get(name) if previous else value
            if previous and old != value:
                old_text = positive if old is True else negative if old is False else str(old)
                line += f" (was {old_text} in frame {previous['frameId']})"
            lines.append(line + ".")
    for key, label in (
        ("targetColor", "Current target color"), ("nextColor", "Authored next-color prediction, not a current observation"),
    ):
        if key in frame:
            lines.append(f"{label}: {_color(frame[key])}.")
    for key, label in (
        ("visibleActorPixels", "Visible actor pixels"), ("visiblePixels", "Currently visible pixels"),
        ("cumulativeKnownPixels", "Cumulative known pixels"), ("completeCoverage", "Complete scene coverage"),
        ("hitTarget", "Input hit target"), ("fullyHidden", "Actor fully hidden"),
        ("renderedActor", "Actor rendered"), ("supported", "Authored support state"),
        ("verticalVelocityPixelsPerTick", "Authored vertical velocity, pixels per tick"),
        ("mechanismEvent", "Authored mechanism event"),
    ):
        if key in frame:
            lines.append(f"{label}: {json.dumps(frame[key], ensure_ascii=True)}.")
    if frame.get("visibleActorPixels") == 0 or frame.get("fullyHidden") is True:
        lines.append("Do not count an unseen actor as a visible detection, or equate missing pixels with destruction.")
    if frame.get("pendingEffects"):
        lines.append("The oracle has pending effects; do not report a future response as already observed.")
    return lines


def _documentation_sections(text: str) -> list[dict]:
    sections = []
    for part in re.split(r"(?m)^## ", text)[1:]:
        title, _, content = part.partition("\n")
        if any(word in title.lower() for word in ("memory required", "measured new evidence", "required caution")):
            sections.append({"title": title.strip(), "text": content.strip().replace("`", "")})
    return sections


def frame_expectations(catalog: DemoCatalog, test_id: str, sequence_id: str, frame_id: str) -> dict:
    test = next((item for item in catalog.tests if item["id"] == test_id), None)
    if test is None or sequence_id not in test["recordings"]:
        raise KeyError("This test is not linked to the selected recording.")
    frames = catalog.frames(sequence_id)
    index = next((index for index, frame in enumerate(frames) if frame["frameId"] == frame_id), None)
    if index is None:
        raise KeyError("Unknown demo frame.")
    sequence = catalog.sequences[sequence_id]
    evaluation_path = sequence.get("evaluation")
    if not isinstance(evaluation_path, str) or not evaluation_path.startswith("evaluation/"):
        raise ValueError("No evaluation reference is supplied for this recording.")
    oracle = json.loads(catalog.read_file(evaluation_path))
    if not isinstance(oracle, dict) or not isinstance(oracle.get("frames"), list):
        raise ValueError("This evaluation file has no supported frame descriptions.")
    records = {row["frameId"]: row for row in oracle["frames"]}
    current = records.get(frame_id)
    if current is None:
        raise KeyError("No authored expectation exists for this frame.")
    image_hash = catalog.files[frames[index]["image"]]
    if current.get("sha256") != image_hash:
        raise ValueError("Frame expectations do not match the recorded image hash.")
    previous = records.get(frames[index - 1]["frameId"]) if index else None
    objects, changes = _object_lines(current, previous)
    interpretation = _state_lines(current, previous)
    specific = test_id in (sequence.get("testId"), oracle.get("testId"), oracle.get("caseId"))
    events = []
    if specific:
        for event in oracle.get("expectedEvents", []):
            if event.get("toFrameId") == frame_id:
                events.append({
                    "fromFrameId": event.get("fromFrameId"), "toFrameId": frame_id,
                    "description": event.get("display") or json.dumps(event.get("term"), ensure_ascii=True),
                })
        teacher = oracle.get("teacher", {})
        if teacher.get("bindingMustStayUnresolved") is True:
            interpretation.append("The controlled actor must remain unresolved; do not force an actor assignment.")
        if teacher.get("bindingExpectedAtFrame") is not None and str(teacher["bindingExpectedAtFrame"]) == frame_id:
            interpretation.append("Earlier calibration should establish the controlled actor here; later test responses must not train that binding.")
        if teacher.get("expectedBlockedStartFrame") is not None and str(teacher["expectedBlockedStartFrame"]) == frame_id:
            interpretation.append("The authored test expects the blocked episode to start here after the required failed attempts.")
    sections = _documentation_sections(catalog.read_file(test["documentation"]).decode("utf-8"))
    limitations = [
        "Author reference only: masks, names, and hidden state are not recognizer observations or inputs.",
        "Pixel area is not physical mass. Match entity identities independently; do not assume identity from a fixture name.",
        "The app runs recognition, not a complete temporal event grader. This guidance does not certify a pass.",
    ]
    if not specific:
        limitations.insert(0, "This recording is shared with another test. Its source oracle describes the frame, but no pass oracle was authored for this selected test-recording link.")
    limitations.extend(section["text"].split("\n\n", 1)[0] for section in sections if "caution" in section["title"].lower())
    if index == 0:
        transition_note = "Initial frame: establish a baseline. A single image does not establish a change, zero velocity, or a false prior relation."
    elif not events:
        transition_note = "No required event is listed for this transition. That is not proof that no event occurred."
    else:
        transition_note = "Authored event targets for this transition, subject to the evidence and timing limits below:"
    return {
        "testId": test_id, "sequenceId": sequence_id, "frameId": frame_id,
        "title": test["title"], "caption": current.get("caption"),
        "sourceSha256": image_hash, "evaluationSource": evaluation_path,
        "testSpecificOracle": specific, "objects": objects, "changes": changes,
        "interpretation": interpretation, "events": events, "transitionNote": transition_note,
        "requirements": oracle.get("requirements", []) if specific else [],
        "context": oracle.get("controlInterpretation") or oracle.get("description") or test["summary"],
        "assessment": oracle.get("expectedAssessment") if specific else "not_authored_for_this_link",
        "limitations": limitations, "evidenceSections": sections,
        "referenceFrame": {key: value for key, value in current.items() if key not in ("image", "sha256")},
    }
