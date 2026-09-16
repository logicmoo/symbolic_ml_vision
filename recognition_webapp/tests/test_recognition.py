import base64
from functools import cache
from hashlib import sha256
import http.client
from io import BytesIO
import json
import os
import re
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import make_server
from recognition import examples, recognize
from shape_core import _TETROMINOES
from pipelines import PipelineError, run_pipeline
from demos import DemoCatalog
from expectations import frame_expectations


DEFAULT_SEQUENCES = (
    "recordings/events_tests/attached",
    "recordings/events_tests/occlude",
    "recordings/events_tests/control_actor_calibration_train_a",
    "recordings/events_tests/push_chain_train_a",
)
DATA_ROOT = Path(os.environ.get(
    "RECOGNITION_DATA_ROOT",
    Path(__file__).resolve().parents[2] / "data" / "omega_vision",
))


@cache
def recorded_frames():
    root = DATA_ROOT
    if not root.is_dir():
        raise FileNotFoundError(
            f"Visual-sequence data is missing: {root}. "
            "Set RECOGNITION_DATA_ROOT to an existing exported data/omega_vision directory."
        )
    root = root.resolve(strict=True)
    catalog = json.loads((root / "dataset.json").read_bytes())
    selected = os.environ.get("RECOGNITION_SEQUENCE_IDS")
    identifiers = tuple(selected.split(",")) if selected else DEFAULT_SEQUENCES
    sequences = {sequence["id"]: sequence for sequence in catalog["sequences"]}
    if identifiers == ("all",):
        identifiers = tuple(sequences)
    frames = []
    for identifier in identifiers:
        sequence = sequences[identifier]
        ordered = sorted(sequence["frames"], key=lambda item: item["order"])
        assert len(ordered) == sequence["frameCount"], f"Incorrect frame count: {identifier}"
        assert len({frame["order"] for frame in ordered}) == len(ordered), f"Duplicate frame order: {identifier}"
        for frame in ordered:
            name = frame["image"]
            parts = name.split("/")
            assert parts[0] in ("recordings", "curated") and len(parts) > 1, name
            assert all(part not in ("", ".", "..") and ":" not in part and "\\" not in part for part in parts), name
            path = root.joinpath(*parts).resolve(strict=True)
            assert path.is_relative_to(root), f"Frame path escaped data root: {name}"
            raw = path.read_bytes()
            digest = sha256(raw).hexdigest()
            assert raw.startswith(b"\x89PNG\r\n\x1a\n"), name
            assert digest == catalog["files"][name], f"Frame hash mismatch: {name}"
            frames.append({
                "sequence": identifier, "frame_id": frame["frameId"], "order": frame["order"],
                "path": path, "sha256": digest, "bytes": len(raw),
                "image": {"base64": base64.b64encode(raw).decode("ascii")},
            })
    assert frames, "The selected visual sequences contain no frames."
    return frames


def recorded_payload(frame, pipeline):
    return {
        "pipeline": pipeline, "image": frame["image"],
        "frame": {"sequenceId": frame["sequence"], "frameId": frame["frame_id"]},
    }


