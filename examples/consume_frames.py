"""Read frame JSONL from stdin and report PNG-byte changes, not inferred events."""

import sys

sys.dont_write_bytecode = True

import base64
import hashlib
import json
import struct


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def consume() -> None:
    previous_sequence = None
    previous_hash = None
    line_number = 0
    for line_number, line in enumerate(sys.stdin, 1):
        try:
            record = json.loads(line)
            require(isinstance(record, dict), "Expected a frame object")
            for key in ("sequence_id", "frame_id"):
                require(isinstance(record.get(key), str), f"Missing or invalid {key}")
            for key in ("order", "at_seconds", "incoming_action", "action_data"):
                require(key in record, f"Missing {key}")
            image = record.get("image")
            require(isinstance(image, dict) and image.get("mime_type") == "image/png", "Expected image/png")
            require(isinstance(image.get("base64"), str), "Missing PNG base64")
            content = base64.b64decode(image["base64"], validate=True)
            require(
                len(content) >= 33 and content[:8] == b"\x89PNG\r\n\x1a\n"
                and content[8:16] == b"\x00\x00\x00\rIHDR",
                "Missing PNG IHDR header",
            )
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", content[16:29])
            require(width > 0 and height > 0, "Invalid PNG dimensions")
            require(color_type in (2, 6), "This example expects RGB or RGBA PNG")
            digest = hashlib.sha256(content).hexdigest()
            source = record.get("source")
            require(isinstance(source, dict), "Missing source metadata")
            hashes = source.get("sha256")
            require(isinstance(hashes, dict) and hashes.get("image") == digest, "PNG source hash mismatch")
            if record["sequence_id"] != previous_sequence:
                previous_hash = None
            print(json.dumps({
                "sequence_id": record["sequence_id"],
                "frame_id": record["frame_id"],
                "order": record["order"],
                "at_seconds": record["at_seconds"],
                "incoming_action": record["incoming_action"],
                "action_data": record["action_data"],
                "png": {
                    "width": width, "height": height, "bit_depth": bit_depth,
                    "color_mode": "RGB" if color_type == 2 else "RGBA",
                    "bytes": len(content), "sha256": digest,
                },
                "png_bytes_changed": None if previous_hash is None else digest != previous_hash,
            }, ensure_ascii=True, allow_nan=False), flush=True)
            previous_sequence = record["sequence_id"]
            previous_hash = digest
        except (OSError, ValueError, struct.error) as error:
            raise ValueError(f"line {line_number}: {error}") from error
    require(line_number > 0, "No frame JSONL received on stdin")


def main() -> int:
    try:
        consume()
    except (OSError, ValueError) as error:
        print(f"consume_frames: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
