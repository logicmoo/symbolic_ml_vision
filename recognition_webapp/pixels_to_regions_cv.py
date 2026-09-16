"""Recognition extraction from logicmoo/omega_vision, LGPL-2.1-or-later.
Source: python/omega_vision/perception/pixels_to_regions_cv.py
Source SHA-256: e9b8b995a62e0da61e2d65034fcd0db749a6440d00d12958f91c9daa89ab99fd
Standalone adapter changes are described in README.md.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from pixels_to_regions import (_neighbors8, _prune_spurs, _simplify_no_cutout, add_enclosed_parts, adjacency, enhance, gradient_blobs, label_map, perimeters, quantize, to_prolog)


def _require_cv2():
    try:
        import cv2  # noqa: PLC0415
    except ImportError as error:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "python_opencv doer needs opencv (pip install opencv-contrib-python-headless)"
        ) from error
    return cv2


def _region_boxes(labels: np.ndarray, big: set) -> dict[int, tuple[int, int, int, int]]:
    """(y0, y1, x0, x1) inclusive bounding box per kept region, one pass."""
    from scipy import ndimage  # noqa: PLC0415

    boxes: dict[int, tuple[int, int, int, int]] = {}
    for gid, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None or gid not in big:
            continue
        boxes[gid] = (sl[0].start, sl[0].stop - 1, sl[1].start, sl[1].stop - 1)
    return boxes


def _ring(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Close the ring like the scikit contours do (first point repeated last)."""
    if points and points[0] != points[-1]:
        return points + [points[0]]
    return points


def region_polygons_cv(labels: np.ndarray, big: set,
                       boxes: dict[int, tuple[int, int, int, int]],
                       tolerance: float = 1.5,
                       preserve_exact: set[int] | None = None) -> dict[int, dict]:
    """OUTER EDGE + INNER EDGES per part via cv2.findContours on the cropped
    mask: the largest external contour is the silhouette, every hierarchy
    child is an inner edge (hole)."""
    cv2 = _require_cv2()
    polygons: dict[int, dict] = {}
    for gid in big:
        box = boxes.get(gid)
        if box is None:
            continue
        y0, y1, x0, x1 = box
        mask = (labels[y0:y1 + 1, x0:x1 + 1] == gid).astype(np.uint8)
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if not contours or hierarchy is None:
            continue
        hierarchy = hierarchy[0]

        def simplify(contour) -> list[tuple[int, int]]:
            epsilon = 0.0 if preserve_exact and gid in preserve_exact else tolerance
            approx = cv2.approxPolyDP(contour, epsilon, True)
            return [(int(p[0][0]) + x0, int(p[0][1]) + y0) for p in approx]

        externals = [i for i, h in enumerate(hierarchy) if h[3] < 0]
        if not externals:
            continue
        outer_index = max(externals, key=lambda i: cv2.contourArea(contours[i]))
        outer = _ring(simplify(contours[outer_index]))
        if len(outer) < 3:
            continue
        outer_contour = contours[outer_index]
        contour_area = abs(float(cv2.contourArea(outer_contour)))
        contour_perimeter = float(cv2.arcLength(outer_contour, True))
        hull_area = abs(float(cv2.contourArea(cv2.convexHull(outer_contour))))
        _bx, _by, box_width, box_height = cv2.boundingRect(outer_contour)
        padded = np.pad(mask, 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        opening = cv2.morphologyEx(padded, cv2.MORPH_OPEN, kernel)
        closing = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, kernel)
        gradient = cv2.morphologyEx(padded, cv2.MORPH_GRADIENT, kernel)
        morphology = {
            "openingArea": int(np.count_nonzero(opening)),
            "closingArea": int(np.count_nonzero(closing)),
            "gradientArea": int(np.count_nonzero(gradient)),
        }
        shape_metrics = {
            "contourArea": round(contour_area, 4),
            "hullArea": round(hull_area, 4),
            "solidity": round(contour_area / hull_area, 6) if hull_area else 0.0,
            "circularity": round(
                4.0 * np.pi * contour_area / (contour_perimeter * contour_perimeter),
                6,
            ) if contour_perimeter else 0.0,
            "extent": round(
                contour_area / float(box_width * box_height),
                6,
            ) if box_width and box_height else 0.0,
            "aspectRatio": round(
                float(box_width) / float(box_height),
                6,
            ) if box_height else 0.0,
        }
        holes: list[list[tuple[int, int]]] = []
        for i, h in enumerate(hierarchy):
            ring = None
            if h[3] >= 0:
                ring = _ring(simplify(contours[i]))  # true inner edge
            elif i != outer_index:
                ring = _ring(simplify(contours[i]))  # disjoint island, kept like scikit
            if ring and len(ring) >= 3:
                holes.append(ring)
        contour_hierarchy = [
            {
                "index": i,
                "kind": "hole" if int(h[3]) >= 0 else "outer",
                "next": int(h[0]),
                "previous": int(h[1]),
                "child": int(h[2]),
                "parent": int(h[3]),
                "area": round(abs(float(cv2.contourArea(contours[i]))), 4),
            }
            for i, h in enumerate(hierarchy)
        ]
        polygons[gid] = {
            "outer": outer,
            "holes": holes,
            "contours": contour_hierarchy,
            "morphology": morphology,
            "shapeMetrics": shape_metrics,
        }
    return polygons


