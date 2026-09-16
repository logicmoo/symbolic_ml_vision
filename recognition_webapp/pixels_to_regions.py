"""Recognition extraction from logicmoo/omega_vision, LGPL-2.1-or-later.
Source: python/omega_vision/perception/pixels_to_regions.py
Source SHA-256: 4ab2cdb27a17b3217b61bc91fff53bc66d83e3aa29047f3ab00dd1223c0cd3d4
Standalone adapter changes are described in README.md.
"""
from __future__ import annotations

from collections import defaultdict
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def _draw_parts_debug(img: Image.Image, polygons: dict[int, dict],
                      midlines: dict[int, list[list[tuple[int, int]]]],
                      fillpoints: dict[int, list[tuple[int, int, float]]]) -> Image.Image:
    """debug_image.png for the parts_map transform: faded original with green
    outer edges, red cutouts, blue median lines, orange fill peaks."""
    base = img.convert("RGB")
    out = Image.blend(base, Image.new("RGB", base.size, (255, 255, 255)), 0.55)
    draw = ImageDraw.Draw(out)
    for gid, d in polygons.items():
        outer = d["outer"]
        if outer:
            draw.line(list(outer) + [outer[0]], fill=(0, 170, 0), width=1)
        for ring in d["holes"]:
            draw.line(list(ring) + [ring[0]], fill=(230, 30, 30), width=1)
    for gid, paths in midlines.items():
        for path in paths:
            if len(path) == 1:
                x, y = path[0]
                draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(40, 90, 255))
            else:
                draw.line(path, fill=(40, 90, 255), width=1)
    for gid, points in fillpoints.items():
        for x, y, _depth in points[:3]:
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], outline=(255, 140, 0))
    return out


STRUCT4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])


