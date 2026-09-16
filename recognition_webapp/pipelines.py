"""Actual OpenCV and SWI-Prolog recognition, using memory and process pipes."""

import base64
from collections import defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from recognition import validate
from frame_metta import build_frame_metta
from shape_core import _canon_key, _identity_name, _proportional_cells


ROOT = Path(__file__).resolve().parent
# Prolog rules now live in the installable SWI pack (prolog/omega_vision). pipeline_bridge.pl
# ensure_loads its co-located rule files relative to its own directory, so they move together.
PROLOG_DIR = ROOT.parent / "prolog" / "omega_vision" / "prolog" / "omega_vision"
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class PipelineError(RuntimeError):
    pass


def capabilities() -> dict:
    import importlib.util

    missing = [name for name in ("cv2", "numpy", "scipy", "PIL", "skimage") if importlib.util.find_spec(name) is None]
    return {"opencv": not missing, "missing_python_modules": missing, "prolog": shutil.which("swipl") is not None}


def _source(payload: dict):
    from PIL import Image, ImageOps, UnidentifiedImageError

    encoded = payload.get("image")
    if encoded is not None:
        if not isinstance(encoded, dict) or not isinstance(encoded.get("base64"), str):
            raise ValueError("Image must contain base64-encoded PNG, JPEG, or WebP bytes.")
        try:
            data = base64.b64decode(encoded["base64"], validate=True)
        except ValueError as error:
            raise ValueError("Image is not valid base64.") from error
        if not 0 < len(data) <= MAX_IMAGE_BYTES:
            raise ValueError("Image must contain at most 10 MB.")
        try:
            with Image.open(BytesIO(data)) as original:
                if original.format not in ("PNG", "JPEG", "WEBP"):
                    raise ValueError("Use PNG, JPEG, or WebP.")
                if original.width * original.height > 4_194_304 or min(original.size) < 2:
                    raise ValueError("Image must be at least 2 x 2 and at most 4 megapixels.")
                original.load()
                image = ImageOps.exif_transpose(original).copy()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError(f"Could not decode image: {error}") from error
        source = {"kind": "original_image", "sha256": sha256(data).hexdigest(), "bytes": len(data)}
    else:
        grid, palette, _background = validate(payload)
        width, height = len(grid[0]), len(grid)
        image = Image.new("RGB", (width, height))
        colors = [tuple(bytes.fromhex(color[1:])) for color in palette]
        image.putdata([colors[index] for row in grid for index in row])
        if payload["pipeline"] == "opencv":
            image = image.resize((width * 8, height * 8), Image.Resampling.NEAREST)
        source = {"kind": "edited_grid", "render_scale": 8 if payload["pipeline"] == "opencv" else 1}
    source["width"], source["height"] = image.size
    return image, source


def _run_prolog(payload: dict) -> dict:
    executable = shutil.which("swipl")
    if executable is None:
        raise PipelineError("SWI-Prolog is missing. Install it and put swipl on PATH; no substitute pipeline was run.")
    try:
        result = subprocess.run(
            [executable, "-q", "-f", "none", "-s", str(PROLOG_DIR / "pipeline_bridge.pl"), "-g", "main", "-t", "halt"],
            input=json.dumps(payload, allow_nan=False), text=True, encoding="utf-8",
            capture_output=True, timeout=30, cwd=PROLOG_DIR,
        )
    except subprocess.TimeoutExpired as error:
        raise PipelineError("SWI-Prolog exceeded 30 seconds. Try a smaller image.") from error
    if result.returncode != 0:
        raise PipelineError(f"SWI-Prolog failed: {result.stderr.strip() or 'no result returned'}")
    try:
        output = json.loads(result.stdout)
    except ValueError as error:
        raise PipelineError("SWI-Prolog did not return valid JSON.") from error
    if result.stderr.strip():
        output["diagnostics"] = result.stderr.strip()
    return output


