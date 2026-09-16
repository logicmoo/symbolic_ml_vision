"""Recognition-only extraction from logicmoo/omega_vision.

Source: python/omega_vision/perception/symbolic_arc.py
Source SHA-256: 462575f05845ee08c94ab5b89ecfa7d6f376d9439174f58cad6d549bfb61b2d3
LGPL-2.1-or-later; see LICENSE. Storage, runtime, and event code omitted.
"""
from __future__ import annotations

import hashlib
from math import gcd


_D4 = (
    ("identity", lambda x, y: (x, y)),
    ("rot90", lambda x, y: (y, -x)),
    ("rot180", lambda x, y: (-x, -y)),
    ("rot270", lambda x, y: (-y, x)),
    ("flip_h", lambda x, y: (-x, y)),
    ("flip_v", lambda x, y: (x, -y)),
    ("transpose", lambda x, y: (y, x)),
    ("anti_transpose", lambda x, y: (-y, -x)),
)


def _norm(offs) -> frozenset:
    if not offs:
        return frozenset()
    mnx = min(o[0] for o in offs)
    mny = min(o[1] for o in offs)
    return frozenset((o[0] - mnx, o[1] - mny) for o in offs)


def _canon_key(offs) -> tuple:
    """Shape key invariant under all 8 flips/rotations (smallest variant)."""
    best = None
    for _n, f in _D4:
        t = tuple(sorted(_norm([f(x, y) for x, y in offs])))
        if best is None or t < best:
            best = t
    return best or ()


def _canon_br(offs) -> tuple:
    """The Buttered Toast Algorithm: bottom-right rotational normalization.

    Like buttered toast landing butter-side down, flip/rotate the shape so its
    heavy side falls to the bottom-right, giving a deterministic canonical
    orientation (see workbench/docs/design/BUTTERED_TOAST_NORMALIZATION.md).
    Scoring, highest priority first (each rule breaks ties of the previous one):
      1. the bottom-right CORNER cell (w-1, h-1) is filled -- touching the corner
         beats any mere pixel count,
      2. most pixels in the bottom-right QUADRANT,
      3. else most pixels in the BOTTOM HALF,
      4. most mass toward bottom-right (sum x+y), then lexicographic.
    If no orientation beats the current one it is already normalized. Same D4
    equivalence class as _canon_key, just a bottom-right representative."""
    best = None
    for _n, f in _D4:
        t = tuple(sorted(_norm([f(x, y) for x, y in offs])))
        cells = set(t)
        w = max(x for x, _ in t) + 1
        h = max(y for _, y in t) + 1
        corner = 1 if (w - 1, h - 1) in cells else 0
        quad = sum(1 for (x, y) in t if 2 * x >= w and 2 * y >= h)
        bottom = sum(1 for (_x, y) in t if 2 * y >= h)
        mass = sum(x + y for x, y in t)
        key = (corner, quad, bottom, mass, t)
        if best is None or key > best[0]:
            best = (key, t)
    return best[1] if best else ()


_MONOMINO = {"monomino": [(0, 0)]}


_DOMINO = {"domino": [(0, 0), (1, 0)]}


_TROMINOES = {
    "tromino_I": [(0, 0), (1, 0), (2, 0)],
    "tromino_L": [(0, 0), (1, 0), (0, 1)],
}


_TETROMINOES = {
    "tetromino_I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "tetromino_O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "tetromino_T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "tetromino_S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "tetromino_L": [(0, 0), (0, 1), (0, 2), (1, 2)],
}


_PENTOMINOES = {
    "pentomino_F": [(1, 0), (2, 0), (0, 1), (1, 1), (1, 2)],
    "pentomino_I": [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)],
    "pentomino_L": [(0, 0), (0, 1), (0, 2), (0, 3), (1, 3)],
    "pentomino_N": [(1, 0), (1, 1), (0, 2), (1, 2), (0, 3)],
    "pentomino_P": [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2)],
    "pentomino_T": [(0, 0), (1, 0), (2, 0), (1, 1), (1, 2)],
    "pentomino_U": [(0, 0), (2, 0), (0, 1), (1, 1), (2, 1)],
    "pentomino_V": [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)],
    "pentomino_W": [(0, 0), (0, 1), (1, 1), (1, 2), (2, 2)],
    "pentomino_X": [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)],
    "pentomino_Y": [(1, 0), (0, 1), (1, 1), (1, 2), (1, 3)],
    "pentomino_Z": [(0, 0), (1, 0), (1, 1), (1, 2), (2, 2)],
}


_SPECIAL_NAMED = {
    "empty_box": [(x, y) for y in range(3) for x in range(3) if x in (0, 2) or y in (0, 2)],
    "empty_rectangle": [(x, y) for y in range(3) for x in range(4) if x in (0, 3) or y in (0, 2)],
}


