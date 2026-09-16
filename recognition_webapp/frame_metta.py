"""Serialize only one frame's measured and derived pipeline output as MeTTa."""

import math
import re


class Atom(str):
    """A string that should be emitted as a bare MeTTa symbol (e.g. region id r2), not quoted."""


# Characters that must be backslash-escaped to keep a value a single bare MeTTa symbol.
_ESCAPES = {"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r"}
_SPECIAL = set(' ()[]{}";')


def _symbol(value: str) -> str:
    """Render a string as a bare MeTTa symbol, backslash-escaping whitespace, quotes, brackets,
    and control characters (space -> \\ , tab -> \\t, newline -> \\n, etc.) instead of quoting."""
    if value == "":
        return "\\ "  # an empty token is written as a single escaped space
    out = []
    for ch in value:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ch in _SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _render(value) -> str:
    if isinstance(value, tuple):
        head, *arguments = value
        if not isinstance(head, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", head):
            raise ValueError("Invalid generated MeTTa predicate.")
        return "(" + " ".join([head, *(_render(item) for item in arguments)]) + ")"
    if isinstance(value, str):
        # Every string is a bare symbol; special characters are backslash-escaped, never quoted.
        return _symbol(value)
    if type(value) in (int, float) and math.isfinite(value):
        return str(value)
    raise ValueError("Unsupported value in frame MeTTa output.")


def _ident(value):
    """Wrap an id-like value so it renders as a bare atom (r2, g1, o3) instead of "r2"."""
    return Atom(value) if isinstance(value, str) else value


def build_frame_metta(frame: dict, source: dict, width: int, height: int, pipeline: str, prolog: dict, objects: list) -> str:
    scope = ("Frame", _ident(frame["sequenceId"]), _ident(frame["frameId"]))
    lines = [
        "; Process output for this frame only.",
        "; Region measurements and Prolog deductions are not authored expected answers.",
        "; No temporal events or cross-frame identity claims are added.",
    ]

    def emit(predicate, *arguments):
        lines.append(_render((predicate, scope, *arguments)))

    emit("pipeline", pipeline)
    emit("imageSize", width, height)
    if source.get("sha256"):
        emit("sourceImageSha256", source["sha256"])
    adjacent = set()
    for part in prolog["parts"]:
        identifier = _ident(part["id"])
        emit("part", identifier, _ident(part["color"]), part["area"])
        emit("centroid", identifier, *part["centroid"])
        for key, predicate in (("polygons", "polygon"), ("holes", "hole"), ("midlines", "midline")):
            for index, points in enumerate(part[key], 1):
                emit(predicate, identifier, index, ("points", *(("xy", x, y) for x, y in points)))
        for x, y, depth in part["fillpoints"]:
            emit("fillpoint", identifier, x, y, depth)
        for other in part["adjacent"]:
            adjacent.add(tuple(sorted((part["id"], other))))
    for left, right in sorted(adjacent):
        emit("adjacent", _ident(left), _ident(right))
    for identifier in prolog["background"]:
        emit("background", _ident(identifier))
    for group in prolog["part_groups"]:
        emit("group", _ident(group["id"]), group["area"])
        for member in group["members"]:
            emit("partOf", _ident(member), _ident(group["id"]))
    for group in prolog["visual_groups"]:
        emit("visualGroup", _ident(group["id"]), group["method"], ("parts", *(_ident(m) for m in group["members"])))
    for group in prolog["accepted_groups"]:
        emit("acceptedGroup", _ident(group["id"]), group["mode"])
        score = group["provenance"].get("score")
        if type(score) in (int, float):
            emit("acceptanceScore", _ident(group["id"]), score)
        for member in group["members"]:
            emit("partOf", _ident(member), _ident(group["id"]))
    for inner, outer in prolog["containment"]:
        emit("inside", _ident(inner), _ident(outer))
    for index, members in enumerate(prolog["objects"], 1):
        emit("objectInstance", Atom(f"o{index}"), ("parts", *(_ident(m) for m in members)))
    for obj in objects:
        emit("shape", _ident(obj["id"]), _ident(obj["shape_id"]), obj["name"])
    for program in prolog["turtle_programs"]:
        commands = []
        for command in program["commands"]:
            op = command["op"]
            if op == "start":
                commands.append((op, command["x"], command["y"], command["heading"]))
            elif op == "forward":
                commands.append((op, command["distance"]))
            elif op == "turn":
                commands.append((op, command["degrees"]))
            elif op in ("close", "dot"):
                commands.append((op,))
            else:
                raise ValueError("Unsupported turtle command in MeTTa output.")
        emit("turtleProgram", _ident(program["region"]), program["kind"], program["index"], ("commands", *commands))
    return "\n".join(lines) + "\n"
