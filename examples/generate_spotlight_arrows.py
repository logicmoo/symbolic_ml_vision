"""Generate the arrow-controlled spotlight recordings (spotlight_arrows suite).

The spotlight aperture is driven by discrete ARROW COMMANDS instead of MOVE_POINTER
coordinates: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right, each moving the
aperture centre 8 px. The commands are recorded as per-frame `incoming_action` input
evidence (action_data stays empty), so a learner must correlate the arrow command with
the aperture's visible motion and accumulate the static scene through the moving hole —
everything else is occluded by darkness.

Idempotent: writes recordings + evaluations + documentation, and registers the new test,
sequences, and file hashes in dataset.json. Reserved-input layout matches the existing
visual-memory-recordings-v1 fixtures. All output is LF.
"""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "omega_vision"
SUITE = "visual-memory-recordings-v1"
TEST_ID = "spotlight_arrows"
WIDTH, HEIGHT, RADIUS, STEP = 48, 32, 8, 8
ARROWS = {"ACTION1": (0, -STEP), "ACTION2": (0, STEP), "ACTION3": (-STEP, 0), "ACTION4": (STEP, 0)}
SCENE_VARIANT = 2


def build_scene() -> list[list[tuple[int, int, int]]]:
    """Deterministic static 48x32 scene: shapes on black, distinct from earlier variants."""
    scene = [[(0, 0, 0)] * WIDTH for _ in range(HEIGHT)]

    def rect(x0, y0, w, h, color, fill=True):
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                if fill or x in (x0, x0 + w - 1) or y in (y0, y0 + h - 1):
                    scene[y][x] = color

    rect(3, 3, 10, 6, (90, 200, 90))            # green slab
    rect(20, 2, 12, 9, (65, 165, 240), False)   # blue hollow frame
    rect(23, 5, 3, 3, (240, 240, 240))          # white glyph inside the frame
    rect(38, 4, 7, 7, (230, 65, 75))            # red block
    rect(6, 14, 4, 12, (180, 120, 220))         # violet pillar
    rect(16, 20, 18, 4, (170, 170, 168))        # grey readout bar...
    rect(18, 21, 10, 2, (91, 91, 91))           # ...its dark track
    for i, x in enumerate((29, 31, 33)):        # ...and cyan energy ticks
        rect(x, 21, 1, 2, (128, 218, 253))
    rect(39, 16, 6, 3, (235, 195, 50))          # yellow ledge
    rect(40, 24, 4, 6, (235, 195, 50))          # yellow post
    for d in range(5):                           # orange diagonal
        scene[27 + d - 4][12 + d] = (250, 140, 40)
    return scene


def aperture_mask(cx: int, cy: int) -> set[tuple[int, int]]:
    return {(x, y) for y in range(HEIGHT) for x in range(WIDTH)
            if (x - cx) ** 2 + (y - cy) ** 2 <= RADIUS * RADIUS}


def frame_png(scene, visible) -> bytes:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    px = image.load()
    for x, y in visible:
        r, g, b = scene[y][x]
        px[x, y] = (r, g, b, 255)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def serpentine_path() -> list[str]:
    """Arrow commands covering every aperture tile: 6x4 grid of centres, 23 moves."""
    moves = []
    for row in range(4):
        moves.extend(["ACTION4" if row % 2 == 0 else "ACTION3"] * 5)
        if row < 3:
            moves.append("ACTION2")
    return moves


PARTIAL_PATH = ["ACTION4", "ACTION4", "ACTION2", "ACTION3", "ACTION1", "ACTION4"]  # revisits (12,4)/(20,4)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def _json_bytes(value, indent: int = 2) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=indent, sort_keys=True) + "\n").encode("ascii")