def _prepare_prolog_image(image):
    from PIL import Image

    image = image.convert("RGB")
    if max(image.size) > 32:
        factor = 32 / max(image.size)
        image = image.resize(
            (max(1, round(image.width * factor)), max(1, round(image.height * factor))),
            Image.Resampling.NEAREST,
        )
    quantized = image.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    pixels = list(quantized.tobytes())
    colors = quantized.getpalette()
    used = sorted(set(pixels))
    indices = {old: new for new, old in enumerate(used)}
    palette = ["#" + bytes(colors[index * 3:index * 3 + 3]).hex() for index in used]
    grid = [[indices[pixels[y * image.width + x]] for x in range(image.width)] for y in range(image.height)]
    return quantized.convert("RGB"), grid, palette


def _render_context_facts(context: dict) -> str:
    """Render reserved-input evidence (state.json commands etc.) as frame_context/2 facts."""
    lines = ["% Input evidence from the recording's reserved state.json (source data, not pipeline output)."]
    for key in sorted(context):
        value = context[key]
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, str):
            rendered = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        else:
            rendered = repr(value)
        lines.append(f"frame_context({key}, {rendered}).")
    return "\n".join(lines) + "\n"


def run_pipeline(payload: object) -> dict:
    if not isinstance(payload, dict) or payload.get("pipeline") not in ("opencv", "prolog"):
        raise ValueError("Choose the opencv or prolog pipeline.")
    mode = payload["pipeline"]
    w_engine = payload.get("w_engine", "crack")
    if w_engine not in ("old", "new", "crack"):
        raise ValueError("w_engine must be 'old', 'new', or 'crack'.")
    strong_edge_pct = payload.get("strong_edge_pct", 1)
    if type(strong_edge_pct) not in (int, float) or not 0 < strong_edge_pct <= 100:
        raise ValueError("strong_edge_pct must be a number in (0, 100].")
    old_strong_edge_pct = payload.get("old_strong_edge_pct", 25)
    if type(old_strong_edge_pct) not in (int, float) or not 0 < old_strong_edge_pct <= 100:
        raise ValueError("old_strong_edge_pct must be a number in (0, 100].")
    upscale = payload.get("upscale", 1)
    if type(upscale) is not int or not 1 <= upscale <= 4:
        raise ValueError("upscale must be an integer from 1 to 4.")
    crack_angle_tol = payload.get("crack_angle_tol", 40)
    if type(crack_angle_tol) not in (int, float) or not 0 <= crack_angle_tol <= 90:
        raise ValueError("crack_angle_tol must be a number from 0 to 90.")
    frame = payload.get("frame")
    if frame is not None and (
        not isinstance(frame, dict) or set(frame) != {"sequenceId", "frameId"} or
        any(not isinstance(frame[key], str) or not 1 <= len(frame[key]) <= 512 or
            any(ord(char) < 32 for char in frame[key]) for key in ("sequenceId", "frameId"))
    ):
        raise ValueError("Frame context must contain nonempty sequenceId and frameId strings.")
    context = payload.get("context")
    if context is not None and (
        not isinstance(context, dict) or
        any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) or
            not (isinstance(value, (str, bool)) or type(value) in (int, float))
            for key, value in context.items())
    ):
        raise ValueError("context must map identifier keys to scalar str/int/float/bool values.")
    context = context or {}
    if shutil.which("swipl") is None:
        raise PipelineError("SWI-Prolog is required for this pipeline. Put swipl on PATH.")
    started = time.perf_counter()
    try:
        from pixels_to_regions import _draw_parts_debug
        from group_acceptance import (
            parse_current_frame_evidence, prepare_current_frame_group_evidence,
            render_group_acceptance_input, parse_group_acceptance_result,
        )

        image, source = _source(payload)
        cv_result = None
        if mode == "opencv":
            import cv2
            from pixels_to_regions_cv import extract_region_facts_cv

            tolerance = payload.get("tolerance", 24)
            if type(tolerance) is not int or not 1 <= tolerance <= 64:
                raise ValueError("OpenCV color tolerance must be an integer from 1 to 64.")
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            try:
                cv_result = extract_region_facts_cv(buffer, tolerance=tolerance, max_dim=256, upscale=upscale)
            except cv2.error as error:
                raise PipelineError(f"OpenCV failed: {error}") from error
            image = cv_result.pop("image")
            elapsed_cv = round((time.perf_counter() - started) * 1000)
            prolog_input = {"mode": "opencv", "facts": cv_result["prolog"], "w_engine": w_engine, "strong_edge_pct": strong_edge_pct, "old_strong_edge_pct": old_strong_edge_pct, "crack_angle_tol": crack_angle_tol}
            prolog = _run_prolog(prolog_input)
            raw_cells = {
                part["id"]: [[x, y] for y, left, right in part["pixelRuns"] for x in range(left, right + 1)]
                for part in cv_result["parts"]
            }
            stages = [
                {"engine": "OpenCV", "version": cv2.__version__, "status": "executed", "milliseconds": elapsed_cv},
                {"engine": "SWI-Prolog", "version": prolog["version"], "status": "executed", "rules": ["group_regions.pl", "turtle_programs.pl"]},
            ]
        else:
            image, grid, palette = _prepare_prolog_image(image)
            prolog_input = {"mode": "prolog", "grid": grid, "palette": palette, "w_engine": w_engine, "strong_edge_pct": strong_edge_pct, "old_strong_edge_pct": old_strong_edge_pct, "crack_angle_tol": crack_angle_tol}
            prolog = _run_prolog(prolog_input)
            raw_cells = {part["id"]: part["cells"] for part in prolog["parts"]}
            stages = [{"engine": "SWI-Prolog", "version": prolog["version"], "status": "executed",
                       "rules": ["shape_finder.pl", "group_regions.pl", "turtle_programs.pl"]}]
    except ImportError as error:
        raise PipelineError(f"Missing pipeline dependency: {error}. Run python -m pip install -r requirements.txt.") from error

    preview = BytesIO()
    image.save(preview, format="PNG")
    if frame is None:
        frame = {
            "sequenceId": source["kind"],
            "frameId": source.get("sha256") or sha256(preview.getvalue()).hexdigest(),
        }
    geometry = {
        "width": image.width, "height": image.height,
        "polygons": {
            part["id"]: {"outer": part["polygons"][0] if part["polygons"] else [], "holes": part["holes"]}
            for part in prolog["parts"]
        },
    }
    evidence = parse_current_frame_evidence(prolog["facts"], prolog["group_facts"], geometry)
    # G = groups the active engine and the Original (old) engine BOTH produce
    # (symmetric agreement, no priority). Any foreground region the two disagree
    # on is individualised as its own singleton G, so G still covers everything.
    if w_engine == "old":
        other_groups = prolog["part_groups"]
    else:
        other_groups = [{"members": members} for members in prolog["old_groups"]]
    active_sets = {frozenset(group["members"]) for group in prolog["part_groups"]}
    other_sets = {frozenset(group["members"]) for group in other_groups}
    agreed_sets = active_sets & other_sets
    all_foreground = set().union(*other_sets) if other_sets else set()
    covered = set().union(*agreed_sets) if agreed_sets else set()
    accepted = []
    for members in agreed_sets:
        accepted.append({"members": sorted(members), "mode": "engine_consensus", "provenance": {"score": 1.0}})
    for region in sorted(all_foreground - covered):
        accepted.append({"members": [region], "mode": "individualized", "provenance": {"score": 0.0}})
    for index, group in enumerate(sorted(accepted, key=lambda g: (-len(g["members"]), g["members"])), 1):
        group["id"] = f"g{index}"
    mirror_groups = accepted
    acceptance = {"acceptedGroups": mirror_groups, "rejections": [], "exactRejections": []}
    acceptance_facts = "% G = agreement of active and old W engines (else individualized)\n" + "".join(
        f"accepted_group({group['id']}, [{','.join(group['members'])}]).\n" for group in mirror_groups
    )
    prolog["accepted_groups"] = mirror_groups
    prolog["visual_groups"] = evidence["visualGroups"]
    prolog["acceptance"] = acceptance
    areas = {part["id"]: part["area"] for part in prolog["parts"]}
    group_layers = {}
    for layer, groups in (
        ("G", acceptance["acceptedGroups"]), ("W", prolog["part_groups"]), ("V", evidence["visualGroups"]),
    ):
        group_layers[layer] = [
            {
                **group, "layer": layer,
                "area": sum(areas[member] for member in group["members"]),
                "reason": group.get("mode") or group.get("method") or "prolog_grouping",
            }
            for group in groups
        ]

    objects = []
    grouped = defaultdict(list)
    for part in prolog["parts"]:
        if part["id"] in prolog["background"]:
            continue
        cells = raw_cells.get(part["id"])
        if not cells:
            raise PipelineError(f"Pipeline omitted the observed cells for {part['id']}.")
        min_x, min_y = min(x for x, _ in cells), min(y for _, y in cells)
        width, height = max(x for x, _ in cells) - min_x + 1, max(y for _, y in cells) - min_y + 1
        canonical = _canon_key(_proportional_cells([(x - min_x, y - min_y) for x, y in cells]))
        identity = "shape-" + sha256(repr(canonical).encode("ascii")).hexdigest()[:16]
        grouped[identity].append(part["id"])
        objects.append({
            "id": part["id"], "shape_id": identity, "name": _identity_name(canonical),
            "geometry": f"{mode} region", "color": part["color"], "area": part["area"],
            "bounds": [min_x, min_y, width, height], "cells": cells,
            "canonical_cells": [list(cell) for cell in canonical],
            "hole_count": len(part["holes"]), "adjacent_to": part["adjacent"],
            "polygons": part["polygons"], "holes": part["holes"],
            "midlines": part["midlines"], "fillpoints": part["fillpoints"],
        })
    polygons = {
        part["id"]: {
            "outer": [tuple(point) for point in part["polygons"][0]] if part["polygons"] else [],
            "holes": [[tuple(point) for point in ring] for ring in part["holes"]],
        }
        for part in prolog["parts"]
    }
    midlines = {part["id"]: [[tuple(point) for point in line] for line in part["midlines"]] for part in prolog["parts"]}
    fillpoints = {part["id"]: [tuple(point) for point in part["fillpoints"]] for part in prolog["parts"]}
    debug_image = BytesIO()
    _draw_parts_debug(image, polygons, midlines, fillpoints).save(debug_image, format="PNG")
    metta = build_frame_metta(frame, source, image.width, image.height, mode, prolog, objects, context=context)
    metta_name = "frame-" + re.sub(r"[^A-Za-z0-9_.-]", "_", frame["frameId"])[:64] + ".metta"
    warnings = [
        "Background and groups are inferred by the original Prolog rules, not the grid editor's background selection.",
        "Contours are approximate; no exact reconstruction of the original image is claimed.",
    ]
    if mode == "opencv":
        warnings.append(f"OpenCV kept {cv_result['regionCount']} of {cv_result['blobCount']} blobs; minimum ordinary region area is {cv_result['minArea']} pixels.")
    else:
        warnings.append("Pure Prolog uses at most 32 x 32 cells and 16 colors; the original shape finder omits regions smaller than four cells.")
    artifacts = [
        {"name": metta_name, "media_type": "text/plain", "content": metta},
        {"name": "regions.pl", "media_type": "text/plain", "content": prolog["facts"]},
        {"name": "groups.pl", "media_type": "text/plain", "content": prolog["group_facts"]},
        {"name": "acceptance.pl", "media_type": "text/plain", "content": acceptance_facts},
        {"name": "turtles.pl", "media_type": "text/plain", "content": prolog["turtle_facts"]},
        {"name": "geometry.json", "media_type": "application/json", "content": json.dumps(
            {"parts": prolog["parts"], "groups": prolog["groups"], "opencv": cv_result}, allow_nan=False, indent=2)},
    ]
    if context:
        artifacts.insert(4, {"name": "context.pl", "media_type": "text/plain",
                             "content": _render_context_facts(context)})
    return {
        "schema_version": 1, "native": True, "pipeline": mode, "stages": stages,
        "source": source, "frame": frame, "width": image.width, "height": image.height,
        "context": context,
        "metta": {"name": metta_name, "content": metta},
        "preview": base64.b64encode(preview.getvalue()).decode("ascii"),
        "debug_image": base64.b64encode(debug_image.getvalue()).decode("ascii"),
        "objects": objects, "object_count": len(objects), "shape_count": len(grouped),
        "foreground_cells": sum(obj["area"] for obj in objects),
        "repeated_shapes": [{"shape_id": key, "objects": ids} for key, ids in grouped.items() if len(ids) > 1],
        "prolog": prolog, "group_layers": group_layers, "opencv": cv_result, "artifacts": artifacts, "warnings": warnings,
        "milliseconds": round((time.perf_counter() - started) * 1000),
        "files_written": 0, "directories_created": 0,
    }
