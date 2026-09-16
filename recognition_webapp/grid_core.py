"""Recognition-only extraction from logicmoo/omega_vision.

Source: python/omega_vision/perception/grid_analysis.py
Source SHA-256: 73d2c7e87cad8e36d787568dd33354eb6892ac0212d3d1d6d101e5b15002e00d
LGPL-2.1-or-later; see LICENSE. Storage, runtime, and event code omitted.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


DEFAULT_GRID: list[list[int]] = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 0, 2, 0, 0],
    [0, 1, 0, 1, 0, 2, 0, 0],
    [0, 1, 1, 1, 0, 2, 2, 0],
    [0, 0, 0, 0, 0, 0, 0, 0],
]


COLOR_NAMES = {
    0: "black",
    1: "blue",
    2: "red",
    3: "green",
    4: "yellow",
    5: "gray",
    6: "magenta",
    7: "orange",
    8: "cyan",
    9: "brown",
}


@dataclass(frozen=True)
class Component:
    object_id: str
    color: int
    cells: tuple[tuple[int, int], ...]

    @property
    def min_x(self) -> int:
        return min(x for x, _ in self.cells)

    @property
    def max_x(self) -> int:
        return max(x for x, _ in self.cells)

    @property
    def min_y(self) -> int:
        return min(y for _, y in self.cells)

    @property
    def max_y(self) -> int:
        return max(y for _, y in self.cells)

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def height(self) -> int:
        return self.max_y - self.min_y + 1


def _components(grid: list[list[int]]) -> list[Component]:
    height = len(grid)
    width = len(grid[0])
    seen: set[tuple[int, int]] = set()
    found: list[Component] = []
    color_counts: dict[int, int] = {}

    for y in range(height):
        for x in range(width):
            color = grid[y][x]
            if color == 0 or (x, y) in seen:
                continue
            queue = deque([(x, y)])
            seen.add((x, y))
            cells: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                cells.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in seen and grid[ny][nx] == color:
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            color_counts[color] = color_counts.get(color, 0) + 1
            ordinal = color_counts[color]
            name = COLOR_NAMES.get(color, f"color_{color}")
            found.append(Component(f"obj_{name}_{ordinal}", color, tuple(sorted(cells, key=lambda p: (p[1], p[0])))))
    return found


def _shape(component: Component) -> str:
    occupied = set(component.cells)
    area = component.width * component.height
    count = len(component.cells)
    if count == area:
        return "rectangle" if component.width != component.height else "square"
    border = {
        (x, y)
        for y in range(component.min_y, component.max_y + 1)
        for x in range(component.min_x, component.max_x + 1)
        if x in (component.min_x, component.max_x) or y in (component.min_y, component.max_y)
    }
    if component.width >= 3 and component.height >= 3 and occupied == border:
        return "hollow_rectangle" if component.width != component.height else "hollow_square"
    if component.width == 1:
        return "vertical_line"
    if component.height == 1:
        return "horizontal_line"
    endpoints = 0
    for x, y in occupied:
        degree = sum((x + dx, y + dy) in occupied for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        if degree == 1:
            endpoints += 1
    if endpoints == 2 and count == component.width + component.height - 1:
        return "angle"
    return "irregular"


def _hole_regions(component: Component) -> list[list[tuple[int, int]]]:
    occupied = set(component.cells)
    empty = {
        (x, y)
        for y in range(component.min_y, component.max_y + 1)
        for x in range(component.min_x, component.max_x + 1)
        if (x, y) not in occupied
    }
    outside: set[tuple[int, int]] = set()
    queue = deque(
        cell
        for cell in empty
        if cell[0] in (component.min_x, component.max_x)
        or cell[1] in (component.min_y, component.max_y)
    )
    outside.update(queue)
    while queue:
        x, y = queue.popleft()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in empty and neighbor not in outside:
                outside.add(neighbor)
                queue.append(neighbor)
    remaining = empty - outside
    regions: list[list[tuple[int, int]]] = []
    while remaining:
        start = min(remaining, key=lambda item: (item[1], item[0]))
        region: list[tuple[int, int]] = []
        queue = deque([start])
        remaining.remove(start)
        while queue:
            cell = queue.popleft()
            region.append(cell)
            x, y = cell
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        regions.append(sorted(region, key=lambda item: (item[1], item[0])))
    return regions


def _boundary_cells(component: Component) -> list[tuple[int, int]]:
    occupied = set(component.cells)
    return [
        cell
        for cell in component.cells
        if any(
            (cell[0] + dx, cell[1] + dy) not in occupied
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        )
    ]