def looks_flat_art(rgb_array: np.ndarray) -> bool:
    """True for cartoon / gridded / cel-flat art: a large share of 4-neighbor
    pixel pairs are (near-)identical, or the palette is tiny. Photographs and
    degraded scans fail both tests."""
    h, w = rgb_array.shape[:2]
    step = max(1, max(h, w) // 256)
    px = rgb_array[::step, ::step].astype(np.int16)
    right_flat = (np.abs(px[:, :-1] - px[:, 1:]).max(axis=2) <= 2).mean()
    down_flat = (np.abs(px[:-1, :] - px[1:, :]).max(axis=2) <= 2).mean()
    flat_fraction = (float(right_flat) + float(down_flat)) / 2.0
    packed = (px[:, :, 0].astype(np.int32) << 16) | (px[:, :, 1].astype(np.int32) << 8) | px[:, :, 2].astype(np.int32)
    unique_colors = int(np.unique(packed).size)
    return flat_fraction >= 0.55 or unique_colors <= 64


def enhance(img: Image.Image, mode: str = "auto") -> tuple[Image.Image, str]:
    """Pre-filter run before Prolog ever sees the image.

    "enhance" uses the Python vision library (PIL) for a little denoising and
    degradation repair: a 3px median filter knocks out impulse/JPEG noise and
    a gentle autocontrast (1% clip) restores washed-out levels. "auto" (the
    default) applies it only to images that are NOT cartoon or gridded items
    — flat cel art and ARC grids are already clean and would only be softened.
    Returns the image plus the action actually taken.
    """
    rgb = img.convert("RGB")
    if mode == "none":
        return rgb, "none"
    if mode == "auto" and looks_flat_art(np.asarray(rgb)):
        return rgb, "skipped (flat art/grid)"
    rgb = rgb.filter(ImageFilter.MedianFilter(size=3))
    return ImageOps.autocontrast(rgb, cutoff=1), "enhanced"


def gradient_blobs(rgb_array: np.ndarray, tolerance: int):
    """Label COLOR BLOBS that accept small color gradients: 4-adjacent pixels
    belong to the same blob when every channel differs by <= tolerance, so a
    smoothly shaded surface stays one blob but hard edges still split. Each
    blob's color is the mean RGB of its members; perimeter counts boundary
    pixel-pairs (to other blobs or the image edge) for bbox-free shape cues."""
    h, w = rgb_array.shape[:2]
    px = rgb_array.astype(np.int16)
    n = h * w
    ids = np.arange(n, dtype=np.int64).reshape(h, w)

    def joins(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.abs(a - b).max(axis=2) <= tolerance

    right = joins(px[:, :-1], px[:, 1:])
    down = joins(px[:-1, :], px[1:, :])
    rows = np.concatenate([ids[:, :-1][right], ids[:-1, :][down]])
    cols = np.concatenate([ids[:, 1:][right], ids[1:, :][down]])
    graph = coo_matrix((np.ones(rows.size, dtype=np.int8), (rows, cols)), shape=(n, n))
    _count, flat = connected_components(graph, directed=False)
    labels = (flat + 1).astype(np.int32).reshape(h, w)  # region ids start at 1

    flat0 = labels.ravel() - 1
    areas = np.bincount(flat0)
    sums = np.zeros((areas.size, 3), dtype=np.int64)
    for channel in range(3):
        sums[:, channel] = np.bincount(flat0, weights=px[:, :, channel].ravel()).astype(np.int64)
    ys, xs = np.divmod(np.arange(n), w)
    cx = np.bincount(flat0, weights=xs) / np.maximum(areas, 1)
    cy = np.bincount(flat0, weights=ys) / np.maximum(areas, 1)
    edge = np.zeros(areas.size, dtype=bool)
    for sel in (labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]):
        edge[np.unique(sel) - 1] = True

    info: dict[int, dict] = {}
    for gid0 in range(areas.size):
        area = int(areas[gid0])
        if area == 0:
            continue
        r, g, b = (sums[gid0] / area).round().astype(int)
        info[gid0 + 1] = {
            "color": f"#{r:02x}{g:02x}{b:02x}",
            "area": area,
            "cx": int(round(cx[gid0])),
            "cy": int(round(cy[gid0])),
            "border": bool(edge[gid0]),
        }
    return labels, info


def quantize(img: Image.Image, n_colors: int, smooth: int):
    rgb = img.convert("RGB")
    if smooth > 0:
        rgb = rgb.filter(ImageFilter.MedianFilter(size=smooth))
    q = rgb.quantize(colors=n_colors, method=Image.MEDIANCUT)
    idx = np.array(q)
    pal = q.getpalette()[: n_colors * 3]
    colors = [(pal[i], pal[i + 1], pal[i + 2]) for i in range(0, len(pal), 3)]
    return idx, colors


def label_map(idx: np.ndarray, colors):
    """Assign every pixel a globally-unique region label; collect per-region
    color / area / centroid / border-touch (no bbox)."""
    h, w = idx.shape
    labels = np.zeros((h, w), dtype=np.int32)
    info: dict[int, dict] = {}
    nxt = 1
    for ci in np.unique(idx):
        lab, n = ndimage.label(idx == ci, structure=STRUCT4)
        for comp in range(1, n + 1):
            sel = lab == comp
            gid = nxt
            nxt += 1
            labels[sel] = gid
            ys, xs = np.where(sel)
            r, g, b = colors[ci]
            info[gid] = {
                "color": f"#{r:02x}{g:02x}{b:02x}",
                "area": int(xs.size),
                "cx": int(round(xs.mean())),
                "cy": int(round(ys.mean())),
                "border": bool(xs.min() == 0 or ys.min() == 0 or xs.max() == w - 1 or ys.max() == h - 1),
            }
    return labels, info


def adjacency(labels: np.ndarray):
    """Neighbor pairs with their shared-edge strength: how many pixel pairs
    the two regions share along an exact 4-neighbor boundary."""
    pairs: dict[tuple[int, int], int] = {}
    for A, B in ((labels[:, :-1], labels[:, 1:]), (labels[:-1, :], labels[1:, :])):
        d = A != B
        if not d.any():
            continue
        u = np.stack([A[d], B[d]], axis=1)
        u.sort(axis=1)
        uniq, counts = np.unique(u, axis=0, return_counts=True)
        for (a, b), n in zip(uniq, counts):
            key = (int(a), int(b))
            pairs[key] = pairs.get(key, 0) + int(n)
    return pairs


def enclosures(info, neigh):
    """Inner is enclosed by Outer iff Inner never touches the edge and its ONLY
    neighbouring region is Outer — a true surround, independent of shape."""
    out = []
    for gid, i in info.items():
        if i["border"]:
            continue
        ns = neigh.get(gid, set())
        if len(ns) == 1:
            out.append((next(iter(ns)), gid))
    return out


def add_enclosed_parts(
    info,
    pairs,
    big: set,
    floor: int = 4,
    excluded_outers: set[int] | None = None,
) -> set:
    """Enclosed fillers survive min_area: a region fully surrounded by a kept
    part is itself a part (eye dots, mouth holes), however small - it is the
    thing that fills a cutout. Iterates so nested fillers (pupil inside iris
    inside eye-white) all make it in. Callers may exclude an elected exterior
    background so isolated image noise does not become a semantic filler."""
    neigh = defaultdict(set)
    excluded_outers = excluded_outers or set()
    for a, b in pairs:
        neigh[a].add(b)
        neigh[b].add(a)
    added = True
    while added:
        added = False
        for outer, inner in enclosures(info, neigh):
            if (
                outer in big
                and outer not in excluded_outers
                and inner not in big
                and info[inner]["area"] >= floor
            ):
                big.add(inner)
                added = True
    return big


def perimeters(labels: np.ndarray) -> dict[int, int]:
    """Boundary length per region: pixel pairs facing a different region plus
    pixels on the image edge (bbox-free shape cue: perimeter^2/area separates
    compact tiles from organic silhouettes)."""
    out: dict[int, int] = defaultdict(int)
    for A, B in ((labels[:, :-1], labels[:, 1:]), (labels[:-1, :], labels[1:, :])):
        d = A != B
        if not d.any():
            continue
        for side in (A[d], B[d]):
            ids, counts = np.unique(side, return_counts=True)
            for gid, count in zip(ids, counts):
                out[int(gid)] += int(count)
    for sel in (labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]):
        ids, counts = np.unique(sel, return_counts=True)
        for gid, count in zip(ids, counts):
            out[int(gid)] += int(count)
    return out