class RecognitionTests(unittest.TestCase):
    def test_original_topology_example(self):
        result = recognize(examples()[0])
        self.assertEqual(result["object_count"], 2)
        self.assertEqual(sum(obj["hole_count"] for obj in result["objects"]), 1)
        self.assertTrue(result["exact_reconstruction"])
        self.assertIn("empty_box", [obj["name"] for obj in result["objects"]])

    def test_color_position_rotation_reflection_and_scale_share_shape(self):
        grid = [[0] * 24 for _ in range(16)]
        cells = _TETROMINOES["tetromino_L"]
        for x, y in cells:
            grid[y + 1][x + 1] = 1
            for dy in range(2):
                for dx in range(2):
                    grid[x * 2 + 8 + dy][y * 2 + 13 + dx] = 2
        result = recognize({"grid": grid, "palette": ["#000000", "#ff0000", "#00ff00"]})
        self.assertEqual(result["object_count"], 2)
        self.assertEqual(result["shape_count"], 1)
        self.assertEqual(len(result["repeated_shapes"]), 1)
        self.assertNotEqual(result["objects"][0]["color"], result["objects"][1]["color"])

    def test_no_background_preserves_all_colors(self):
        result = recognize({"grid": [[0, 1]], "palette": ["#000000", "#ffffff"], "background": None})
        self.assertEqual(result["object_count"], 2)
        self.assertEqual(result["objects"][0]["adjacent_to"], ["object-2"])
        self.assertTrue(result["exact_reconstruction"])

    def test_contact_uses_cells_not_overlapping_bounds(self):
        result = recognize({"grid": [[1, 1, 1], [1, 0, 1], [1, 1, 1]], "palette": ["#000000", "#ffffff"]})
        self.assertEqual(result["objects"][0]["adjacent_to"], [])
        self.assertEqual(result["objects"][0]["hole_count"], 1)

    def test_no_mutation_or_retention(self):
        payload = examples()[1]
        before = json.dumps(payload)
        self.assertEqual(recognize(payload), recognize(payload))
        self.assertEqual(json.dumps(payload), before)
        self.assertEqual(recognize(examples()[2])["object_count"], 0)

    def test_validation(self):
        for payload in [
            None, {}, {"grid": []}, {"grid": [[True]], "palette": ["#000000"]},
            {"grid": [[1]], "palette": ["#000000"]},
            {"grid": [[0], [0, 0]], "palette": ["#000000"]},
            {"grid": [[0]], "palette": ["red"]},
            {"grid": [[0, 1]], "palette": ["#ffffff", "#FFFFFF"]},
            {"grid": [[0]], "palette": ["#000000"], "background": -1},
            {"grid": [[0]], "palette": ["#000000"], "background": True},
            {"grid": [[0] * 65], "palette": ["#000000"]},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                recognize(payload)

    def test_region_limit(self):
        with self.assertRaisesRegex(ValueError, "separate regions"):
            recognize({
                "grid": [[(x + y) % 2 for x in range(64)] for y in range(64)],
                "palette": ["#000000", "#ffffff"], "background": None,
            })


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0, DATA_ROOT)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=45)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), response.getheader("Cache-Control")
        finally:
            connection.close()

    def test_ui_and_health(self):
        for path in ("/omega_vision/ui/", "/omega_vision/ui/shapes", "/omega_vision/ui/app.js",
                     "/omega_vision/ui/style.css", "/omega_vision/ui/clause_explorer.js",
                     "/omega_vision/ui/clause_explorer.css", "/omega_vision/api/v1/health",
                     "/omega_vision/api/v1/examples", "/omega_vision/api/v1/capabilities"):
            status, body, cache = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
            self.assertEqual(cache, "no-store")

    def test_root_redirects_to_namespaced_ui(self):
        for path, target in (("/", "/omega_vision/ui/"), ("/shapes", "/omega_vision/ui/shapes")):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                response.read()
                self.assertEqual(response.status, 302)
                self.assertEqual(response.getheader("Location"), target)
            finally:
                connection.close()

    def test_original_explorer_is_hash_bound_and_source_routes_are_allowlisted(self):
        root = Path(__file__).resolve().parents[1] / "clause_explorer"
        provenance = json.loads((root / "upstream.json").read_bytes())
        for name, expected in provenance["files"].items():
            self.assertEqual(sha256((root / "upstream" / name).read_bytes()).hexdigest(), expected, name)
        self.assertEqual(sha256((root / "explorer.css").read_bytes()).hexdigest(), provenance["css"]["extractedHash"])
        status, source, _ = self.request("GET", "/clause-explorer-source?file=component")
        self.assertEqual(status, 200)
        self.assertEqual(source, (root / "upstream/packages/omega_vision_ui/src/components/PrologClauseExplorer.tsx").read_bytes())
        self.assertIn(b"Most clauses first", source)
        for query in ("file=../../app.py", "file=component&file=css", "file=unknown"):
            self.assertEqual(self.request("GET", "/clause-explorer-source?" + query)[0], 404)

    def test_editor_style_nonce_is_per_document_without_inline_script_permission(self):
        nonces = []
        for _ in range(2):
            connection = http.client.HTTPConnection("127.0.0.1", self.port)
            try:
                connection.request("GET", "/omega_vision/ui/shapes")
                response = connection.getresponse()
                page = response.read().decode()
                nonce = re.search(r'name="clause-explorer-style-nonce" content="([^"]+)"', page).group(1)
                policy = response.getheader("Content-Security-Policy")
                self.assertIn(f"style-src 'self' 'nonce-{nonce}'", policy)
                self.assertIn("script-src 'self';", policy)
                self.assertNotIn("unsafe-inline", policy)
                self.assertNotIn("unsafe-eval", policy)
                nonces.append(nonce)
            finally:
                connection.close()
        self.assertNotEqual(*nonces)

    def test_source_syntax_endpoint_uses_python_and_never_recognizes(self):
        sources = [
            {"name": "frame-2.metta", "text": "(part r2 #0c1018)"},
            {"name": "deductions-2.pl", "text": "group(g7, members(['e4']))."},
            {"name": "geometry.json", "text": '{"regions":[]}'},
        ]
        with patch("web_api.run_pipeline", side_effect=AssertionError("Source views must not run inference")):
            status, raw, cache = self.request("POST", "/omega_vision/api/v1/source-syntax",
                                            json.dumps({"sources": sources}), {"Content-Type": "application/json"})
        result = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(cache, "no-store")
        self.assertEqual(len(result["sources"]), 3)
        self.assertEqual(result["sources"][1]["formats"]["metta"], "(group g7 (members ([] e4)))")
        status, _, _ = self.request("POST", "/omega_vision/api/v1/source-syntax", '{"path":"../private"}',
                                    {"Content-Type": "application/json"})
        self.assertEqual(status, 422)

    def test_demos_and_shapes_have_distinct_page_modes(self):
        _, demos, _ = self.request("GET", "/omega_vision/ui/")
        _, shapes, _ = self.request("GET", "/omega_vision/ui/shapes")
        self.assertIn(b'data-page="demos"', demos)
        self.assertIn(b'data-page="shapes"', shapes)
        self.assertNotIn(b'id="demo-recording"', demos)

    def test_frame_expectations_are_a_separate_read_only_endpoint(self):
        query = urlencode({"test": "deformed", "sequence": "recordings/events_tests/deformed", "frame": "1"})
        status, body, cache = self.request("GET", "/omega_vision/api/v1/demos/expectations?" + query)
        self.assertEqual(status, 200)
        guide = json.loads(body)
        self.assertIn("36", guide["caption"])
        self.assertEqual(guide["events"][0]["description"], "deformed(actor)")
        self.assertEqual(cache, "no-store")
        invalid = urlencode({"test": "carry", "sequence": "recordings/events_tests/deformed", "frame": "1"})
        status, _, _ = self.request("GET", "/omega_vision/api/v1/demos/expectations?" + invalid)
        self.assertEqual(status, 404)

    def test_geometry_api(self):
        status, body, _ = self.request(
            "POST", "/omega_vision/api/v1/recognize", json.dumps(examples()[0]), {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["object_count"], 2)

    def test_recognition_serves_concurrent_requests_without_a_busy_lock(self):
        # Recognition must never reject a request as "busy": overlapping frame requests are served
        # concurrently by the threading server, so several in-flight recognitions all succeed.
        payload = json.dumps(examples()[0])
        results, errors = [], []

        def hit():
            try:
                status, body, _ = self.request(
                    "POST", "/omega_vision/api/v1/recognize", payload, {"Content-Type": "application/json"},
                )
                results.append((status, json.loads(body).get("object_count")))
            except Exception as error:  # pragma: no cover - surfaced via errors assertion
                errors.append(error)

        threads = [threading.Thread(target=hit) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=45)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 8)
        self.assertTrue(all(status == 200 for status, _ in results), results)
        self.assertTrue(all(count == 2 for _, count in results), results)

    def test_recorded_sequence_pipelines_api(self):
        frames = recorded_frames()
        first_sequence = frames[0]["sequence"]
        for frame in frames:
            if frame["sequence"] != first_sequence:
                continue
            for pipeline in ("opencv", "prolog"):
                with self.subTest(pipeline=pipeline, sequence=first_sequence, frame=frame["frame_id"]):
                    status, body, _ = self.request(
                        "POST", "/omega_vision/api/v1/recognize", json.dumps(recorded_payload(frame, pipeline)),
                        {"Content-Type": "application/json"},
                    )
                    self.assertEqual(status, 200, body.decode("utf-8"))
                    result = json.loads(body)
                    self.assertEqual(result["source"]["sha256"], frame["sha256"])
                    self.assertEqual(result["source"]["kind"], "original_image")
                    self.assertEqual(result["pipeline"], pipeline)

    def test_demo_dropdown_contains_real_tests_and_numeric_frame_order(self):
        status, body, _ = self.request("GET", "/omega_vision/api/v1/demos")
        self.assertEqual(status, 200)
        listed = json.loads(body)
        manifest = json.loads((DATA_ROOT / "dataset.json").read_bytes())
        self.assertEqual({test["id"] for test in listed["tests"]}, {test["id"] for test in manifest["tests"]})
        self.assertEqual(len(listed["sequences"]), len(manifest["sequences"]))
        for sequence in listed["sequences"]:
            self.assertEqual([frame["order"] for frame in sequence["frames"]],
                             sorted(frame["order"] for frame in sequence["frames"]))
            self.assertNotIn("evaluation", sequence)
            self.assertNotIn("observerAssessment", sequence)

    def test_demo_frame_endpoint_returns_original_png(self):
        frame = recorded_frames()[0]
        query = urlencode({"sequence": frame["sequence"], "frame": frame["frame_id"]})
        status, body, cache = self.request("GET", "/omega_vision/api/v1/demos/frame?" + query)
        self.assertEqual(status, 200)
        self.assertEqual(sha256(body).hexdigest(), frame["sha256"])
        self.assertEqual(body, frame["path"].read_bytes())
        self.assertEqual(cache, "no-store")
        for query in (
            urlencode({"sequence": "../evaluation", "frame": "0"}),
            urlencode({"sequence": frame["sequence"], "frame": "not-a-frame"}),
        ):
            status, body, _ = self.request("GET", "/omega_vision/api/v1/demos/frame?" + query)
            self.assertEqual(status, 404)
            self.assertIn("error", json.loads(body))

    def test_invalid_and_cross_origin_requests(self):
        for method, path, body, headers, expected in [
            ("GET", "/../app.py", None, {}, 404),
            ("GET", "/omega_vision/api/v1/health", None, {"Host": "attacker.invalid"}, 403),
            ("POST", "/omega_vision/api/v1/recognize", "{}", {"Content-Type": "application/json", "Origin": "https://attacker.invalid"}, 403),
            ("POST", "/omega_vision/api/v1/recognize", "{}", {"Content-Type": "text/plain"}, 415),
            ("POST", "/omega_vision/api/v1/recognize", "{", {"Content-Type": "application/json"}, 400),
            ("POST", "/omega_vision/api/v1/recognize", "{}", {"Content-Type": "application/json"}, 422),
        ]:
            with self.subTest(path=path, expected=expected):
                status, response, _ = self.request(method, path, body, headers)
                self.assertEqual(status, expected)
                self.assertIn("error", json.loads(response))