def generate_recording(rec_id: str, commands: list[str], description: str, partition: str,
                       scene) -> dict:
    rel = f"recordings/events_tests/{rec_id}"
    rec_dir = DATA / "recordings" / "events_tests" / rec_id
    cx, cy = RADIUS // 2, RADIUS // 2  # (4, 4)
    known: set[tuple[int, int]] = set()
    moves, eval_frames, frames_meta, files = [], [], [], {}
    actions = [None] + commands
    total = WIDTH * HEIGHT
    for index, action in enumerate(actions):
        if action is not None:
            dx, dy = ARROWS[action]
            cx = min(max(cx + dx, 0), WIDTH - 1)
            cy = min(max(cy + dy, 0), HEIGHT - 1)
        visible = aperture_mask(cx, cy)
        known |= visible
        png = frame_png(scene, visible)
        digest = sha256(png).hexdigest()
        at_seconds = round(index * 0.25, 2)
        frame_dir = rec_dir / str(index)
        _write(frame_dir / "image.png", png)
        state = {
            "action_data": {},
            "action_directory": str(index) if action is not None else None,
            "action_path": [str(index)] if action is not None else [],
            "at_seconds": at_seconds,
            "game_directory": "events_tests",
            "game_id": "events_tests",
            "image_hash": digest[:16],
            "incoming_action": action,
            "kind": "synthetic_visual_memory_frame",
            "level": "1",
            "parent_node": f"../{index - 1}" if index else None,
            "recorded_at": "2000-01-01T00:00:00Z",
            "state": "NOT_FINISHED",
            "step_count": index,
        }
        _write(frame_dir / "state.json", _json_bytes(state))
        moves.append({
            "action": action, "at_seconds": at_seconds, "data": {},
            "directory": f"data/{rel}/{index}", "index": index, "level": "1",
            "recorded_at": "2000-01-01T00:00:00Z", "state": "NOT_FINISHED",
        })
        eval_frames.append({
            "apertureCenter": [cx, cy], "atSeconds": at_seconds,
            "completeCoverage": len(known) == total,
            "cumulativeKnownPixels": len(known), "frameId": str(index),
            "sha256": digest, "visiblePixels": len(visible),
        })
        frames_meta.append({"frameId": str(index), "image": f"{rel}/{index}/image.png",
                            "order": index, "state": f"{rel}/{index}/state.json"})
        files[f"{rel}/{index}/image.png"] = sha256(png).hexdigest()
        files[f"{rel}/{index}/state.json"] = sha256(_json_bytes(state)).hexdigest()
    recording = {
        "description": "Synthetic visual observation sequence; expected results are separate and recognition has not run.",
        "fixture_suite": SUITE, "game_directory": "events_tests", "game_id": "events_tests",
        "kind": "arc3_play_recording", "last_event": "fixture_created", "level": "1",
        "level_directory": f"data/{rel}", "moves": moves, "session_id": None,
        "source": "synthetic_visual_memory_tests", "started_at": "2000-01-01T00:00:00Z",
        "updated_at": "2000-01-01T00:00:00Z",
    }
    _write(rec_dir / "recording.json", _json_bytes(recording))
    files[f"{rel}/recording.json"] = sha256(_json_bytes(recording)).hexdigest()
    evaluation = {
        "baselineStatus": "fixture_unit_baseline_only_not_workbench_execution",
        "description": description,
        "frames": eval_frames,
        "groundTruthIsRecognizerInput": False,
        "partition": partition,
        "recognizerStatus": "not_run",
        "schemaVersion": 1,
        "suiteId": SUITE,
        "teacher": {
            "fullSceneRgb": [list(scene[y][x]) for y in range(HEIGHT) for x in range(WIDTH)],
            "height": HEIGHT, "radius": RADIUS, "sceneVariant": SCENE_VARIANT,
            "source": "teacher_only_full_scene_never_accumulator_input",
            "staticCamera": True, "width": WIDTH,
        },
        "testId": TEST_ID,
    }
    eval_rel = f"evaluation/events_tests/{rec_id}/evaluation.json"
    _write(DATA / "evaluation" / "events_tests" / rec_id / "evaluation.json", _json_bytes(evaluation))
    files[eval_rel] = sha256(_json_bytes(evaluation)).hexdigest()
    return {
        "sequence": {
            "controlProtocol": None, "directory": rel, "evaluation": eval_rel,
            "frameCount": len(actions), "frames": frames_meta, "id": rel,
            "label": rec_id.removeprefix("spotlight_arrows_").replace("_", " "),
            "observerAssessment": None, "partition": partition, "testId": TEST_ID,
        },
        "files": files,
    }