def _neighbors8(point: tuple[int, int], pool: set) -> list[tuple[int, int]]:
    x, y = point
    return [(x + dx, y + dy)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if (dx or dy) and (x + dx, y + dy) in pool]


def _prune_spurs(points: set, dist: np.ndarray) -> set:
    """Keep only the CREST of the medial axis (think of the part as a sand
    mound: height = distance to the nearest edge; the midline is the ridge
    of highest points). The exact medial axis grows spurs that CLIMB from
    every corner up to the crest — a solid rectangle would get 4 diagonals.
    From each endpoint, walk while the height keeps climbing and prune that
    climb (when its length fits the corner geometry), leaving the rectangle
    a single straight line ending as far from the short sides as it is from
    the long sides. Ridges (constant height) never climb, so they survive."""
    pts = set(points)
    for _ in range(12):
        changed = False
        for endpoint in [p for p in pts if len(_neighbors8(p, pts)) == 1]:
            if endpoint not in pts:
                continue
            branch = [endpoint]
            prev: tuple[int, int] | None = None
            cur = endpoint
            while True:
                nxt = [n for n in _neighbors8(cur, pts) if n != prev]
                if len(nxt) != 1:
                    break  # junction or chain end: the climb stops here
                if dist[nxt[0][1], nxt[0][0]] <= dist[cur[1], cur[0]] + 0.2:
                    break  # stopped climbing: we reached the crest plateau
                branch.append(nxt[0])
                prev, cur = cur, nxt[0]
            climb = branch[:-1]  # keep the top pixel: the crest starts there
            if not climb:
                continue
            top = branch[-1]
            crest_h = float(dist[top[1], top[0]])
            if len(climb) <= 1.6 * crest_h + 3:
                pts -= set(climb)
                changed = True
        if not changed:
            break
    return pts