def _skeleton_points(mask: np.ndarray) -> tuple[set, np.ndarray]:
    """Skeleton pixel set + distance-to-edge map for one padded crop mask.
    cv2.ximgproc.thinning when the contrib build is present, else the
    scikit medial axis (still fast: the mask is bbox-cropped)."""
    cv2 = _require_cv2()
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    thinning = getattr(getattr(cv2, "ximgproc", None), "thinning", None)
    if thinning is not None:
        skeleton = thinning(mask.astype(np.uint8) * 255) > 0
    else:  # pragma: no cover - depends on the installed opencv flavor
        from skimage.morphology import medial_axis  # noqa: PLC0415
        skeleton, dist = medial_axis(mask, return_distance=True)
    ys, xs = np.nonzero(skeleton)
    return {(int(x), int(y)) for x, y in zip(xs, ys)}, dist


def _walk_paths(points: set, dist: np.ndarray) -> list[list[tuple[int, int]]]:
    """Order skeleton pixels into polylines (endpoints first, then loops)."""
    remaining = set(points)
    paths: list[list[tuple[int, int]]] = []
    while remaining:
        endpoints = [p for p in remaining if len(_neighbors8(p, remaining)) <= 1]
        current = endpoints[0] if endpoints else next(iter(remaining))
        path = [current]
        remaining.discard(current)
        while True:
            options = _neighbors8(current, remaining)
            if not options:
                break
            current = options[0]
            path.append(current)
            remaining.discard(current)
        if len(path) >= 2:
            paths.append(path)
    if not paths and points:
        best = max(points, key=lambda p: dist[p[1], p[0]])
        return [[best]]
    return paths


def region_midlines_cv(labels: np.ndarray, big: set,
                       boxes: dict[int, tuple[int, int, int, int]],
                       tolerance: float = 1.5) -> dict[int, list[list[tuple[int, int]]]]:
    """INNER MEDIALS per part: thinning skeleton -> crest pruning -> ordered
    polylines, simplified without ever crossing a cutout (same guarantees as
    the scikit doer)."""
    midlines: dict[int, list[list[tuple[int, int]]]] = {}
    for gid in big:
        box = boxes.get(gid)
        if box is None:
            continue
        y0, y1, x0, x1 = box
        sub = labels[y0:y1 + 1, x0:x1 + 1] == gid
        padded = np.pad(sub, 1)
        points, dist = _skeleton_points(padded)
        if not points:
            continue
        points = _prune_spurs(points, dist)
        if not points:
            peak = int(np.argmax(dist))
            py, px = np.unravel_index(peak, dist.shape)
            midlines[gid] = [[(int(px) - 1 + x0, int(py) - 1 + y0)]]
            continue

        def inside(x: int, y: int) -> bool:
            return 0 <= y - y0 <= y1 - y0 and 0 <= x - x0 <= x1 - x0 and bool(sub[y - y0, x - x0])

        simplified: list[list[tuple[int, int]]] = []
        raw_paths = _walk_paths(points, dist)
        for path in raw_paths:
            full = [(x - 1 + x0, y - 1 + y0) for x, y in path]
            pts = [(int(x), int(y)) for x, y in _simplify_no_cutout(full, inside, tolerance)]
            if len(pts) >= 2:
                simplified.append(pts)
        if not simplified and raw_paths:
            x, y = raw_paths[0][0]
            simplified = [[(x - 1 + x0, y - 1 + y0)]]
        if simplified:
            midlines[gid] = simplified
    return midlines


