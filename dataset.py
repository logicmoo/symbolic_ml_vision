"""Read the local Omega Vision export without importing its source application."""

import sys

sys.dont_write_bytecode = True

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re


class DatasetError(ValueError):
    """An invalid, unsafe, or inconsistent dataset input."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def field(record: dict, key: str, kind: type):
    value = record.get(key)
    require(type(value) is kind, f"{key!r} must be a {kind.__name__}")
    return value


def reject_constant(value: str):
    raise DatasetError(f"Non-JSON numeric constant: {value}")


def decode_json(content: bytes, name: str):
    try:
        return json.loads(content, parse_constant=reject_constant)
    except (UnicodeDecodeError, ValueError) as error:
        raise DatasetError(f"{name}: {error}") from error


def portable_parts(name: str) -> list[str]:
    require(isinstance(name, str) and bool(name), "Paths must be nonempty strings")
    require(
        not any(char in name for char in '\\:<>\"|?*')
        and not any(ord(char) < 32 for char in name),
        f"Not a portable relative path: {name!r}",
    )
    parts = name.split("/")
    require(
        all(part not in ("", ".", "..") and not part.endswith((" ", ".")) for part in parts),
        f"Not a portable relative path: {name!r}",
    )
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in range(1, 10))
    require(
        all(part.split(".")[0].upper() not in reserved for part in parts),
        f"Windows device name in path: {name!r}",
    )
    return parts


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)


class Dataset:
    def __init__(self) -> None:
        requested = Path(__file__).resolve().parent / "data" / "omega_vision"
        self.root = requested.resolve(strict=True)
        require(self.root == requested, "The data root must not be redirected by a symlink or junction")
        self.catalog = decode_json(self.path("dataset.json").read_bytes(), "dataset.json")
        require(isinstance(self.catalog, dict), "dataset.json must contain an object")
        require(
            type(self.catalog.get("schemaVersion")) is int and self.catalog["schemaVersion"] == 1,
            "Only dataset schemaVersion 1 is supported",
        )
        self.files = field(self.catalog, "files", dict)
        require("dataset.json" not in self.files, "The manifest must not hash itself")
        for name, digest in self.files.items():
            portable_parts(name)
            require(
                isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest) is not None,
                f"Invalid SHA-256 for {name!r}",
            )
        self.tests = self.index("tests")
        self.sequences = self.index("sequences")
        self.symbolic = self.index("symbolicExamples")

    def path(self, name: str) -> Path:
        result = self.root.joinpath(*portable_parts(name)).resolve(strict=True)
        require(result.is_relative_to(self.root), f"Path escapes the data root: {name!r}")
        return result

    def reference(self, name: str) -> str:
        portable_parts(name)
        require(name in self.files, f"Referenced file has no manifest hash: {name!r}")
        return name

    def read(self, name: str) -> bytes:
        self.reference(name)
        path = self.path(name)
        require(path.is_file(), f"Not a regular file: {name!r}")
        content = path.read_bytes()
        require(
            hashlib.sha256(content).hexdigest() == self.files[name].lower(),
            f"SHA-256 mismatch: {name}",
        )
        return content

    def index(self, key: str) -> dict[str, dict]:
        result = {}
        for record in field(self.catalog, key, list):
            require(isinstance(record, dict), f"{key} entries must be objects")
            identifier = field(record, "id", str)
            require(bool(identifier) and identifier not in result, f"Empty or duplicate {key} ID: {identifier!r}")
            result[identifier] = record
        return result

    def frames(self, sequence: dict) -> list[dict]:
        directory = field(sequence, "directory", str)
        parts = portable_parts(directory)
        require(
            len(parts) > 1 and parts[0] in ("recordings", "curated"),
            f"Sequence directory must be below recordings or curated: {directory}",
        )
        frames = field(sequence, "frames", list)
        require(field(sequence, "frameCount", int) == len(frames), f"Incorrect frameCount: {sequence['id']}")
        identifiers, orders = set(), set()
        for frame in frames:
            require(isinstance(frame, dict), "Frame entries must be objects")
            identifier = field(frame, "frameId", str)
            order = field(frame, "order", int)
            require(bool(identifier) and identifier not in identifiers, f"Empty or duplicate frameId in {sequence['id']}")
            require(order >= 0 and order not in orders, f"Invalid or duplicate frame order in {sequence['id']}")
            identifiers.add(identifier)
            orders.add(order)
            for key in ("image", "state"):
                name = self.reference(field(frame, key, str))
                require(name.startswith(directory + "/"), f"{key} is outside its sequence directory: {name}")
        return sorted(frames, key=lambda frame: frame["order"])

    def listing(self) -> dict:
        return {
            "name": field(self.catalog, "name", str),
            "source": field(self.catalog, "source", dict),
            "inventory": field(self.catalog, "inventory", dict),
            "tests": [
                {key: field(test, key, list if key == "recordings" else str)
                 for key in ("id", "title", "group", "summary", "documentation", "recordings")}
                for test in self.tests.values()
            ],
            "sequences": [
                {
                    **{key: field(sequence, key, int if key == "frameCount" else str)
                       for key in ("id", "testId", "partition", "label", "frameCount")},
                    "testIds": [test["id"] for test in self.tests.values() if sequence["id"] in test["recordings"]],
                }
                for sequence in self.sequences.values()
            ],
            "symbolicExamples": [
                {key: field(example, key, str) for key in ("id", "track", "task", "description")}
                for example in self.symbolic.values()
            ],
        }

    def verify(self) -> dict:
        self.listing()
        frame_count = 0
        for test in self.tests.values():
            self.reference(field(test, "documentation", str))
            seen = set()
            for identifier in field(test, "recordings", list):
                require(isinstance(identifier, str) and identifier in self.sequences, f"Unknown recording in test {test['id']}")
                require(identifier not in seen, f"Duplicate recording in test {test['id']}: {identifier}")
                seen.add(identifier)
        for sequence in self.sequences.values():
            test_id = field(sequence, "testId", str)
            require(test_id in self.tests, f"Unknown testId: {test_id}")
            require(any(sequence["id"] in test["recordings"] for test in self.tests.values()),
                    f"Unlisted test recording: {sequence['id']}")
            frames = self.frames(sequence)
            require(self.path(sequence["directory"]).is_dir(), f"Missing sequence directory: {sequence['directory']}")
            frame_count += len(frames)
            evaluation = self.reference(field(sequence, "evaluation", str))
            require(evaluation.startswith("evaluation/"), f"Oracle must be in evaluation: {evaluation}")
            for key in ("controlProtocol", "observerAssessment"):
                require(key in sequence, f"Missing sequence field: {key}")
                if sequence[key] is not None:
                    self.reference(field(sequence, key, str))
        for example in self.symbolic.values():
            require(example.get("track") in ("symbolic_deduction", "symbolic_induction"), f"Unknown symbolic track: {example['id']}")
            public = self.reference(field(example, "input", str))
            expected = self.reference(field(example, "expected", str))
            require(public.startswith("symbolic/inputs/"), f"Symbolic input must be public: {public}")
            require(expected.startswith("evaluation/"), f"Expected result must be in evaluation: {expected}")
            for test_id in field(example, "sourceTests", list):
                require(isinstance(test_id, str) and bool(test_id), "Source-test citations must be nonempty strings")
        counts = {
            "tests": len(self.tests),
            "sequences": len(self.sequences),
            "frames": frame_count,
            "symbolicExamples": len(self.symbolic),
        }
        inventory = field(self.catalog, "inventory", dict)
        for key, actual in counts.items():
            require(field(inventory, key, int) == actual, f"Inventory {key}: expected {inventory[key]}, found {actual}")
        for name in self.files:
            self.read(name)
        return {"ok": True, "inventory": counts, "verifiedFiles": len(self.files)}

    def stream(self, identifier: str) -> None:
        require(identifier in self.sequences, f"Unknown sequence ID: {identifier!r}")
        for frame in self.frames(self.sequences[identifier]):
            image = self.read(frame["image"])
            require(image.startswith(b"\x89PNG\r\n\x1a\n"), f"Not a PNG: {frame['image']}")
            state = decode_json(self.read(frame["state"]), frame["state"])
            require(isinstance(state, dict), f"Frame state must be an object: {frame['state']}")
            for key in ("incoming_action", "action_data", "at_seconds"):
                require(key in state, f"Missing {key} in {frame['state']}")
            emit({
                "sequence_id": identifier,
                "frame_id": frame["frameId"],
                "order": frame["order"],
                "image": {"mime_type": "image/png", "base64": base64.b64encode(image).decode("ascii")},
                "incoming_action": state["incoming_action"],
                "action_data": state["action_data"],
                "at_seconds": state["at_seconds"],
                "source": {
                    "image": frame["image"],
                    "state": frame["state"],
                    "sha256": {key: self.files[frame[key]].lower() for key in ("image", "state")},
                },
            })

    def symbolic_input(self, identifier: str, expected: bool) -> object:
        require(identifier in self.symbolic, f"Unknown symbolic example ID: {identifier!r}")
        example = self.symbolic[identifier]
        name = field(example, "expected" if expected else "input", str)
        prefix = "evaluation/" if expected else "symbolic/inputs/"
        require(name.startswith(prefix), f"Incorrect symbolic {'expected' if expected else 'input'} area: {name}")
        return decode_json(self.read(name), name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List public catalogue metadata and IDs")
    commands.add_parser("verify", help="Check manifest references, counts, and every listed file hash")
    stream = commands.add_parser("stream", help="Emit chronological public frame JSONL")
    stream.add_argument("--sequence", required=True, help="Exact sequence ID from list")
    symbolic = commands.add_parser("symbolic", help="Read one public symbolic input")
    symbolic.add_argument("--id", required=True, help="Exact symbolic example ID from list")
    symbolic.add_argument("--expected", action="store_true", help="Read evaluation output INSTEAD of public input")
    args = parser.parse_args()
    try:
        dataset = Dataset()
        if args.command == "list":
            emit(dataset.listing())
        elif args.command == "verify":
            emit(dataset.verify())
        elif args.command == "stream":
            dataset.stream(args.sequence)
        else:
            emit(dataset.symbolic_input(args.id, args.expected))
    except (OSError, ValueError) as error:
        print(f"dataset: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