def _simplify_no_cutout(path: list[tuple[int, int]], inside, tolerance: float) -> list[tuple[int, int]]:
    """Douglas-Peucker constrained to the part raster: a chord is accepted
    only when every pixel under it stays inside the part, so midlines never
    cross into cutouts. Kept vertices are original skeleton pixels - each one
    could seed a fill. Points that merely touch an edge stay; fill is simply
    never called from midline points (fillpoint/3 owns that)."""
    if len(path) <= 2:
        return list(path)

    def chord_ok(i: int, j: int) -> bool:
        x0, y0 = path[i]
        x1, y1 = path[j]
        n = int(max(abs(x1 - x0), abs(y1 - y0)))
        for t in range(1, n):
            if not inside(round(x0 + (x1 - x0) * t / n), round(y0 + (y1 - y0) * t / n)):
                return False
        return True

    keep = {0, len(path) - 1}
    stack = [(0, len(path) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        x0, y0 = path[i]
        x1, y1 = path[j]
        dx, dy = x1 - x0, y1 - y0
        norm = (dx * dx + dy * dy) ** 0.5 or 1.0
        kmax, dmax = -1, -1.0
        for k in range(i + 1, j):
            px, py = path[k]
            d = abs(dx * (y0 - py) - dy * (x0 - px)) / norm
            if d > dmax:
                kmax, dmax = k, d
        if dmax <= tolerance and chord_ok(i, j):
            continue
        keep.add(kmax)
        stack.append((i, kmax))
        stack.append((kmax, j))
    return [path[k] for k in sorted(keep)]


def to_prolog(info, pairs, big: set, w: int, h: int, perims: dict[int, int] | None = None,
              polygons: dict[int, dict] | None = None,
              midlines: dict[int, list[list[tuple[int, int]]]] | None = None,
              fillpoints: dict[int, list[tuple[int, int, float]]] | None = None) -> str:
    neigh = defaultdict(set)
    for a, b in pairs:
        neigh[a].add(b)
        neigh[b].add(a)
    encl = [(o, i) for (o, i) in enclosures(info, neigh) if o in big and i in big]
    L = [
        "% bbox-FREE region facts (topology only).",
        ":- dynamic region/4.", ":- dynamic adjacent/2.", ":- dynamic shared_edge/3.",
        ":- dynamic encloses/2.", ":- dynamic border/1.", ":- dynamic img_size/2.",
        ":- dynamic perimeter/2.", ":- dynamic polygon/2.", ":- dynamic hole/2.",
        ":- dynamic midline/2.", ":- dynamic fillpoint/3.",
        ":- discontiguous region/4.", ":- discontiguous adjacent/2.",
        ":- discontiguous shared_edge/3.", ":- discontiguous encloses/2.",
        ":- discontiguous border/1.", ":- discontiguous perimeter/2.",
        ":- discontiguous polygon/2.", ":- discontiguous hole/2.",
        ":- discontiguous midline/2.", ":- discontiguous fillpoint/3.",
        f"img_size({w}, {h}).", "",
    ]
    for gid in sorted(big, key=lambda g: -info[g]["area"]):
        i = info[gid]
        L.append(f"region(r{gid}, '{i['color']}', {i['area']}, centroid({i['cx']},{i['cy']})).")
        if perims and gid in perims:
            L.append(f"perimeter(r{gid}, {perims[gid]}).")
        if polygons and gid in polygons:
            outer = ",".join(f"xy({x},{y})" for x, y in polygons[gid]["outer"])
            L.append(f"polygon(r{gid}, [{outer}]).")
            for hole_points in polygons[gid]["holes"]:
                inner = ",".join(f"xy({x},{y})" for x, y in hole_points)
                L.append(f"hole(r{gid}, [{inner}]).")
        if midlines and gid in midlines:
            for line in midlines[gid]:
                mid = ",".join(f"xy({x},{y})" for x, y in line)
                L.append(f"midline(r{gid}, [{mid}]).")
        if fillpoints and gid in fillpoints:
            for fx, fy, depth in fillpoints[gid]:
                L.append(f"fillpoint(r{gid}, xy({fx},{fy}), {depth}).")
        if i["border"]:
            L.append(f"border(r{gid}).")
    L.append("")
    for (a, b) in sorted(pairs):
        if a in big and b in big:
            L.append(f"adjacent(r{a}, r{b}).")
            L.append(f"shared_edge(r{a}, r{b}, {pairs[(a, b)]}).")
    L.append("")
    for o, i in encl:
        L.append(f"encloses(r{o}, r{i}).")
    return "\n".join(L) + "\n"