def region_fillpoints_cv(labels: np.ndarray, big: set,
                         boxes: dict[int, tuple[int, int, int, int]]) -> dict[int, list[tuple[int, int, float]]]:
    """Fill peaks per part from the cv2 distance transform (deepest first)."""
    cv2 = _require_cv2()
    from scipy import ndimage  # noqa: PLC0415

    fillpoints: dict[int, list[tuple[int, int, float]]] = {}
    for gid in big:
        box = boxes.get(gid)
        if box is None:
            continue
        y0, y1, x0, x1 = box
        mask = np.pad(labels[y0:y1 + 1, x0:x1 + 1] == gid, 1)
        dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
        peak = float(dist.max())
        if peak <= 0:
            continue
        local_max = (dist == ndimage.maximum_filter(dist, size=3)) & mask
        floor = max(1.0, 0.25 * peak)
        plateaus, count = ndimage.label(local_max & (dist >= floor))
        points: list[tuple[int, int, float]] = []
        for index in range(1, count + 1):
            ys, xs = np.nonzero(plateaus == index)
            mid = len(ys) // 2
            py, px = int(ys[mid]), int(xs[mid])
            points.append((px - 1 + x0, py - 1 + y0, round(float(dist[py, px]), 1)))
        points.sort(key=lambda p: -p[2])
        if points:
            fillpoints[gid] = points
    return fillpoints


def exterior_background_candidates(
    info: dict[int, dict],
    kept: set[int],
    width: int,
    height: int,
) -> set[int]:
    """Mirror group_regions.pl exterior_background/1 for OpenCV evidence."""
    min_area = 0.10 * width * height
    return {
        gid
        for gid in kept
        if info[gid].get("border") and info[gid]["area"] >= min_area
    }