def _proportional_cells(offs) -> list:
    """Proportional (un-pixelated) form: divide the shape by its largest integer
    BLOCK factor k, where the shape is exactly a k-by-k-block upscale (every k x k
    block is uniformly filled or empty). Preserves the exact shape and true aspect
    ratio at the smallest integer scale: a 2x-scaled sprite -> the base shape, a
    6x3 solid -> 2x1, but a 5x3 (gcd 1) stays 5x3. Distinct from squared (collapse
    all runs) and aspect (landscape/portrait/square class)."""
    cells = set(map(tuple, offs))
    if not cells:
        return []
    w = max(x for x, _ in cells) + 1
    h = max(y for _, y in cells) + 1
    g = gcd(w, h)
    for k in sorted((d for d in range(2, g + 1) if g % d == 0), reverse=True):
        ok = True
        for by in range(h // k):
            for bx in range(w // k):
                filled = [(bx * k + i, by * k + j) in cells
                          for j in range(k) for i in range(k)]
                if any(filled) and not all(filled):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return sorted({(x // k, y // k) for (x, y) in cells})
    return sorted(cells)


def _box_cut_name(ck) -> str:
    """Universal fallback descriptor: the shape's bounding box (H x W) minus the
    cells that are cut out of it. A solid rectangle is `box_HxW`; otherwise
    `box_HxW_cut_N_at_rYcX_...` listing the removed cells in row-major order.
    Canonical (the D4-canonical orientation) so it is unique per free shape."""
    xs = [c[0] for c in ck]
    ys = [c[1] for c in ck]
    w = max(xs) + 1
    h = max(ys) + 1
    filled = set(ck)
    cuts = [(x, y) for y in range(h) for x in range(w) if (x, y) not in filled]
    if not cuts:
        return f"box_{h}x{w}"
    pos = "_".join(f"r{y}c{x}" for (x, y) in cuts)
    return f"box_{h}x{w}_cut_{len(cuts)}_at_{pos}"


_NAMED_LOOKUP: "dict | None" = None


def _named_lookup() -> dict:
    """Memoized {D4-canonical key: letter name} for the classically named small
    polyominoes (monomino .. pentomino) plus the named hollow-frame shapes
    (empty_box, empty_rectangle)."""
    global _NAMED_LOOKUP
    if _NAMED_LOOKUP is None:
        _NAMED_LOOKUP = {}
        for nm, cells in {**_MONOMINO, **_DOMINO, **_TROMINOES,
                          **_TETROMINOES, **_PENTOMINOES, **_SPECIAL_NAMED}.items():
            _NAMED_LOOKUP[_canon_key(cells)] = nm
    return _NAMED_LOOKUP


def _name_of_cells(cells) -> str:
    """Name of a cell set: its letter name if it is a classic small polyomino,
    otherwise its universal box-cut descriptor. Used to see whether a shrunk large
    shape 'gets lucky' and collapses onto a named thing."""
    if not cells:
        return ""
    ck = _canon_key(cells)
    return _named_lookup().get(ck) or _box_cut_name(ck)


_MAX_IDENTITY_CELLS = 4096


def _identity_name(off) -> str:
    """Option-A OBJECT identity: the shape's NAME after un-pixelating to its
    smallest integer scale. Color, full size, and position are occurrence
    attributes -- so two occurrences that are the same shape up to color, integer
    scale, rotation, and reflection share this identity (recolor / resize / move
    all keep the same object). Uses the proportional (un-pixelated) form, so a
    2x-scaled sprite and its base collapse to one identity; names via the classic
    polyomino vocabulary, else a box-cut descriptor. Very large or very complex
    regions (whose box-cut descriptor would be unwieldy) fall back to a compact
    rotation-normalized colour-free hash -- still recolour-invariant."""
    cells = [tuple(c) for c in off]
    if not cells:
        return ""
    if len(cells) > _MAX_IDENTITY_CELLS:
        return "shape_" + hashlib.sha1(repr(_canon_br(cells)).encode("utf-8")).hexdigest()[:12]
    prop = _proportional_cells(cells)
    name = _name_of_cells(prop)
    # a big cut-list box name is unreadable and bloats the store: keep only the
    # bounding-box size and a stable hash of the exact prop shape.
    if len(name) > 48:
        h, w = 0, 0
        if prop:
            w = max(x for x, _ in prop) + 1
            h = max(y for _, y in prop) + 1
        return f"shape_{h}x{w}_" + hashlib.sha1(repr(sorted(prop)).encode("utf-8")).hexdigest()[:10]
    return name