DOCUMENTATION = """# Reconstruct a static scene through an arrow-commanded spotlight

The circular sensor aperture is moved by DISCRETE ARROW COMMANDS, not pointer
coordinates: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right, one 8 px step
per command. Each frame's `incoming_action` in state.json is the only movement
evidence; `action_data` is empty. Everything outside the aperture is occluded by
darkness (RGB and alpha zero) - darkness hides, it never erases.

## Task

Correlate the arrow command received between frames with the aperture's visible
motion, and accumulate previously observed pixels while the spotlight moves.
Observed black inside the aperture (alpha 255) is knowledge; black with alpha 0
remains unknown. Previously seen pixels persist after the spotlight moves on.

## Recordings

* `spotlight_arrows_train_a` - a serpentine scan (23 arrow commands) that
  eventually reveals every pixel of the static 48x32 scene.
* `spotlight_arrows_control_partial` - a short partial walk with a revisit;
  unobserved scene cells must remain unknown and repeats add no new knowledge.

Only the evaluator carries the full scene. Reconstruction is exact
registered-pixel accumulation through the moving hole; moving the aperture does
not mean objects appeared or disappeared.
"""


def main() -> None:
    scene = build_scene()
    results = [
        generate_recording(
            "spotlight_arrows_train_a", serpentine_path(),
            "Arrow-commanded serpentine scan: every arrow command moves the aperture one step; the full static scene is eventually revealed.",
            "training", scene),
        generate_recording(
            "spotlight_arrows_control_partial", PARTIAL_PATH,
            "Arrow-commanded partial walk with a revisit: previously seen pixels persist, unobserved cells stay unknown.",
            "training_control", scene),
    ]
    doc_rel = "recordings/events_tests/documentation/spotlight_arrows.md"
    doc_bytes = DOCUMENTATION.encode("ascii")
    _write(DATA / Path(doc_rel), doc_bytes)

    dataset_path = DATA / "dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    test_entry = {
        "documentation": doc_rel, "group": "Events", "id": TEST_ID,
        "recordings": [r["sequence"]["id"] for r in results],
        "summary": "Accumulate a static scene through a spotlight moved by discrete arrow commands (ACTION1-4); the command stream is the only motion evidence.",
        "title": "Spotlight scene by arrow commands",
    }
    dataset["tests"] = [t for t in dataset["tests"] if t["id"] != TEST_ID] + [test_entry]
    new_ids = {r["sequence"]["id"] for r in results}
    dataset["sequences"] = [s for s in dataset["sequences"] if s["id"] not in new_ids] + \
                           [r["sequence"] for r in results]
    dataset["files"][doc_rel] = sha256(doc_bytes).hexdigest()
    for r in results:
        dataset["files"].update(r["files"])
    dataset["inventory"] = {
        "frames": sum(s["frameCount"] for s in dataset["sequences"]),
        "sequences": len(dataset["sequences"]),
        "symbolicExamples": dataset["inventory"]["symbolicExamples"],
        "tests": len(dataset["tests"]),
    }
    _write(dataset_path, _json_bytes(dataset, indent=1))
    for r in results:
        seq = r["sequence"]
        print(f"{seq['id']}: {seq['frameCount']} frames, partition {seq['partition']}")
    print("dataset.json updated:", dataset["inventory"])


if __name__ == "__main__":
    main()