def _hex_rgb(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.array(
        [int(value[index:index + 2], 16) for index in (0, 2, 4)],
        dtype=np.int16,
    )


def _pixel_runs(labels: np.ndarray, gid: int) -> list[list[int]]:
    runs: list[list[int]] = []
    ys = np.flatnonzero(np.any(labels == gid, axis=1))
    for y in ys:
        xs = np.flatnonzero(labels[y] == gid)
        if not xs.size:
            continue
        start = previous = int(xs[0])
        for value in xs[1:]:
            x = int(value)
            if x != previous + 1:
                runs.append([int(y), start, previous])
                start = x
            previous = x
        runs.append([int(y), start, previous])
    return runs


def small_contrast_features_cv(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    info: dict[int, dict],
    pairs: dict[tuple[int, int], int],
    kept: set[int],
    perims: dict[int, int],
    *,
    floor: int = 16,
    min_contrast: int = 48,
    min_host_area_ratio: float = 4.0,
    min_host_contact_ratio: float = 0.25,
    min_surround_contact_ratio: float = 0.75,
    min_bbox_fill: float = 0.2,
    min_thickness: float = 1.5,
    max_color_std: float = 24.0,
) -> dict[int, dict]:
    """Recover coherent raw components that carry strong embedded mark evidence.

    The ordinary area floor remains the noise gate. This exception is limited
    to non-border components with a substantially larger non-background host,
    strong shared-edge support, high contrast against every immediate neighbor,
    compact/thick raw pixels, and nearly complete contact with kept structure.
    No morphology changes the component; it is used only as stability evidence.
    """
    cv2 = _require_cv2()
    height, width = labels.shape
    backgrounds = exterior_background_candidates(info, kept, width, height)
    contacts: dict[int, dict[int, int]] = {}
    for (left, right), shared in pairs.items():
        contacts.setdefault(left, {})[right] = int(shared)
        contacts.setdefault(right, {})[left] = int(shared)

    recovered: dict[int, dict] = {}
    for gid in sorted(set(info) - kept):
        details = info[gid]
        area = int(details["area"])
        if area < max(4, int(floor)) or details.get("border"):
            continue
        neighbors = contacts.get(gid, {})
        eligible_hosts = [
            neighbor
            for neighbor in neighbors
            if neighbor in kept
            and neighbor not in backgrounds
            and int(info[neighbor]["area"]) >= min_host_area_ratio * area
        ]
        if not eligible_hosts:
            continue
        host = max(
            eligible_hosts,
            key=lambda neighbor: (
                neighbors[neighbor],
                int(info[neighbor]["area"]),
                -neighbor,
            ),
        )
        perimeter = max(1, int(perims.get(gid, 0)))
        host_contact = int(neighbors[host])
        surround_contact = sum(
            shared for neighbor, shared in neighbors.items() if neighbor in kept
        )
        host_ratio = host_contact / perimeter
        surround_ratio = surround_contact / perimeter
        if (
            host_ratio < min_host_contact_ratio
            or surround_ratio < min_surround_contact_ratio
        ):
            continue

        neighbor_contrasts = [
            int(np.abs(_hex_rgb(details["color"]) - _hex_rgb(info[neighbor]["color"])).max())
            for neighbor in neighbors
        ]
        contrast = min(neighbor_contrasts, default=0)
        if contrast < min_contrast:
            continue

        ys, xs = np.nonzero(labels == gid)
        color_std = float(image_rgb[ys, xs].astype(np.float32).std(axis=0).max())
        if color_std > max_color_std:
            continue
        box_area = int((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
        bbox_fill = area / max(1, box_area)
        if bbox_fill < min_bbox_fill:
            continue
        crop = (labels[ys.min():ys.max() + 1, xs.min():xs.max() + 1] == gid).astype(np.uint8)
        padded = np.pad(crop, 1)
        thickness = float(cv2.distanceTransform(padded, cv2.DIST_L2, 3).max())
        if thickness < min_thickness:
            continue
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        opened = cv2.morphologyEx(padded, cv2.MORPH_OPEN, kernel)
        opening_retention = int(np.count_nonzero(opened)) / area

        recovered[gid] = {
            "host": host,
            "area": area,
            "floor": int(floor),
            "sharedEdge": host_contact,
            "perimeter": perimeter,
            "hostContactRatio": round(host_ratio, 6),
            "surroundContactRatio": round(surround_ratio, 6),
            "minContrast": contrast,
            "colorStd": round(color_std, 6),
            "bboxFill": round(bbox_fill, 6),
            "thickness": round(thickness, 6),
            "openingRetention": round(opening_retention, 6),
            "pixelRuns": _pixel_runs(labels, gid),
        }
    return recovered


def foreground_components_cv(
    labels: np.ndarray,
    info: dict,
    big: set,
    width: int,
    height: int,
) -> tuple[set[int], list[dict]]:
    """Eight-connected components after removing every exterior background.

    The set mirrors the authoritative Prolog exterior rule; richer cutout
    background propagation remains Prolog-owned.
    """
    cv2 = _require_cv2()
    backgrounds = exterior_background_candidates(info, big, width, height)
    foreground = set(big) - backgrounds
    if not foreground:
        return backgrounds, []
    mask = np.isin(labels, list(foreground)).astype(np.uint8)
    count, component_labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask,
        connectivity=8,
    )
    components: list[dict] = []
    for component_id in range(1, count):
        component_mask = component_labels == component_id
        members = sorted(
            int(gid)
            for gid in np.unique(labels[component_mask])
            if int(gid) in foreground
        )
        if not members:
            continue
        components.append({
            "id": len(components) + 1,
            "members": members,
            "area": int(stats[component_id, cv2.CC_STAT_AREA]),
            "centroid": (
                int(round(float(centroids[component_id][0]))),
                int(round(float(centroids[component_id][1]))),
            ),
        })
    return backgrounds, components


def watershed_segments_cv(
    image_rgb: np.ndarray,
    labels: np.ndarray,
    regions: set,
    boxes: dict[int, tuple[int, int, int, int]],
) -> dict[int, list[dict]]:
    """Conventional distance-marker watershed segments within each region."""
    cv2 = _require_cv2()
    segments: dict[int, list[dict]] = {}
    for gid in sorted(regions):
        box = boxes.get(gid)
        if box is None:
            continue
        y0, y1, x0, x1 = box
        mask = (labels[y0:y1 + 1, x0:x1 + 1] == gid).astype(np.uint8)
        if min(mask.shape) < 3:
            ys, xs = np.nonzero(mask)
            if len(xs):
                segments[gid] = [{
                    "id": 1,
                    "area": int(len(xs)),
                    "centroid": (
                        int(round(float(xs.mean()))) + x0,
                        int(round(float(ys.mean()))) + y0,
                    ),
                }]
            continue
        distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        peak = float(distance.max())
        if peak <= 0:
            continue
        sure_foreground = (distance >= 0.45 * peak).astype(np.uint8)
        marker_count, markers = cv2.connectedComponents(sure_foreground)
        markers = markers.astype(np.int32) + 1
        unknown = cv2.subtract(mask, sure_foreground)
        markers[unknown > 0] = 0
        markers[mask == 0] = 1
        crop = cv2.cvtColor(
            image_rgb[y0:y1 + 1, x0:x1 + 1],
            cv2.COLOR_RGB2BGR,
        )
        cv2.watershed(crop, markers)
        region_segments: list[dict] = []
        for marker in range(2, marker_count + 1):
            ys, xs = np.nonzero((markers == marker) & (mask > 0))
            if len(xs) == 0:
                continue
            region_segments.append({
                "id": len(region_segments) + 1,
                "area": int(len(xs)),
                "centroid": (
                    int(round(float(xs.mean()))) + x0,
                    int(round(float(ys.mean()))) + y0,
                ),
            })
        if not region_segments:
            ys, xs = np.nonzero(mask)
            if len(xs):
                region_segments.append({
                    "id": 1,
                    "area": int(len(xs)),
                    "centroid": (
                        int(round(float(xs.mean()))) + x0,
                        int(round(float(ys.mean()))) + y0,
                    ),
                })
        if region_segments:
            segments[gid] = region_segments
    return segments


def opencv_grouping_prolog(
    backgrounds: set[int],
    components: list[dict],
    polygons: dict[int, dict],
    watershed: dict[int, list[dict]],
    visual_groups: list[dict],
    small_features: dict[int, dict] | None = None,
) -> str:
    """Render advisory OpenCV grouping evidence as queryable Prolog facts."""
    predicates = (
        "opencv_background_candidate/1",
        "opencv_component/2",
        "opencv_component_area/2",
        "opencv_component_centroid/2",
        "opencv_contour/4",
        "opencv_contour_hierarchy/6",
        "opencv_morphology/4",
        "opencv_shape_metrics/7",
        "opencv_watershed_count/2",
        "opencv_watershed_segment/4",
        "opencv_small_feature/9",
        "opencv_small_feature_pixel_run/4",
        "vision_group/4",
    )
    lines = [
        "",
        "% OpenCV grouping evidence (advisory; base topology remains authoritative).",
    ]
    for predicate in predicates:
        lines.extend((
            f":- dynamic {predicate}.",
            f":- discontiguous {predicate}.",
        ))
    for background in sorted(backgrounds):
        lines.append(f"opencv_background_candidate(r{background}).")
    for gid, evidence in sorted((small_features or {}).items()):
        lines.append(
            f"opencv_small_feature(r{gid}, host(r{evidence['host']}), "
            f"area({evidence['area']}), floor({evidence['floor']}), "
            f"shared_edge({evidence['sharedEdge']}), perimeter({evidence['perimeter']}), "
            f"min_contrast({evidence['minContrast']}), bbox_fill({evidence['bboxFill']}), "
            f"thickness({evidence['thickness']}))."
        )
        for y, x0, x1 in evidence["pixelRuns"]:
            lines.append(
                f"opencv_small_feature_pixel_run(r{gid}, {y}, {x0}, {x1})."
            )
    for component in components:
        component_id = f"cc{component['id']}"
        members = ",".join(f"r{gid}" for gid in component["members"])
        cx, cy = component["centroid"]
        lines.append(f"opencv_component({component_id}, [{members}]).")
        lines.append(f"opencv_component_area({component_id}, {component['area']}).")
        lines.append(f"opencv_component_centroid({component_id}, centroid({cx},{cy})).")
    for gid in sorted(polygons):
        region = f"r{gid}"
        details = polygons[gid]
        morphology = details.get("morphology") or {}
        lines.append(
            f"opencv_morphology({region}, "
            f"opening_area({morphology.get('openingArea', 0)}), "
            f"closing_area({morphology.get('closingArea', 0)}), "
            f"gradient_area({morphology.get('gradientArea', 0)}))."
        )
        metrics = details.get("shapeMetrics") or {}
        lines.append(
            f"opencv_shape_metrics({region}, "
            f"contour_area({metrics.get('contourArea', 0)}), "
            f"hull_area({metrics.get('hullArea', 0)}), "
            f"solidity({metrics.get('solidity', 0)}), "
            f"circularity({metrics.get('circularity', 0)}), "
            f"extent({metrics.get('extent', 0)}), "
            f"aspect_ratio({metrics.get('aspectRatio', 0)}))."
        )
        for contour in details.get("contours") or []:
            contour_id = f"c{contour['index']}"

            def contour_ref(value: int) -> str:
                return "none" if value < 0 else f"c{value}"

            lines.append(
                f"opencv_contour({region}, {contour_id}, {contour['kind']}, "
                f"{contour['area']})."
            )
            lines.append(
                f"opencv_contour_hierarchy({region}, {contour_id}, "
                f"next({contour_ref(contour['next'])}), "
                f"previous({contour_ref(contour['previous'])}), "
                f"child({contour_ref(contour['child'])}), "
                f"parent({contour_ref(contour['parent'])}))."
            )
    for gid in sorted(watershed):
        region_segments = watershed[gid]
        lines.append(f"opencv_watershed_count(r{gid}, {len(region_segments)}).")
        for segment in region_segments:
            cx, cy = segment["centroid"]
            lines.append(
                f"opencv_watershed_segment(r{gid}, ws{segment['id']}, "
                f"{segment['area']}, centroid({cx},{cy}))."
            )
    for group in visual_groups:
        members = ",".join(group["members"])
        evidence = group["evidence"]
        cx, cy = evidence["centroid"]
        lines.append(
            f"vision_group({group['id']}, {group['method']}, [{members}], "
            f"evidence(confidence({group['confidence']}), "
            f"component({evidence['component']}), "
            f"pixel_area({evidence['pixelArea']}), "
            f"centroid({cx},{cy}), "
            f"contours({evidence['contourCount']}), "
            f"hierarchy_links({evidence['hierarchyLinkCount']}), "
            f"watershed_segments({evidence['watershedSegmentCount']})))."
        )
    return "\n".join(lines) + "\n"


def visual_group_hypotheses(
    components: list[dict],
    polygons: dict[int, dict],
    watershed: dict[int, list[dict]],
) -> list[dict]:
    """Project existing OpenCV evidence into deterministic advisory vN claims."""
    groups: list[dict] = []
    ordered = sorted(components, key=lambda item: (tuple(item["members"]), item["id"]))
    for index, component in enumerate(ordered, start=1):
        members = [int(member) for member in component["members"]]
        contours = [
            contour
            for member in members
            for contour in (polygons.get(member, {}).get("contours") or [])
        ]
        groups.append({
            "id": f"v{index}",
            "method": "connected_component",
            "members": [f"r{member}" for member in members],
            "confidence": 0.75,
            "evidence": {
                "component": f"cc{component['id']}",
                "pixelArea": int(component["area"]),
                "centroid": [int(value) for value in component["centroid"]],
                "contourCount": len(contours),
                "hierarchyLinkCount": sum(
                    1
                    for contour in contours
                    if any(int(contour.get(key, -1)) >= 0 for key in ("child", "parent"))
                ),
                "watershedSegmentCount": sum(
                    len(watershed.get(member, [])) for member in members
                ),
            },
        })
    return groups


def _attachment_evidence(info, kept, polygons, fillpoints, *, opaque: bool, policy: dict) -> dict:
    """Attest producer coverage, not a consumer guess from nonempty fact lists.

    Pruned regions and dropped/degenerate contours cannot justify absence of
    attachments. Transparency is not modeled by the RGB segmentation, so it
    cannot attest trusted background roles.
    """
    regions_complete = set(info) == kept
    holes_complete = all(
        gid in polygons
        and len({tuple(point) for point in polygons[gid]["outer"]}) >= 3
        and sum(contour["kind"] == "outer" for contour in polygons[gid]["contours"]) == 1
        and len(polygons[gid]["holes"]) == len(polygons[gid]["contours"]) - 1
        for gid in kept
    )
    probes_complete = all(bool(fillpoints.get(gid)) for gid in kept)
    complete = {
        "regions": regions_complete, "shared_edges": regions_complete,
        "adjacency": regions_complete, "enclosure": regions_complete,
        "borders": regions_complete, "holes": holes_complete,
        "probes": probes_complete,
    }
    producer_files = (
        Path(__file__), Path(__file__).with_name("pixels_to_regions.py"),
        Path(__file__).with_name("group_regions.pl"),
    )
    policy = {
        "schema": "canonical-cv-attachment-coverage-v1", **policy,
        "implementations": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in producer_files
        },
    }
    return {
        "schemaVersion": 1, "complete": complete,
        "backgroundRolesTrusted": bool(opaque and all(complete.values())),
        "extractionPolicyHash": hashlib.sha256(
            json.dumps(policy, sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
    }


def extract_region_facts_cv(
    image_path: str | Path,
    *,
    tolerance: int = 24,
    filter_mode: str = "auto",
    max_dim: int = 960,
    upscale: int = 1,
    minfrac: float = 0.0008,
    small_feature_floor: int = 16,
    small_feature_contrast: int = 48,
) -> dict:
    """OpenCV twin of :func:`pixels_to_regions.extract_region_facts`: same
    segmentation, same fact schema (outer edge + inner edges + inner medials
    + fill peaks), a fraction of the runtime."""
    _require_cv2()
    img = Image.open(image_path)
    opaque = img.convert("RGBA").getextrema()[3][0] == 255
    if max_dim and max(img.size) > max_dim:
        scale = max_dim / max(img.size)
        img = img.resize((max(1, round(img.size[0] * scale)), max(1, round(img.size[1] * scale))), Image.LANCZOS)
    if upscale and upscale > 1:
        img = img.resize((img.size[0] * upscale, img.size[1] * upscale), Image.NEAREST)
    img, filter_action = enhance(img, filter_mode)
    w, h = img.size
    image_rgb = np.asarray(img.convert("RGB"))
    if tolerance > 0:
        labels, info = gradient_blobs(image_rgb, tolerance)
    else:
        idx, colors = quantize(img, 14, 0)
        labels, info = label_map(idx, colors)
    if len(info) > 4096:
        raise ValueError("Too many color blobs. Use a smaller image or a higher color tolerance.")
    min_area = max(12, int(minfrac * w * h))
    big = {gid for gid, i in info.items() if i["area"] >= min_area}
    pairs = adjacency(labels)
    exteriors = exterior_background_candidates(info, big, w, h)
    big = add_enclosed_parts(
        info,
        pairs,
        big,
        excluded_outers=exteriors,
    )
    perims = perimeters(labels)
    small_features = small_contrast_features_cv(
        image_rgb,
        labels,
        info,
        pairs,
        big,
        perims,
        floor=small_feature_floor,
        min_contrast=small_feature_contrast,
    )
    big.update(small_features)
    if len(big) > 512:
        raise ValueError("More than 512 kept regions. Use a smaller image or a higher color tolerance.")
    boxes = _region_boxes(labels, big)
    polygons = region_polygons_cv(
        labels,
        big,
        boxes,
        preserve_exact=set(small_features),
    )
    for gid, evidence in small_features.items():
        if gid in polygons:
            polygons[gid]["smallFeature"] = evidence
    midlines = region_midlines_cv(labels, big, boxes)
    fillpoints = region_fillpoints_cv(labels, big, boxes)
    backgrounds, components = foreground_components_cv(labels, info, big, w, h)
    watershed_regions = set(big) - backgrounds
    watershed = watershed_segments_cv(image_rgb, labels, watershed_regions, boxes)
    visual_groups = visual_group_hypotheses(components, polygons, watershed)
    parts = [
        {
            "id": f"r{gid}",
            "color": info[gid]["color"],
            "area": info[gid]["area"],
            "outer": len(polygons.get(gid, {}).get("outer", [])),
            "holes": len(polygons.get(gid, {}).get("holes", [])),
            "contours": len(polygons.get(gid, {}).get("contours", [])),
            "midlines": len(midlines.get(gid, [])),
            "fillpoints": len(fillpoints.get(gid, [])),
            "watershedSegments": len(watershed.get(gid, [])),
            "smallFeature": gid in small_features,
            "pixelRuns": _pixel_runs(labels, gid),
            "smallFeatureEvidence": {
                key: value
                for key, value in small_features.get(gid, {}).items()
                if key != "pixelRuns"
            },
        }
        for gid in sorted(big, key=lambda g: -info[g]["area"])
    ]
    base_prolog = to_prolog(info, pairs, big, w, h, perims, polygons, midlines, fillpoints)
    return {
        "image": img,
        "geometry": {
            "polygons": {str(g): d for g, d in polygons.items()},
            "midlines": {str(g): p for g, p in midlines.items()},
            "fillpoints": {str(g): p for g, p in fillpoints.items()},
            "components": components,
            "watershed": {str(g): p for g, p in watershed.items()},
        },
        "prolog": base_prolog + opencv_grouping_prolog(
            backgrounds,
            components,
            polygons,
            watershed,
            visual_groups,
            small_features,
        ),
        "width": w,
        "height": h,
        "regionCount": len(big),
        "adjacencyCount": sum(1 for a, b in pairs if a in big and b in big),
        "blobCount": len(info),
        "componentCount": len(components),
        "contourCount": sum(len(value.get("contours", [])) for value in polygons.values()),
        "watershedSegmentCount": sum(len(value) for value in watershed.values()),
        "visualGroupCount": len(visual_groups),
        "smallFeatureCount": len(small_features),
        "tolerance": tolerance,
        "filterAction": filter_action,
        "attachmentEvidence": _attachment_evidence(
            info, big, polygons, fillpoints, opaque=opaque,
            policy={
                "tolerance": tolerance, "filterMode": filter_mode,
                "filterAction": filter_action, "maxDim": max_dim,
                "minfrac": minfrac, "smallFeatureFloor": small_feature_floor,
                "smallFeatureContrast": small_feature_contrast,
            },
        ),
        "minArea": min_area,
        "smallFeatureFloor": small_feature_floor,
        "smallFeatureContrast": small_feature_contrast,
        "parts": parts,
        "visualGroups": visual_groups,
        "smallFeatures": [
            {"id": f"r{gid}", **evidence}
            for gid, evidence in sorted(small_features.items())
        ],
    }
