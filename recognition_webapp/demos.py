"""Read-only access to the exported visual demo catalogue and original PNGs."""

from hashlib import sha256
import json
from pathlib import Path


class DemoCatalog:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        manifest = json.loads(self.path("dataset.json").read_bytes())
        if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1:
            raise ValueError("Demo data must use dataset schemaVersion 1.")
        for key, kind in (("tests", list), ("sequences", list), ("files", dict)):
            if not isinstance(manifest.get(key), kind):
                raise ValueError(f"Invalid demo catalogue field: {key}")
        self.tests = manifest["tests"]
        self.files = manifest["files"]
        self.sequences = {}
        for sequence in manifest["sequences"]:
            if not isinstance(sequence, dict) or not isinstance(sequence.get("id"), str):
                raise ValueError("Invalid demo sequence entry.")
            if sequence["id"] in self.sequences:
                raise ValueError("Duplicate demo sequence ID.")
            self.sequences[sequence["id"]] = sequence

    def path(self, name: str) -> Path:
        if not isinstance(name, str) or not name or any(char in name for char in '\\:<>\"|?*'):
            raise ValueError("Unsafe demo file path.")
        parts = name.split("/")
        if any(part in ("", ".", "..") or part.endswith((" ", ".")) or
               any(ord(char) < 32 for char in part) for part in parts):
            raise ValueError("Unsafe demo file path.")
        path = self.root.joinpath(*parts).resolve(strict=True)
        if not path.is_relative_to(self.root):
            raise ValueError("Demo file path escapes the data directory.")
        return path

    def frames(self, identifier: str) -> list[dict]:
        sequence = self.sequences.get(identifier)
        if sequence is None:
            raise KeyError("Unknown demo recording.")
        frames = sequence.get("frames")
        if not isinstance(frames, list) or len(frames) != sequence.get("frameCount"):
            raise ValueError("Invalid demo frame inventory.")
        if any(not isinstance(frame, dict) or type(frame.get("order")) is not int or
               not isinstance(frame.get("frameId"), str) for frame in frames):
            raise ValueError("Invalid demo frame entry.")
        if len({frame["frameId"] for frame in frames}) != len(frames) or len({frame["order"] for frame in frames}) != len(frames):
            raise ValueError("Duplicate demo frame ID or order.")
        return sorted(frames, key=lambda frame: frame["order"])

    def listing(self) -> dict:
        tests = []
        memberships = {identifier: [] for identifier in self.sequences}
        test_ids = set()
        for test in self.tests:
            if not isinstance(test, dict) or any(
                not isinstance(test.get(key), str) for key in ("id", "title", "group", "summary")
            ) or not isinstance(test.get("recordings"), list):
                raise ValueError("Invalid demo test entry.")
            if any(not isinstance(identifier, str) or identifier not in self.sequences for identifier in test["recordings"]):
                raise ValueError("Demo test references a missing recording.")
            if test["id"] in test_ids or len(set(test["recordings"])) != len(test["recordings"]):
                raise ValueError("Duplicate demo test or test-recording link.")
            test_ids.add(test["id"])
            for identifier in test["recordings"]:
                memberships[identifier].append(test["id"])
            tests.append({key: test[key] for key in ("id", "title", "group", "summary", "recordings")})
        sequences = []
        for identifier, sequence in self.sequences.items():
            if any(not isinstance(sequence.get(key), str) for key in ("label", "partition")):
                raise ValueError("Invalid demo recording metadata.")
            sequences.append({
                "id": identifier, "testIds": memberships[identifier], "label": sequence["label"],
                "partition": sequence["partition"],
                "frames": [{"frameId": frame["frameId"], "order": frame["order"]} for frame in self.frames(identifier)],
            })
        return {"tests": tests, "sequences": sequences}

    def read_file(self, name: str) -> bytes:
        expected = self.files.get(name)
        if not isinstance(expected, str):
            raise ValueError("Demo file has no source hash.")
        content = self.path(name).read_bytes()
        if sha256(content).hexdigest() != expected.lower():
            raise ValueError("Demo file source hash mismatch.")
        return content

    def image(self, identifier: str, frame_id: str) -> bytes:
        frame = next((frame for frame in self.frames(identifier) if frame["frameId"] == frame_id), None)
        if frame is None:
            raise KeyError("Unknown demo frame.")
        name = frame.get("image")
        if not isinstance(name, str) or name.split("/")[0] not in ("recordings", "curated"):
            raise ValueError("Demo images must be in recordings or curated.")
        image = self.read_file(name)
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Demo frame is not a PNG.")
        return image
