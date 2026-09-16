# Recognition-only copy from logicmoo/omega_vision. LGPL-2.1-or-later.
# Original source SHA-256: ca2809cedf6ae0409f577bcf1943f1cd98c2a349dc3c634ee663504abf058a7f
"""Measurements and result parsing for Prolog-owned current-frame gN acceptance."""
from __future__ import annotations

import base64
from collections import Counter, defaultdict
from itertools import islice, permutations, product
import json
import math
import re
from typing import Any, Iterable, Iterator

import numpy as np
from PIL import Image, ImageDraw


SYMBOLIC_GEOMETRY_TOLERANCE = 0.18
PIXEL_SHAPE_FALLBACK_THRESHOLD = 0.82
PIXEL_SHAPE_UNIQUE_MARGIN = 0.03
PIXEL_COLOR_MASS_TOLERANCE = 0.12
MAX_COLOR_CORRESPONDENCES = 4096
CANONICAL_MASK_SIZE = 64


def _natural_key(value: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([A-Za-z_-]*?)(\d+)", value)
    if not match:
        return value.lower(), 2**31 - 1, value.lower()
    return match.group(1).lower(), int(match.group(2)), value.lower()


def _canonical_members(members: Iterable[str], region_order: dict[str, int]) -> tuple[str, ...]:
    return tuple(sorted(set(members), key=lambda member: (region_order.get(member, 2**31), _natural_key(member))))


def _strip_atom(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_current_frame_evidence(
    extraction_text: str,
    grouping_text: str,
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    regions: dict[str, dict[str, Any]] = {}
    for source_order, match in enumerate(re.finditer(
        r"region\(\s*(\w+)\s*,\s*('(?:[^']|'')*'|[^,]+)\s*,\s*"
        r"(-?\d+(?:\.\d+)?)\s*,\s*centroid\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)\s*\)",
        extraction_text,
    )):
        region_id, color, area, x, y = match.groups()
        regions[region_id] = {
            "id": region_id,
            "color": _strip_atom(color),
            "area": float(area),
            "centroid": [float(x), float(y)],
            "sourceOrder": source_order,
        }

    visual_groups: list[dict[str, Any]] = []
    for source_order, (group_id, method, members) in enumerate(re.findall(
        r"vision_group\(\s*(v\d+)\s*,\s*(\w+)\s*,\s*\[([^\]]*)\]\s*,",
        extraction_text,
    )):
        visual_groups.append({
            "id": group_id,
            "method": method,
            "members": [member.strip() for member in members.split(",") if member.strip()],
            "sourceOrder": source_order,
        })
    if not visual_groups:
        for source_order, (_component, members) in enumerate(re.findall(
            r"opencv_component\(\s*(cc\d+)\s*,\s*\[([^\]]*)\]\s*\)",
            extraction_text,
        )):
            visual_groups.append({
                "id": f"v{source_order + 1}",
                "method": "connected_component",
                "members": [member.strip() for member in members.split(",") if member.strip()],
                "sourceOrder": source_order,
            })

    group_areas = {
        group_id: float(area)
        for group_id, area in re.findall(
            r"group_area\(\s*([gw]\d+)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)",
            grouping_text,
        )
    }
    symbolic_groups: list[dict[str, Any]] = []
    for source_order, (group_id, members) in enumerate(re.findall(
        r"part_group\(\s*([gw]\d+)\s*,\s*\[([^\]]*)\]\s*\)",
        grouping_text,
    )):
        active_id = f"w{group_id[1:]}" if group_id.startswith("g") else group_id
        symbolic_groups.append({
            "id": active_id,
            "sourceId": group_id if group_id != active_id else None,
            "members": [member.strip() for member in members.split(",") if member.strip()],
            "sourceOrder": source_order,
            "area": group_areas.get(group_id),
        })

    relation_patterns = {
        "adjacent": r"adjacent\(\s*(\w+)\s*,\s*(\w+)\s*\)",
        "shared_edge": r"shared_edge\(\s*(\w+)\s*,\s*(\w+)\s*,",
        "encloses": r"encloses\(\s*(\w+)\s*,\s*(\w+)\s*\)",
        "cutout": r"fills_cutout\(\s*(\w+)\s*,\s*(\w+)\s*\)",
    }
    relations = {
        name: set(re.findall(pattern, extraction_text + "\n" + grouping_text))
        for name, pattern in relation_patterns.items()
    }
    backgrounds = set(re.findall(r"background\(\s*(\w+)\s*\)", grouping_text))
    return {
        "regions": regions,
        "visualGroups": visual_groups,
        "symbolicGroups": symbolic_groups,
        "relations": relations,
        "background": backgrounds,
        "geometry": geometry or {},
    }


def _color_multiset(members: Iterable[str], regions: dict[str, dict[str, Any]]) -> Counter[str]:
    return Counter(regions[member]["color"] for member in members)


def _color_mass(members: Iterable[str], regions: dict[str, dict[str, Any]]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    total = 0.0
    for member in members:
        area = max(0.0, float(regions[member]["area"]))
        totals[str(regions[member]["color"])] += area
        total += area
    return {color: area / total for color, area in totals.items()} if total else {}


def _color_mass_error(
    left: Iterable[str],
    right: Iterable[str],
    regions: dict[str, dict[str, Any]],
) -> float:
    a = _color_mass(left, regions)
    b = _color_mass(right, regions)
    return 0.5 * sum(abs(a.get(color, 0.0) - b.get(color, 0.0)) for color in set(a) | set(b))


def _topology_signature(
    members: Iterable[str],
    index_of: dict[str, int],
    relations: dict[str, set[tuple[str, str]]],
) -> tuple[tuple[Any, ...], ...]:
    member_set = set(members)
    signature: set[tuple[Any, ...]] = set()
    for relation in ("adjacent", "shared_edge"):
        for left, right in relations.get(relation, set()):
            if left not in member_set or right not in member_set:
                continue
            a, b = sorted((index_of[left], index_of[right]))
            signature.add((relation, a, b))
    for relation in ("encloses", "cutout"):
        for left, right in relations.get(relation, set()):
            if left in member_set and right in member_set:
                signature.add((relation, index_of[left], index_of[right]))
    return tuple(sorted(signature))


def _correspondences(
    template_members: tuple[str, ...],
    candidate_members: tuple[str, ...],
    regions: dict[str, dict[str, Any]],
) -> Iterator[dict[str, int]]:
    if _color_multiset(template_members, regions) != _color_multiset(candidate_members, regions):
        return
    template_by_color: defaultdict[str, list[str]] = defaultdict(list)
    candidate_by_color: defaultdict[str, list[str]] = defaultdict(list)
    for member in template_members:
        template_by_color[str(regions[member]["color"])].append(member)
    for member in candidate_members:
        candidate_by_color[str(regions[member]["color"])].append(member)
    colors = sorted(template_by_color)
    choices = [
        tuple(islice(
            permutations(sorted(candidate_by_color[color], key=_natural_key)),
            MAX_COLOR_CORRESPONDENCES,
        ))
        for color in colors
    ]
    template_index = {member: index for index, member in enumerate(template_members)}
    for selected in islice(product(*choices), MAX_COLOR_CORRESPONDENCES):
        mapping: dict[str, int] = {}
        for color, candidates in zip(colors, selected):
            templates = sorted(template_by_color[color], key=lambda member: template_index[member])
            for template_member, candidate_member in zip(templates, candidates):
                mapping[candidate_member] = template_index[template_member]
        yield mapping


def _radial_signature(member: str, regions: dict[str, dict[str, Any]], geometry: dict[str, Any]) -> list[float]:
    details = (geometry.get("polygons") or {}).get(member.removeprefix("r"))
    if details is None:
        details = (geometry.get("polygons") or {}).get(member)
    outer = (details or {}).get("outer") or []
    if not outer:
        return [0.0] * 5
    cx, cy = regions[member]["centroid"]
    scale = math.sqrt(max(float(regions[member]["area"]), 1.0))
    radii = sorted(math.hypot(float(point[0]) - cx, float(point[1]) - cy) / scale for point in outer)
    return [radii[round((len(radii) - 1) * fraction)] for fraction in (0.0, 0.25, 0.5, 0.75, 1.0)]


def _normalized_members(
    members: tuple[str, ...],
    regions: dict[str, dict[str, Any]],
    geometry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    total_area = sum(max(float(regions[member]["area"]), 0.0) for member in members)
    if total_area <= 0:
        total_area = 1.0
    center_x = sum(float(regions[member]["centroid"][0]) * float(regions[member]["area"]) for member in members) / total_area
    center_y = sum(float(regions[member]["centroid"][1]) * float(regions[member]["area"]) for member in members) / total_area
    scale = math.sqrt(total_area)
    return {
        member: {
            "x": (float(regions[member]["centroid"][0]) - center_x) / scale,
            "y": (float(regions[member]["centroid"][1]) - center_y) / scale,
            "area": float(regions[member]["area"]) / total_area,
            "radial": _radial_signature(member, regions, geometry),
        }
        for member in members
    }


def _geometry_measures(
    template_members: tuple[str, ...],
    candidate_members: tuple[str, ...],
    mapping: dict[str, int],
    regions: dict[str, dict[str, Any]],
    geometry: dict[str, Any],
) -> dict[str, float]:
    template_features = _normalized_members(template_members, regions, geometry)
    candidate_features = _normalized_members(candidate_members, regions, geometry)
    candidate_for_index = {index: member for member, index in mapping.items()}
    position_errors: list[float] = []
    area_errors: list[float] = []
    radial_errors: list[float] = []
    pair_distance_errors: list[float] = []
    angle_errors: list[float] = []
    for index, template_member in enumerate(template_members):
        candidate_member = candidate_for_index[index]
        template = template_features[template_member]
        candidate = candidate_features[candidate_member]
        position_errors.append((template["x"] - candidate["x"]) ** 2 + (template["y"] - candidate["y"]) ** 2)
        area_errors.append((template["area"] - candidate["area"]) ** 2)
        radial_errors.extend((left - right) ** 2 for left, right in zip(template["radial"], candidate["radial"]))
    for left in range(len(template_members)):
        for right in range(left + 1, len(template_members)):
            ta = template_features[template_members[left]]
            tb = template_features[template_members[right]]
            ca = candidate_features[candidate_for_index[left]]
            cb = candidate_features[candidate_for_index[right]]
            template_dx, template_dy = tb["x"] - ta["x"], tb["y"] - ta["y"]
            candidate_dx, candidate_dy = cb["x"] - ca["x"], cb["y"] - ca["y"]
            pair_distance_errors.append(
                (math.hypot(template_dx, template_dy) - math.hypot(candidate_dx, candidate_dy)) ** 2
            )
            angle_delta = abs(math.atan2(template_dy, template_dx) - math.atan2(candidate_dy, candidate_dx))
            angle_delta = min(angle_delta, 2 * math.pi - angle_delta) / math.pi
            angle_errors.append(angle_delta**2)

    def rmse(values: list[float]) -> float:
        return math.sqrt(sum(values) / len(values)) if values else 0.0

    measures = {
        "positionRmse": rmse(position_errors),
        "areaRmse": rmse(area_errors),
        "pairDistanceRmse": rmse(pair_distance_errors),
        "angleRmse": rmse(angle_errors),
        "radialRmse": rmse(radial_errors),
    }
    measures["error"] = (
        0.4 * measures["positionRmse"]
        + 0.2 * measures["areaRmse"]
        + 0.2 * measures["pairDistanceRmse"]
        + 0.1 * measures["angleRmse"]
        + 0.1 * measures["radialRmse"]
    )
    return measures


def _symbolic_comparison(
    candidate: dict[str, Any],
    template: dict[str, Any],
    regions: dict[str, dict[str, Any]],
    relations: dict[str, set[tuple[str, str]]],
    geometry: dict[str, Any],
) -> dict[str, Any]:
    candidate_members = tuple(candidate["members"])
    template_members = tuple(template["members"])
    color_match = _color_multiset(candidate_members, regions) == _color_multiset(template_members, regions)
    if not color_match:
        return {
            "template": template,
            "colorMatch": False,
            "topologyMatch": False,
            "measures": {"error": float("inf")},
            "correspondence": [],
            "score": 0.0,
        }
    template_index = {member: index for index, member in enumerate(template_members)}
    template_topology = _topology_signature(template_members, template_index, relations)
    matches: list[dict[str, Any]] = []
    for mapping in _correspondences(template_members, candidate_members, regions):
        topology_match = _topology_signature(candidate_members, mapping, relations) == template_topology
        measures = _geometry_measures(template_members, candidate_members, mapping, regions, geometry)
        correspondence = [
            {
                "template": template_member,
                "candidate": next(member for member, mapped_index in mapping.items() if mapped_index == index),
            }
            for index, template_member in enumerate(template_members)
        ]
        matches.append({
            "template": template,
            "measures": measures,
            "correspondence": correspondence,
            "score": 1.0 / (1.0 + measures["error"]),
            "colorMatch": True,
            "topologyMatch": topology_match,
        })
    if not matches:
        return {
            "template": template,
            "colorMatch": True,
            "topologyMatch": False,
            "measures": {"error": float("inf")},
            "correspondence": [],
            "score": 0.0,
        }
    matches.sort(key=lambda match: (
        not match["topologyMatch"],
        match["measures"]["error"],
        _natural_key(str(template["id"])),
        tuple(pair["candidate"] for pair in match["correspondence"]),
    ))
    return matches[0]


def _member_polygon(member: str, geometry: dict[str, Any]) -> dict[str, Any]:
    polygons = geometry.get("polygons") or {}
    return polygons.get(member.removeprefix("r")) or polygons.get(member) or {}


def _canonical_group_mask(members: Iterable[str], geometry: dict[str, Any]) -> np.ndarray | None:
    width = int(geometry.get("width") or 0)
    height = int(geometry.get("height") or 0)
    if width <= 0 or height <= 0:
        return None
    union = np.zeros((height, width), dtype=bool)
    for member in members:
        polygon = _member_polygon(member, geometry)
        outer = polygon.get("outer") or []
        if len(outer) < 3:
            continue
        layer = Image.new("1", (width, height), 0)
        draw = ImageDraw.Draw(layer)
        draw.polygon([(float(point[0]), float(point[1])) for point in outer], fill=1)
        for hole in polygon.get("holes") or []:
            if len(hole) >= 3:
                draw.polygon([(float(point[0]), float(point[1])) for point in hole], fill=0)
        union |= np.asarray(layer, dtype=bool)
    ys, xs = np.nonzero(union)
    if len(xs) == 0:
        return None
    center_x, center_y = float(xs.mean()), float(ys.mean())
    scale = math.sqrt(float(len(xs)))
    canonical = np.zeros((CANONICAL_MASK_SIZE, CANONICAL_MASK_SIZE), dtype=bool)
    factor = CANONICAL_MASK_SIZE / 4.0
    gx = np.rint(CANONICAL_MASK_SIZE / 2 + (xs - center_x) / scale * factor).astype(int)
    gy = np.rint(CANONICAL_MASK_SIZE / 2 + (ys - center_y) / scale * factor).astype(int)
    valid = (gx >= 0) & (gx < CANONICAL_MASK_SIZE) & (gy >= 0) & (gy < CANONICAL_MASK_SIZE)
    canonical[gy[valid], gx[valid]] = True
    try:
        from scipy import ndimage  # noqa: PLC0415

        canonical = ndimage.binary_dilation(canonical, iterations=1)
    except ImportError:  # pragma: no cover - scipy is a project dependency
        pass
    return canonical


def _mask_similarity(left: np.ndarray | None, right: np.ndarray | None) -> float:
    if left is None or right is None:
        return 0.0
    union = np.count_nonzero(left | right)
    return float(np.count_nonzero(left & right) / union) if union else 0.0


def prepare_current_frame_group_evidence(
    evidence: dict[str, Any],
    *,
    frame_id: str = "frame",
    symbolic_tolerance: float = SYMBOLIC_GEOMETRY_TOLERANCE,
    pixel_threshold: float = PIXEL_SHAPE_FALLBACK_THRESHOLD,
    pixel_unique_margin: float = PIXEL_SHAPE_UNIQUE_MARGIN,
    pixel_color_tolerance: float = PIXEL_COLOR_MASS_TOLERANCE,
) -> dict[str, Any]:
    regions: dict[str, dict[str, Any]] = evidence["regions"]
    region_order = {
        region_id: int(region.get("sourceOrder", index))
        for index, (region_id, region) in enumerate(regions.items())
    }
    visual_groups = [
        {**group, "members": _canonical_members(group["members"], region_order)}
        for group in evidence.get("visualGroups", [])
    ]
    symbolic_groups = [
        {**group, "members": _canonical_members(group["members"], region_order)}
        for group in evidence.get("symbolicGroups", [])
    ]
    backgrounds = set(evidence.get("background", set()))
    foreground = _canonical_members((region for region in regions if region not in backgrounds), region_order)
    relations = evidence.get("relations") or {}
    geometry = evidence.get("geometry") or {}
    visual_by_members: defaultdict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    symbolic_by_members: defaultdict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for group in visual_groups:
        visual_by_members[group["members"]].append(group)
    for group in symbolic_groups:
        symbolic_by_members[group["members"]].append(group)

    exact_keys = sorted(
        set(visual_by_members) & set(symbolic_by_members),
        key=lambda members: (
            min(group["sourceOrder"] for group in symbolic_by_members[members]),
            tuple(region_order.get(member, 2**31) for member in members),
        ),
    )
    exact_symbolic_ids: set[str] = set()
    template_candidates: list[dict[str, Any]] = []
    for template_order, members in enumerate(exact_keys, start=1):
        visual_sources = sorted(visual_by_members[members], key=lambda group: group["sourceOrder"])
        symbolic_sources = sorted(symbolic_by_members[members], key=lambda group: group["sourceOrder"])
        provenance = {
            "mode": "exact_consensus",
            "frame": frame_id,
            "visualGroups": [group["id"] for group in visual_sources],
            "symbolicGroups": [group["id"] for group in symbolic_sources],
            "visualEvidence": [group.get("evidence", {}) for group in visual_sources],
            "symbolicEvidence": [
                {
                    "id": group["id"],
                    "sourceId": group.get("sourceId"),
                    "area": group.get("area"),
                }
                for group in symbolic_sources
            ],
            "score": 1.0,
        }
        exact_symbolic_ids.update(group["id"] for group in symbolic_sources)
        template_candidates.append({
            "id": f"t{template_order}",
            "order": template_order,
            "members": list(members),
            "visualGroups": provenance["visualGroups"],
            "symbolicGroups": provenance["symbolicGroups"],
            "evidence": provenance,
        })

    template_masks = {
        template["id"]: _canonical_group_mask(template["members"], geometry)
        for template in template_candidates
    }
    candidate_measurements: list[dict[str, Any]] = []
    for symbolic in sorted(symbolic_groups, key=lambda group: (group["sourceOrder"], _natural_key(group["id"]))):
        if symbolic["id"] in exact_symbolic_ids:
            continue
        symbolic_measurements = []
        pixel_measurements = []
        candidate_mask = _canonical_group_mask(symbolic["members"], geometry)
        for template in template_candidates:
            comparison = _symbolic_comparison(
                symbolic,
                template,
                regions,
                relations,
                geometry,
            )
            symbolic_measurements.append({
                "template": template["id"],
                "templateOrder": template["order"],
                "colorMatch": comparison["colorMatch"],
                "topologyMatch": comparison["topologyMatch"],
                "score": comparison["score"],
                "geometryError": comparison["measures"]["error"],
                "measures": comparison["measures"],
                "correspondence": comparison["correspondence"],
                "evidence": {
                    "mode": "symbolic_shape_analogy",
                    "frame": frame_id,
                    "symbolicGroup": symbolic["id"],
                    "templateKey": template["id"],
                    "templateVisualGroups": template["visualGroups"],
                    "templateSymbolicGroups": template["symbolicGroups"],
                    "score": comparison["score"],
                    "measures": comparison["measures"],
                    "tolerance": symbolic_tolerance,
                    "correspondence": comparison["correspondence"],
                    "attempts": ["symbolic_shape_analogy"],
                },
            })
            color_error = _color_mass_error(symbolic["members"], template["members"], regions)
            pixel_score = _mask_similarity(
                candidate_mask,
                template_masks[template["id"]],
            )
            pixel_measurements.append({
                "template": template["id"],
                "templateOrder": template["order"],
                "score": pixel_score,
                "colorMassError": color_error,
                "evidence": {
                    "mode": "pixel_shape_fallback",
                    "frame": frame_id,
                    "symbolicGroup": symbolic["id"],
                    "templateKey": template["id"],
                    "templateVisualGroups": template["visualGroups"],
                    "templateSymbolicGroups": template["symbolicGroups"],
                    "score": pixel_score,
                    "threshold": pixel_threshold,
                    "uniqueMargin": pixel_unique_margin,
                    "colorMassError": color_error,
                    "colorMassTolerance": pixel_color_tolerance,
                    "attempts": ["symbolic_shape_analogy", "pixel_shape_fallback"],
                },
            })
        candidate_measurements.append({
            "id": symbolic["id"],
            "order": int(symbolic["sourceOrder"]),
            "members": list(symbolic["members"]),
            "evidence": {
                "frame": frame_id,
                "symbolicGroup": symbolic["id"],
                "members": list(symbolic["members"]),
            },
            "symbolicMeasurements": symbolic_measurements,
            "pixelMeasurements": pixel_measurements,
        })

    return {
        "frame": frame_id,
        "foreground": list(foreground),
        "background": sorted(backgrounds, key=_natural_key),
        "templateCandidates": template_candidates,
        "symbolicCandidates": candidate_measurements,
        "singletonEvidence": {
            region_id: {
                "mode": "singleton_remainder",
                "frame": frame_id,
                "region": region_id,
                "reason": "uncovered_foreground",
                "score": 1.0,
            }
            for region_id in foreground
        },
        "parameters": {
            "symbolicGeometryTolerance": symbolic_tolerance,
            "pixelShapeThreshold": pixel_threshold,
            "pixelUniqueMargin": pixel_unique_margin,
            "pixelColorMassTolerance": pixel_color_tolerance,
        },
    }


def _evidence_atom(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return f"'{encoded}'"


def render_group_acceptance_input(prepared: dict[str, Any]) -> str:
    lines = [
        "% deterministic measurements for Prolog-owned final group acceptance",
    ]
    parameters = prepared["parameters"]
    for name, value in (
        ("symbolic_geometry_tolerance", parameters["symbolicGeometryTolerance"]),
        ("pixel_shape_threshold", parameters["pixelShapeThreshold"]),
        ("pixel_unique_margin", parameters["pixelUniqueMargin"]),
        ("pixel_color_mass_tolerance", parameters["pixelColorMassTolerance"]),
    ):
        lines.append(f"acceptance_parameter({name}, {float(value):.9f}).")
    for order, region_id in enumerate(prepared["foreground"]):
        lines.append(f"foreground_region({order}, {region_id}, {_evidence_atom(prepared['singletonEvidence'][region_id])}).")
    for region_id in prepared["background"]:
        lines.append(f"background_region({region_id}).")
    for template in prepared["templateCandidates"]:
        lines.append(
            f"exact_template_candidate({template['order']}, {template['id']}, "
            f"[{','.join(template['members'])}], "
            f"[{','.join(template['visualGroups'])}], "
            f"[{','.join(template['symbolicGroups'])}], "
            f"{_evidence_atom(template['evidence'])})."
        )
    for candidate in prepared["symbolicCandidates"]:
        lines.append(
            f"symbolic_candidate({candidate['order']}, {candidate['id']}, "
            f"[{','.join(candidate['members'])}], {_evidence_atom(candidate['evidence'])})."
        )
        for measurement in candidate["symbolicMeasurements"]:
            error = measurement["geometryError"]
            finite_error = float(error) if math.isfinite(float(error)) else 1.0e9
            lines.append(
                f"symbolic_shape_measure({candidate['id']}, {measurement['template']}, "
                f"{str(bool(measurement['colorMatch'])).lower()}, "
                f"{str(bool(measurement['topologyMatch'])).lower()}, "
                f"{finite_error:.9f}, {float(measurement['score']):.9f}, "
                f"{_evidence_atom(measurement['evidence'])})."
            )
        for measurement in candidate["pixelMeasurements"]:
            lines.append(
                f"pixel_shape_measure({candidate['id']}, {measurement['template']}, "
                f"{float(measurement['score']):.9f}, "
                f"{float(measurement['colorMassError']):.9f}, "
                f"{_evidence_atom(measurement['evidence'])})."
            )
    return "\n".join(lines) + "\n"


def _decode_evidence_atom(value: str) -> dict[str, Any]:
    decoded = base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
    return json.loads(decoded)


def parse_group_acceptance_result(
    text: str,
    prepared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    members_by_group = {
        group_id: [member.strip() for member in members.split(",") if member.strip()]
        for group_id, members in re.findall(r"accepted_group\((g\d+),\s*\[([^\]]*)\]\)", text)
    }
    evidence_by_group = {
        group_id: _decode_evidence_atom(encoded)
        for group_id, encoded in re.findall(
            r"group_acceptance_evidence\((g\d+),\s*'?([A-Za-z0-9_=-]+)'?\)",
            text,
        )
    }
    modes: dict[str, tuple[str, dict[str, Any]]] = {}
    for group_id, visual, symbolic in re.findall(
        r"group_acceptance\((g\d+),\s*exact_consensus\(\[([^\]]*)\],\[([^\]]*)\]\),\s*score\(",
        text,
    ):
        modes[group_id] = ("exact_consensus", {
            "visualGroups": [item.strip() for item in visual.split(",") if item.strip()],
            "symbolicGroups": [item.strip() for item in symbolic.split(",") if item.strip()],
        })
    for group_id, mode, symbolic_group, template_group in re.findall(
        r"group_acceptance\((g\d+),\s*(symbolic_shape_analogy|pixel_shape_fallback)"
        r"\((w\d+),(g\d+)\),\s*score\(",
        text,
    ):
        modes[group_id] = (mode, {
            "symbolicGroup": symbolic_group,
            "templateGroup": template_group,
        })
    for group_id, region_id in re.findall(
        r"group_acceptance\((g\d+),\s*singleton_remainder\((\w+)\),\s*score\(",
        text,
    ):
        modes[group_id] = ("singleton_remainder", {"region": region_id})
    accepted_groups = []
    for group_id in sorted(members_by_group, key=_natural_key):
        provenance = evidence_by_group.get(group_id, {})
        mode, mode_evidence = modes.get(group_id, ("", {}))
        provenance.update(mode_evidence)
        accepted_groups.append({
            "id": group_id,
            "members": members_by_group[group_id],
            "mode": mode or str(provenance.get("mode") or ""),
            "provenance": provenance,
        })
    rejected = [
        {
            "id": group_id,
            "reason": reason,
            "attempts": ["symbolic_shape_analogy", "pixel_shape_fallback"],
        }
        for group_id, reason in re.findall(r"group_rejection\((w\d+),\s*(\w+)\)", text)
    ]
    rejected_templates = [
        {
            "id": template_id,
            "reason": reason,
            "evidence": _decode_evidence_atom(encoded),
        }
        for template_id, reason, encoded in re.findall(
            r"template_rejection\((t\d+),\s*(\w+),\s*'?([A-Za-z0-9_=-]+)'?\)",
            text,
        )
    ]
    if prepared:
        candidates = {
            candidate["id"]: candidate
            for candidate in prepared.get("symbolicCandidates", [])
        }
        for rejection in rejected:
            candidate = candidates.get(rejection["id"], {})
            rejection["members"] = list(candidate.get("members") or [])
            rejection["evidence"] = candidate.get("evidence") or {}
    return {
        "acceptedGroups": accepted_groups,
        "rejectedSymbolicGroups": rejected,
        "rejectedTemplateCandidates": rejected_templates,
    }