class DemoCatalogTests(unittest.TestCase):
    def test_recordings_can_be_shared_between_tests(self):
        catalog = DemoCatalog(DATA_ROOT)
        shared = recorded_frames()[0]["sequence"]
        original_tests = [test["id"] for test in catalog.tests if shared in test["recordings"]]
        other = next(test for test in catalog.tests if shared not in test["recordings"])
        other["recordings"].append(shared)
        listed = catalog.listing()
        sequence = next(item for item in listed["sequences"] if item["id"] == shared)
        self.assertEqual(set(sequence["testIds"]), {*original_tests, other["id"]})
        self.assertNotIn("testId", sequence)
        self.assertTrue(all(shared in test["recordings"] for test in listed["tests"]
                            if test["id"] in sequence["testIds"]))
        self.assertEqual(len(listed["sequences"]), len(catalog.sequences))
        self.assertEqual(catalog.image(shared, recorded_frames()[0]["frame_id"]),
                         recorded_frames()[0]["path"].read_bytes())

    def test_unsafe_paths_and_hash_mismatches_are_errors(self):
        catalog = DemoCatalog(DATA_ROOT)
        for name in ("../LICENSE", "/absolute", "C:/outside", "recordings\\outside", "a//b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                catalog.path(name)
        frame = recorded_frames()[0]
        listed = catalog.frames(frame["sequence"])[0]
        catalog.files[listed["image"]] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            catalog.image(frame["sequence"], frame["frame_id"])


class FrameExpectationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = DemoCatalog(DATA_ROOT)

    def test_deformation_preserves_authored_area_not_physical_mass(self):
        guide = frame_expectations(self.catalog, "deformed", "recordings/events_tests/deformed", "1")
        self.assertIn("12 by 3", guide["caption"])
        self.assertTrue(any("area unchanged at 36 pixels" in line for line in guide["changes"]))
        self.assertTrue(any("Pixel area is not physical mass" in line for line in guide["limitations"]))

    def test_carry_timing_caution_is_not_hidden_by_oracle_event(self):
        guide = frame_expectations(self.catalog, "carry", "recordings/events_tests/carry", "1")
        self.assertEqual(guide["events"][0]["description"], "start(carry(carrier, cargo))")
        self.assertTrue(any("classify carry no earlier than 2" in line for line in guide["limitations"]))

    def test_plate_state_changes_and_ambiguity_are_explicit(self):
        plate = frame_expectations(self.catalog, "plate_momentary", "recordings/events_tests/plate_momentary_train_a", "3")
        self.assertTrue(any("Door door: open (was closed" in line for line in plate["interpretation"]))
        self.assertEqual(plate["assessment"], "requires_evaluation")
        ambiguous = frame_expectations(self.catalog, "control_actor_calibration", "recordings/events_tests/control_actor_calibration_ambiguous", "0")
        self.assertTrue(any("must remain unresolved" in line for line in ambiguous["interpretation"]))

    def test_shared_recording_does_not_invent_a_test_specific_oracle(self):
        other = next(test for test in self.catalog.tests if test["id"] == "deformed")
        other["recordings"].append("recordings/events_tests/carry")
        guide = frame_expectations(self.catalog, "deformed", "recordings/events_tests/carry", "1")
        self.assertFalse(guide["testSpecificOracle"])
        self.assertEqual(guide["events"], [])
        self.assertTrue(any("no pass oracle was authored" in line for line in guide["limitations"]))

    def test_every_recorded_frame_has_hash_bound_guidance(self):
        for test in self.catalog.tests:
            for identifier in test["recordings"]:
                frames = self.catalog.frames(identifier)
                for frame in frames:
                    with self.subTest(test=test["id"], sequence=identifier, frame=frame["frameId"]):
                        guide = frame_expectations(self.catalog, test["id"], identifier, frame["frameId"])
                        self.assertEqual(guide["frameId"], frame["frameId"])
                        self.assertEqual(guide["sourceSha256"], self.catalog.files[frame["image"]])
                        self.assertTrue(guide["caption"] or guide["context"])


class NativePipelineTests(unittest.TestCase):
    def snapshot(self):
        root = Path(__file__).resolve().parents[1]
        return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in root.rglob("*") if path.is_file()}

    def assert_recorded_result(self, frame, result, pipeline):
        self.assertEqual(result["pipeline"], pipeline)
        self.assertEqual(result["source"]["kind"], "original_image")
        self.assertEqual(result["source"]["sha256"], frame["sha256"])
        self.assertEqual(result["source"]["bytes"], frame["bytes"])
        self.assertTrue(all(stage["status"] == "executed" for stage in result["stages"]))
        self.assertEqual(result["object_count"], len(result["objects"]))
        known_regions = {part["id"] for part in result["prolog"]["parts"]}
        parts = {part["id"]: part for part in result["prolog"]["parts"]}
        for index, group in enumerate(result["prolog"]["part_groups"], 1):
            self.assertEqual(group["id"], f"w{index}")
            self.assertEqual(group["members"], result["prolog"]["groups"][index - 1])
            self.assertEqual(group["area"], sum(parts[identifier]["area"] for identifier in group["members"]))
        for group in result["prolog"]["groups"]:
            self.assertTrue(set(group) <= known_regions)
        for obj in result["objects"]:
            self.assertIn(obj["id"], known_regions)
            self.assertEqual(obj["area"], len(obj["cells"]))
            self.assertEqual(len(obj["cells"]), len({tuple(cell) for cell in obj["cells"]}))
            self.assertTrue(all(0 <= x < result["width"] and 0 <= y < result["height"]
                                for x, y in obj["cells"]))
        self.assertEqual(result["files_written"], 0)
        self.assertEqual(result["directories_created"], 0)
        programs = result["prolog"]["turtle_programs"]
        self.assertEqual(len(programs), result["prolog"]["turtle_facts"].count("turtle_program("))
        for program in programs:
            self.assertIn(program["region"], known_regions)
            self.assertIn(program["kind"], ("outer", "hole", "midline"))
            self.assertEqual(program["commands"][0]["op"], "start")
            self.assertTrue(all(command["op"] in ("start", "turn", "forward", "close", "dot")
                                for command in program["commands"]))
        from PIL import Image
        with Image.open(BytesIO(base64.b64decode(result["debug_image"], validate=True))) as debug, \
                Image.open(BytesIO(base64.b64decode(result["preview"], validate=True))) as preview:
            self.assertEqual(debug.size, (result["width"], result["height"]))
            self.assertNotEqual(debug.tobytes(), preview.tobytes())
        self.assertEqual({item["name"] for item in result["artifacts"]},
                         {"regions.pl", "groups.pl", "acceptance.pl", "turtles.pl", "geometry.json", result["metta"]["name"]})
        self.assertEqual(result["frame"], {"sequenceId": frame["sequence"], "frameId": frame["frame_id"]})
        scope = f'(Frame {frame["sequence"]} {frame["frame_id"]})'
        facts = [line for line in result["metta"]["content"].splitlines() if line and not line.startswith(";")]
        self.assertTrue(facts)
        self.assertTrue(all(scope in line for line in facts))
        self.assertTrue(any(line.startswith("(part ") for line in facts))
        self.assertFalse(any(line.startswith(("(expected", "(teacher", "(carry ", "(missing ", "(appeared ")) for line in facts))
        self.assertEqual(next(artifact["content"] for artifact in result["artifacts"]
                              if artifact["name"] == result["metta"]["name"]), result["metta"]["content"])
        self.assertEqual(sha256(frame["path"].read_bytes()).hexdigest(), frame["sha256"])

    def test_recorded_sequences_opencv_then_prolog_without_files(self):
        import cv2
        import subprocess

        before = self.snapshot()
        for frame in recorded_frames():
            with self.subTest(sequence=frame["sequence"], frame=frame["frame_id"], order=frame["order"]):
                with patch("cv2.findContours", wraps=cv2.findContours) as contours, patch(
                    "pipelines.subprocess.run", wraps=subprocess.run
                ) as prolog:
                    result = run_pipeline(recorded_payload(frame, "opencv"))
                self.assertGreater(contours.call_count, 0)
                prolog_calls = prolog.call_args_list
                self.assertTrue(prolog_calls)
                self.assertTrue(all("pipeline_bridge.pl" in " ".join(call.args[0]) for call in prolog_calls))
                self.assertIn("opencv", [json.loads(call.kwargs["input"])["mode"] for call in prolog_calls])
                self.assertEqual([stage["engine"] for stage in result["stages"]], ["OpenCV", "SWI-Prolog"])
                self.assert_recorded_result(frame, result, "opencv")
        self.assertEqual(before, self.snapshot())

    def test_recorded_sequences_pure_prolog_without_opencv_or_files(self):
        import cv2

        before = self.snapshot()
        with patch("cv2.findContours", side_effect=AssertionError("Pure Prolog must not call OpenCV")):
            for frame in recorded_frames():
                with self.subTest(sequence=frame["sequence"], frame=frame["frame_id"], order=frame["order"]):
                    result = run_pipeline(recorded_payload(frame, "prolog"))
                    self.assertEqual(result["stages"][0]["rules"][0], "shape_finder.pl")
                    self.assertIn("shape_finder_prolog", result["prolog"]["facts"])
                    self.assert_recorded_result(frame, result, "prolog")
        self.assertEqual(before, self.snapshot())

    def test_missing_prolog_is_an_error_not_a_fallback(self):
        with patch("pipelines.shutil.which", return_value=None):
            with self.assertRaisesRegex(PipelineError, "SWI-Prolog"):
                run_pipeline({**examples()[0], "pipeline": "opencv"})

    def test_native_image_validation(self):
        with self.assertRaisesRegex(ValueError, "base64"):
            run_pipeline({"pipeline": "opencv", "image": {"base64": "not valid!"}})
        with self.assertRaisesRegex(ValueError, "tolerance"):
            run_pipeline({**examples()[0], "pipeline": "opencv", "tolerance": 100})
        with self.assertRaisesRegex(ValueError, "Frame context"):
            run_pipeline({**examples()[0], "pipeline": "opencv", "frame": {"sequenceId": "x", "frameId": 0}})

    def test_turtle_commands_and_debug_images_are_exposed_by_both_pipelines(self):
        frame = recorded_frames()[0]
        for pipeline in ("opencv", "prolog"):
            with self.subTest(pipeline=pipeline):
                result = run_pipeline(recorded_payload(frame, pipeline))
                self.assert_recorded_result(frame, result, pipeline)
                self.assertGreater(len(result["prolog"]["turtle_programs"]), 0)

    def test_metta_outputs_do_not_accumulate_across_frames(self):
        first, second = recorded_frames()[:2]
        previous_scope = f'(Frame {first["sequence"]} {first["frame_id"]})'
        for pipeline in ("opencv", "prolog"):
            with self.subTest(pipeline=pipeline):
                earlier = run_pipeline(recorded_payload(first, pipeline))
                later = run_pipeline(recorded_payload(second, pipeline))
                self.assertIn(previous_scope, earlier["metta"]["content"])
                self.assertNotIn(previous_scope, later["metta"]["content"])
                self.assert_recorded_result(second, later, pipeline)


