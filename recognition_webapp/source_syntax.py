"""In-memory Prolog/MeTTa/JSON source views, also usable without a browser or Node."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys

from frame_metta import _symbol

NUMBER = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
ATOM = re.compile(r"[a-z][A-Za-z0-9_]*\Z")
VARIABLE = re.compile(r"[A-Z_][A-Za-z0-9_]*\Z")
DIALECTS = {"prolog", "metta", "json"}


@dataclass(frozen=True)
class Term:
    kind: str
    value: str = ""
    children: tuple[Term, ...] = ()
    tail: Term | None = None


def _quoted(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'").replace(
        "\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "'"


def _atom(value: str) -> str:
    return value if ATOM.fullmatch(value) else _quoted(value)


def _bare(value: str) -> str:
    # Empty text has no bare-token spelling; retain it rather than turn it into a space.
    return '""' if not value else _symbol(value).replace("$", "\\$")


def prolog(term: Term) -> str:
    if term.kind == "list":
        return "[" + ", ".join(map(prolog, term.children)) + (
            " | " + prolog(term.tail) if term.tail else "") + "]"
    if term.kind == "compound":
        return _atom(term.value) + ("(" + ", ".join(map(prolog, term.children)) + ")" if term.children else "")
    if term.kind in {"number", "variable"}:
        return term.value
    return _atom(term.value)


def metta(term: Term) -> str:
    if term.kind == "list":
        if term.tail:
            # Retain the existing open-tail notation; [] is reserved for proper lists.
            return "(list* " + " ".join(map(metta, (*term.children, term.tail))) + ")"
        return "([]" + (" " + " ".join(map(metta, term.children)) if term.children else "") + ")"
    if term.kind == "compound":
        return "(" + _bare(term.value) + (" " + " ".join(map(metta, term.children)) if term.children else "") + ")"
    if term.kind == "variable":
        return "$" + term.value
    return term.value if term.kind == "number" else _bare(term.value)


def _decode_escape(char: str) -> str:
    return {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", "v": "\v"}.get(char, char)


def _unquote(text: str) -> str:
    quote, body = text[0], text[1:-1]
    result, index = [], 0
    while index < len(body):
        char = body[index]
        if char == "\\":
            index += 1
            if index == len(body):
                raise ValueError("Incomplete quoted escape")
            result.append(_decode_escape(body[index]))
        elif char == quote and index + 1 < len(body) and body[index + 1] == quote:
            result.append(quote)
            index += 1
        else:
            result.append(char)
        index += 1
    return "".join(result)


def _split(text: str, delimiter: str = ",") -> list[str]:
    parts, start, stack, quote, index = [], 0, [], "", 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 1
                else:
                    quote = ""
        elif char in "'\"":
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != {")": "(", "]": "[", "}": "{"}[char]:
                raise ValueError("Unbalanced Prolog delimiters")
        elif not stack and text.startswith(delimiter, index):
            parts.append(text[start:index].strip())
            index += len(delimiter) - 1
            start = index + 1
        index += 1
    if stack or quote:
        raise ValueError("Unterminated Prolog term")
    parts.append(text[start:].strip())
    return parts


def parse_prolog_term(text: str, depth: int = 0) -> Term:
    text = text.strip()
    if not text or depth > 128:
        raise ValueError("Missing or excessively nested Prolog term")
    if text.startswith("[") and text.endswith("]"):
        body = text[1:-1].strip()
        if not body:
            return Term("list")
        parts = _split(body, "|")
        if len(parts) > 2:
            raise ValueError("Invalid Prolog list tail")
        values = tuple(parse_prolog_term(part, depth + 1) for part in _split(parts[0]))
        tail = parse_prolog_term(parts[1], depth + 1) if len(parts) == 2 else None
        if tail and tail.kind == "list":
            return Term("list", children=values + tail.children, tail=tail.tail)
        return Term("list", children=values, tail=tail)
    match = re.fullmatch(r"([a-z][A-Za-z0-9_]*|'(?:\\.|''|[^'])*')\s*\(([\s\S]*)\)", text)
    if match:
        head, body = match.groups()
        return Term("compound", _unquote(head) if head.startswith("'") else head,
                    tuple(parse_prolog_term(part, depth + 1) for part in _split(body)) if body.strip() else ())
    if text[0] in "'\"" and text[-1] == text[0]:
        return Term("atom", _unquote(text))
    if NUMBER.fullmatch(text):
        return Term("number", text)
    if VARIABLE.fullmatch(text):
        return Term("variable", text)
    if ATOM.fullmatch(text):
        return Term("atom", text)
    raise ValueError(f"Unsupported Prolog data term: {text[:100]}")


def _prolog_statements(source: str) -> list[tuple[str, int, int]]:
    results, current, start, stack, quote = [], [], None, [], ""
    index = 0
    while index < len(source):
        char, following = source[index], source[index + 1:index + 2]
        if quote:
            current.append(char)
            if char == "\\" and following:
                index += 1
                current.append(following)
            elif char == quote:
                if following == quote:
                    index += 1
                    current.append(following)
                else:
                    quote = ""
        elif char == "%" or source.startswith("/*", index):
            if char == "%":
                end = source.find("\n", index)
                end = len(source) if end < 0 else end
            else:
                end = source.find("*/", index + 2)
                if end < 0:
                    raise ValueError("Unterminated Prolog block comment")
                end += 2
            current.append(" ")
            index = end
            continue
        else:
            if start is None and not char.isspace():
                start = index
            current.append(char)
            if char in "'\"":
                quote = char
            elif char in "([{":
                stack.append(char)
            elif char in ")]}":
                if not stack or stack.pop() != {")": "(", "]": "[", "}": "{"}[char]:
                    raise ValueError("Unbalanced Prolog delimiters")
            elif char == "." and not stack and (not following or following.isspace() or following == "%" or source.startswith("/*", index + 1)):
                if start is not None:
                    results.append(("".join(current).strip(), start, index + 1))
                current, start = [], None
        index += 1
    if quote or stack or "".join(current).strip():
        raise ValueError("Unterminated Prolog statement")
    return results


def _metta_expressions(source: str) -> list[tuple[Term, int, int]]:
    cursor = 0

    def whitespace():
        nonlocal cursor
        while cursor < len(source):
            if source[cursor].isspace():
                cursor += 1
            elif source[cursor] == ";":
                end = source.find("\n", cursor)
                cursor = len(source) if end < 0 else end
            else:
                break

    def term(depth=0):
        nonlocal cursor
        whitespace()
        if depth > 128 or cursor >= len(source):
            raise ValueError("Unterminated or excessively nested MeTTa expression")
        if source[cursor] == "(":
            cursor += 1
            whitespace()
            head = token()
            values = []
            while True:
                whitespace()
                if cursor >= len(source):
                    raise ValueError("Unterminated MeTTa expression")
                if source[cursor] == ")":
                    cursor += 1
                    break
                values.append(term(depth + 1))
            if head[1] == "[]":
                return Term("list", children=tuple(values))
            if head[1] == "list*" and values:
                return Term("list", children=tuple(values[:-1]), tail=values[-1])
            return Term("compound", head[0], tuple(values))
        value, raw, quoted = token()
        if not quoted and re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", raw):
            return Term("variable", value[1:])
        return Term("number" if not quoted and NUMBER.fullmatch(raw) else "atom", value)

    def token():
        nonlocal cursor
        if cursor >= len(source) or source[cursor] in "();":
            raise ValueError("Expected a MeTTa symbol")
        start, quoted, values = cursor, source[cursor] == '"', []
        if quoted:
            cursor += 1
        while cursor < len(source):
            char = source[cursor]
            if char == "\\":
                cursor += 1
                if cursor >= len(source):
                    raise ValueError("Incomplete MeTTa escape")
                values.append(_decode_escape(source[cursor]))
                cursor += 1
            elif quoted and char == '"':
                cursor += 1
                return "".join(values), source[start:cursor], True
            elif not quoted and (char.isspace() or char in "();"):
                break
            else:
                values.append(char)
                cursor += 1
        if quoted:
            raise ValueError("Unterminated MeTTa quoted value")
        return "".join(values), source[start:cursor], False

    result = []
    while True:
        whitespace()
        if cursor == len(source):
            return result
        start = cursor
        parsed = term()
        if parsed.kind != "compound":
            raise ValueError("Expected a top-level MeTTa expression")
        result.append((parsed, start, cursor))


def _json_term(value) -> Term:
    if value is None:
        return Term("compound", "json_null")
    if isinstance(value, str):
        return Term("compound", "json_string", (Term("atom", value),))
    if type(value) is bool:
        return Term("compound", "json_boolean", (Term("atom", str(value).lower()),))
    if type(value) is int or type(value) is float and math.isfinite(value):
        return Term("compound", "json_number", (Term("number", json.dumps(value)),))
    if isinstance(value, list):
        return Term("compound", "json_array", (Term("list", children=tuple(map(_json_term, value))),))
    if isinstance(value, dict):
        pairs = tuple(Term("compound", "json_pair", (_json_term(key), _json_term(item))) for key, item in value.items())
        return Term("compound", "json_object", (Term("list", children=pairs),))
    raise ValueError("Unsupported JSON value")


def _term_data(term: Term) -> dict:
    value = {"kind": term.kind, "source": prolog(term)}
    if term.kind == "compound":
        value.update(functor=_atom(term.value), args=[_term_data(child) for child in term.children])
    elif term.kind == "list":
        value["items"] = [_term_data(child) for child in term.children]
        if term.tail:
            value["tail"] = _term_data(term.tail)
    value["formats"] = {"prolog": prolog(term), "metta": metta(term)}
    value["formats"]["json"] = json.dumps(_plain_term(term), ensure_ascii=True)
    return value


def _plain_term(term: Term) -> dict:
    result = {"kind": term.kind, "value": term.value}
    if term.children:
        result["children"] = [_plain_term(child) for child in term.children]
    if term.tail:
        result["tail"] = _plain_term(term.tail)
    return result


def _json_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _json_entries(text: str):
    decoder = json.JSONDecoder(object_pairs_hook=_json_pairs)
    value = decoder.decode(text)
    if not isinstance(value, dict) or not value:
        yield Term("compound", "json_document", (_json_term(value),)), 0, len(text)
        return
    cursor = text.index("{") + 1
    while True:
        while text[cursor].isspace():
            cursor += 1
        if text[cursor] == "}":
            return
        start = cursor
        key, cursor = decoder.raw_decode(text, cursor)
        while text[cursor].isspace():
            cursor += 1
        cursor += 1  # The complete document was validated before reading its fields.
        while text[cursor].isspace():
            cursor += 1
        item, end = decoder.raw_decode(text, cursor)
        yield Term("compound", "json_field", (Term("atom", key), _json_term(item))), start, end
        cursor = end
        while text[cursor].isspace():
            cursor += 1
        if text[cursor] == ",":
            cursor += 1


def dialect_for(source: dict) -> str:
    suffix = Path(source["name"]).suffix.lower()
    dialect = {".pl": "prolog", ".prolog": "prolog", ".metta": "metta", ".json": "json"}.get(suffix, source.get("dialect", "prolog"))
    if dialect not in DIALECTS:
        raise ValueError("Unsupported source dialect")
    return dialect


def analyze_source(source: dict) -> dict:
    if (not isinstance(source, dict) or not isinstance(source.get("name"), str)
            or not isinstance(source.get("text"), str)):
        raise ValueError("Each source requires a name and text")
    text, name, dialect = source["text"], source["name"], dialect_for(source)
    clauses, diagnostics = [], []
    try:
        if dialect == "prolog":
            for raw, start, end in _prolog_statements(text):
                body = raw.rstrip(".").strip()
                if body.startswith((":-", "?-")):
                    continue
                parts = _split(body, ":-")
                try:
                    node = parse_prolog_term(parts[0])
                    if node.kind == "atom":
                        node = Term("compound", node.value)
                    if node.kind != "compound":
                        raise ValueError("Expected a predicate head")
                except ValueError as error:
                    diagnostics.append({"line": text.count("\n", 0, start) + 1, "severity": "warning", "message": str(error), "statement": raw})
                    continue
                clauses.append(_clause(node, source, start, end, raw, rule=len(parts) > 1))
        elif dialect == "metta":
            for node, start, end in _metta_expressions(text):
                clauses.append(_clause(node, source, start, end))
        else:
            for node, start, end in _json_entries(text):
                clauses.append(_clause(node, source, start, end))
    except (ValueError, RecursionError) as error:
        diagnostics.append({"line": 1, "severity": "error", "message": str(error), "statement": text})
    for index, clause in enumerate(clauses):
        clause["index"] = index
    formats, view_nodes = {}, {}
    for syntax in ("prolog", "metta", "json"):
        if syntax == dialect:
            formats[syntax] = text
            view_nodes[syntax] = [{"key": clause["predicate"] + "/" + str(clause["arity"]),
                                   "text": clause["original"], "start": clause["start"], "end": clause["end"]}
                                  for clause in clauses]
        elif syntax == "json":
            formats[syntax] = json.dumps({"source": name, "clauses": [
                {"predicate": clause["predicate"], "arguments": clause["args"], "native": clause["original"]}
                for clause in clauses]}, ensure_ascii=True, indent=2)
            view_nodes[syntax] = []
        else:
            prefix = "%" if syntax == "prolog" else ";"
            pieces, nodes, cursor, size = [], [], 0, 0
            for clause in clauses:
                gap = text[cursor:clause["start"]]
                if gap.strip():
                    gap = "\n".join(prefix + " " + line if line.strip() else line for line in gap.split("\n"))
                    if not gap.endswith("\n"):
                        gap += "\n"
                pieces.append(gap)
                size += len(gap)
                rendered = clause["formats"][syntax]
                pieces.append(rendered)
                nodes.append({"key": clause["predicate"] + "/" + str(clause["arity"]),
                              "text": rendered, "start": size, "end": size + len(rendered)})
                size += len(rendered)
                cursor = clause["end"]
            gap = text[cursor:]
            if gap.strip():
                gap = "\n".join(prefix + " " + line if line.strip() else line for line in gap.split("\n"))
            pieces.append(gap)
            if any(item["severity"] == "error" for item in diagnostics):
                warning = prefix + " Conversion incomplete: " + diagnostics[-1]["message"] + "\n"
                pieces.insert(0, warning)
                for item in nodes:
                    item["start"] += len(warning)
                    item["end"] += len(warning)
            formats[syntax] = "".join(pieces)
            view_nodes[syntax] = nodes
    for syntax, nodes in view_nodes.items():
        for item in nodes:
            rendered = formats[syntax]
            item["start"] = len(rendered[:item["start"]].encode("utf-16-le")) // 2
            item["end"] = len(rendered[:item["end"]].encode("utf-16-le")) // 2
    return {"name": name, "text": text, "dialect": dialect, "clauses": clauses,
            "diagnostics": diagnostics, "formats": formats, "viewNodes": view_nodes}


def _clause(node: Term, source: dict, start: int, end: int, raw: str | None = None, *, rule=False) -> dict:
    text, name = source["text"], source["name"]
    native = text[start:end]
    pl = raw if raw is not None else prolog(node) + "."
    mt = "; Prolog rule retained in native Prolog only: " + " ".join(native.split()) if rule else metta(node)
    value = {
        "predicate": _atom(node.value), "arity": len(node.children),
        "args": [prolog(child) for child in node.children],
        "argTerms": [_term_data(child) for child in node.children],
        "source": pl, "original": native, "metta": mt, "sourcePath": name,
        "sourceLabel": source.get("label") or name.replace("\\", "/").split("/")[-1],
        "line": text.count("\n", 0, start) + 1,
        "endLine": text.count("\n", 0, end) + 1,
        "start": start, "end": end,
        "predicateFormats": {"prolog": _atom(node.value), "metta": _bare(node.value)},
    }
    value["formats"] = {"prolog": pl, "metta": mt, "json": json.dumps({
        "predicate": value["predicate"], "arguments": [_plain_term(child) for child in node.children],
        "source": {"file": name, "line": value["line"]}, "original": native,
    }, ensure_ascii=True)}
    return value


def analyze_sources(sources: list[dict]) -> dict:
    if not isinstance(sources, list) or len(sources) > 100:
        raise ValueError("Expected at most 100 source files")
    if len({item.get("name") for item in sources if isinstance(item, dict)}) != len(sources):
        raise ValueError("Source names must be unique")
    return {"schemaVersion": 1, "sources": [analyze_source(source) for source in sources]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source_dialect", choices=sorted(DIALECTS), required=True)
    parser.add_argument("--to", dest="target", choices=sorted(DIALECTS), required=True)
    parser.add_argument("--file", type=Path, help="Read this file instead of stdin; output is stdout only")
    args = parser.parse_args()
    try:
        text = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
        suffix = {"prolog": "pl", "metta": "metta", "json": "json"}[args.source_dialect]
        result = analyze_source({"name": f"source.{suffix}", "text": text})
        if result["diagnostics"]:
            print(json.dumps(result["diagnostics"]), file=sys.stderr)
        print(result["formats"][args.target], end="")
        return 1 if result["diagnostics"] else 0
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
