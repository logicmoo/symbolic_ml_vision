"""In-memory image-grid recognition, without the Workbench runtime."""

from collections import defaultdict
from hashlib import sha256
import re

from grid_core import DEFAULT_GRID, _boundary_cells, _components, _hole_regions, _shape
from shape_core import _TETROMINOES, _canon_key, _identity_name, _proportional_cells


ARC_PALETTE = [
    "#101725", "#5d8df5", "#ef6a61", "#60bb9c", "#efd06b",
    "#9bacc5", "#c88ce5", "#eaa367", "#66c6d3", "#9c7861",
]
MAX_SIDE = 64
MAX_COLORS = 256
MAX_OBJECTS = 512


def validate(payload: object) -> tuple[list[list[int]], list[str], int | None]:
    if not isinstance(payload, dict):
        raise ValueError("Send an object containing grid, palette, and background.")
    grid = payload.get("grid")
    palette = payload.get("palette")
    background = payload.get("background", 0)
    if not isinstance(palette, list) or not 1 <= len(palette) <= MAX_COLORS:
        raise ValueError(f"Palette must contain 1 to {MAX_COLORS} hex colors.")
    if any(not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in palette):
        raise ValueError("Palette colors must use #RRGGBB notation.")
    if len({color.lower() for color in palette}) != len(palette):
        raise ValueError("Palette colors must be distinct.")
    if not isinstance(grid, list) or not 1 <= len(grid) <= MAX_SIDE:
        raise ValueError(f"Grid must contain 1 to {MAX_SIDE} rows.")
    width = len(grid[0]) if isinstance(grid[0], list) else 0
    if not 1 <= width <= MAX_SIDE:
        raise ValueError(f"Grid width must be 1 to {MAX_SIDE} cells.")
    for row in grid:
        if not isinstance(row, list) or len(row) != width:
            raise ValueError("Grid rows must have equal widths.")
        if any(type(value) is not int or not 0 <= value < len(palette) for value in row):
            raise ValueError("Every grid cell must be an integer index into the palette.")
    if background is not None and (
        type(background) is not int or not 0 <= background < len(palette)
    ):
        raise ValueError("Background must be a palette index, or null for no background.")
    return grid, [color.lower() for color in palette], background


def recognize(payload: object) -> dict:
    grid, palette, background = validate(payload)
    # The extracted component finder reserves zero for background.
    indexed = [[0 if value == background else value + 1 for value in row] for row in grid]
    components = _components(indexed)
    if len(components) > MAX_OBJECTS:
        raise ValueError(f"More than {MAX_OBJECTS} separate regions; reduce the palette or grid size.")

    objects = []
    owners = {}
    groups = defaultdict(list)
    reconstructed = [[background for _ in row] for row in grid]
    for ordinal, component in enumerate(components, 1):
        identifier = f"object-{ordinal}"
        color_index = component.color - 1
        offsets = [(x - component.min_x, y - component.min_y) for x, y in component.cells]
        canonical = _canon_key(_proportional_cells(offsets))
        identity = "shape-" + sha256(repr(canonical).encode("ascii")).hexdigest()[:16]
        holes = _hole_regions(component)
        objects.append({
            "id": identifier,
            "shape_id": identity,
            "name": _identity_name(canonical),
            "geometry": _shape(component),
            "color": palette[color_index],
            "color_index": color_index,
            "area": len(component.cells),
            "bounds": [component.min_x, component.min_y, component.width, component.height],
            "cells": [list(cell) for cell in component.cells],
            "boundary_cells": [list(cell) for cell in _boundary_cells(component)],
            "hole_count": len(holes),
            "canonical_cells": [list(cell) for cell in canonical],
            "adjacent_to": [],
        })
        groups[identity].append(identifier)
        for x, y in component.cells:
            owners[x, y] = identifier
            reconstructed[y][x] = color_index

    contacts = defaultdict(set)
    for (x, y), identifier in owners.items():
        for neighbor in ((x + 1, y), (x, y + 1)):
            other = owners.get(neighbor)
            if other and other != identifier:
                contacts[identifier].add(other)
                contacts[other].add(identifier)
    for obj in objects:
        obj["adjacent_to"] = sorted(contacts[obj["id"]])

    return {
        "schema_version": 1,
        "engine": "Omega Vision geometric recognition",
        "width": len(grid[0]),
        "height": len(grid),
        "grid": grid,
        "palette": palette,
        "background": background,
        "objects": objects,
        "object_count": len(objects),
        "shape_count": len(groups),
        "foreground_cells": len(owners),
        "reconstruction": reconstructed,
        "exact_reconstruction": reconstructed == grid,
        "repeated_shapes": [
            {"shape_id": identity, "objects": identifiers}
            for identity, identifiers in groups.items() if len(identifiers) > 1
        ],
        "limits": {
            "recognition": "Connected color regions and geometric shapes, not semantic photo labels.",
            "identity": "Shape IDs ignore color, translation, rotation, reflection, and exact integer scale. Object IDs are local to this image, not tracked entities.",
            "reconstruction": "Compared with the submitted analysis grid, not an unprocessed source photograph.",
        },
    }


def examples() -> list[dict]:
    repeats = [[0] * 28 for _ in range(16)]
    placements = [
        ("tetromino_T", 2, 2, 1, 1),
        ("tetromino_T", 11, 2, 2, 2),
        ("tetromino_L", 3, 9, 1, 3),
        ("tetromino_L", 13, 10, 1, 4),
        ("tetromino_S", 21, 10, 1, 6),
    ]
    for name, origin_x, origin_y, scale, color in placements:
        for x, y in _TETROMINOES[name]:
            for dy in range(scale):
                for dx in range(scale):
                    repeats[origin_y + y * scale + dy][origin_x + x * scale + dx] = color
    return [
        {
            "id": "topology",
            "title": "A ring and an angle",
            "description": "Original recognition example: two regions, including a shape with a hole.",
            "grid": DEFAULT_GRID,
            "palette": ARC_PALETTE,
            "background": 0,
        },
        {
            "id": "repeats",
            "title": "Same shape, different appearance",
            "description": "Built from the original tetromino vocabulary. Color, position, and integer scale do not change a shape's identity.",
            "grid": repeats,
            "palette": ARC_PALETTE,
            "background": 0,
        },
        {
            "id": "blank",
            "title": "Draw your own",
            "description": "An empty 24 x 16 canvas. Paint connected shapes, then recognize them.",
            "grid": [[0] * 24 for _ in range(16)],
            "palette": ARC_PALETTE,
            "background": 0,
        },
    ]