class HudReadoutAndInputEvidenceTests(unittest.TestCase):
    """Regressions for HUD/readout W-grouping and state.json input evidence."""

    HUD_FRAME = DATA_ROOT / "recordings" / "ls20" / "saved_136" / "3"

    def hud_payload(self, **extra):
        image = base64.b64encode((self.HUD_FRAME / "image.png").read_bytes()).decode("ascii")
        return {"pipeline": "opencv", "image": {"base64": image},
                "frame": {"sequenceId": "recordings/ls20/saved_136", "frameId": "3"}, **extra}

    def test_energy_bar_hud_is_one_w_group_with_child_group(self):
        result = run_pipeline(self.hud_payload())
        colors = {obj["id"]: obj["color"] for obj in result["objects"]}
        segments = {i for i, c in colors.items() if c == "#80dafd"}
        self.assertEqual(len(segments), 3, "expected three cyan energy segments")
        w_groups = [set(g["members"]) for g in result["group_layers"]["W"]]
        hud = [g for g in w_groups if segments <= g and any(colors.get(m) == "#aaaaa8" for m in g)]
        self.assertTrue(hud, "energy bar container + segments must form one W group")
        whole = max(hud, key=len)
        self.assertTrue(any(colors.get(m) == "#5b5b5b" for m in whole), "track must join the HUD group")
        children = [g for g in w_groups if g < whole and segments <= g]
        self.assertTrue(children, "HUD contents must also be emitted as a child group")

    def test_state_json_context_becomes_input_evidence(self):
        state = json.loads((self.HUD_FRAME / "state.json").read_bytes())
        context = {k: v for k, v in state.items() if isinstance(v, (str, int, float, bool))}
        self.assertEqual(context["incoming_action"], "ACTION3")
        result = run_pipeline(self.hud_payload(context=context))
        self.assertEqual(result["context"]["incoming_action"], "ACTION3")
        context_pl = next(a["content"] for a in result["artifacts"] if a["name"] == "context.pl")
        self.assertIn('frame_context(incoming_action, "ACTION3").', context_pl)
        self.assertIn("incoming_action ACTION3", result["metta"]["content"])
        with self.assertRaisesRegex(ValueError, "context"):
            run_pipeline(self.hud_payload(context={"bad key!": "x"}))

    def test_first_frame_is_an_appearance_from_virtual_empty_frame(self):
        from frame_pipeline import deduce2_from_payload
        objs = [{"id": "r1", "shape_id": "s1", "color": "#ff0000", "area": 64,
                 "bounds": [10, 10, 8, 8], "hole_count": 0,
                 "cells": [[x, y] for x in range(10, 18) for y in range(10, 18)]}]
        deduced = deduce2_from_payload({
            "sequenceId": "synthetic/appearance-test", "current": {"objects": objs},
            "previous": {"objects": []},
            "currentGroups": {"G": [["r1"]], "W": [["r1"]]}, "previousGroups": {"G": [], "W": []},
            "currentOrder": 0, "previousOrder": -1, "width": 64, "height": 64,
            "userAction": "ACTION3"})
        self.assertEqual(deduced["userAction"], "ACTION3")
        deductions = next(f["content"] for f in deduced["files"] if f["name"] == "deductions.pl")
        self.assertIn('user_action("ACTION3", from_frame(-1), to_frame(0)).', deductions)
        self.assertIn("appeared(e1, frame(0)).", deductions)

    def test_reserved_inputs_are_never_written_and_generated_manifest_is_safe(self):
        from frame_pipeline import _write, clean_generated, is_generated, is_reserved_input
        frame_dir = self.HUD_FRAME
        for name in ("image.png", "state.json"):
            self.assertTrue(is_reserved_input(frame_dir / name))
            self.assertFalse(is_generated(frame_dir / name))
            with self.assertRaisesRegex(ValueError, "reserved input"):
                _write(frame_dir / name, "clobber")
        self.assertTrue(is_generated(frame_dir / "recognition.json"))
        self.assertTrue(is_generated(frame_dir / "context.pl"))
        victims = clean_generated(frame_dir.parent, dry_run=True)
        self.assertFalse(any(is_reserved_input(v) for v in victims))
        # dry run must not delete anything
        self.assertTrue((frame_dir / "image.png").is_file())
        self.assertTrue((frame_dir / "state.json").is_file())


if __name__ == "__main__":
    unittest.main()
