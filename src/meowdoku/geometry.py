"""Locate a regular Meowdoku grid from its colored cell interiors."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from PIL import Image


class BoardReadError(ValueError):
    """The screenshot cannot be read confidently as a Meowdoku board."""


@dataclass(frozen=True, slots=True)
class GridGeometry:
    left: float
    top: float
    cell_width: float
    cell_height: float
    size: int

    @property
    def right(self) -> float:
        return self.left + self.cell_width * self.size

    @property
    def bottom(self) -> float:
        return self.top + self.cell_height * self.size

    def cell_center(self, row: int, column: int) -> tuple[float, float]:
        if not (0 <= row < self.size and 0 <= column < self.size):
            raise IndexError("cell is outside the board")
        return (
            self.left + (column + 0.5) * self.cell_width,
            self.top + (row + 0.5) * self.cell_height,
        )


def _bands(counts: list[int], threshold: int, minimum_length: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, count in enumerate((*counts, 0)):
        if count >= threshold and start is None:
            start = index
        elif count < threshold and start is not None:
            if index - start >= minimum_length:
                result.append((start, index - 1))
            start = None
    return result


def _projection_grid(image: Image.Image) -> GridGeometry | None:
    """Locate cell bands even when cats and automatic X marks cover cells."""

    scale = min(1.0, 900 / image.width)
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    hsv = image.resize((width, height)).convert("HSV")
    raw = hsv.tobytes()
    mask = bytearray(width * height)
    row_counts = [0] * height
    for index in range(width * height):
        saturation = raw[index * 3 + 1]
        value = raw[index * 3 + 2]
        if saturation >= 65 and value >= 55:
            mask[index] = 1
            row_counts[index // width] += 1

    y_bands = _bands(
        row_counts,
        threshold=max(20, round(width * 0.25)),
        minimum_length=max(8, round(height * 0.018)),
    )
    if not 3 <= len(y_bands) <= 12:
        return None
    y_centers = [(start + end) / 2 for start, end in y_bands]
    dy = median(bottom - top for top, bottom in zip(y_centers, y_centers[1:]))
    if any(abs((bottom - top) - dy) > dy * 0.06 for top, bottom in zip(y_centers, y_centers[1:])):
        return None

    y_start = y_bands[0][0]
    y_end = y_bands[-1][1]
    x_counts = [0] * width
    for y in range(y_start, y_end + 1):
        offset = y * width
        for x in range(width):
            x_counts[x] += mask[offset + x]
    x_bands = _bands(
        x_counts,
        threshold=max(20, round((y_end - y_start + 1) * 0.25)),
        minimum_length=max(8, round(width * 0.018)),
    )
    if len(x_bands) != len(y_bands):
        return None
    x_centers = [(start + end) / 2 for start, end in x_bands]
    dx = median(right - left for left, right in zip(x_centers, x_centers[1:]))
    if any(abs((right - left) - dx) > dx * 0.06 for left, right in zip(x_centers, x_centers[1:])):
        return None
    size = len(y_bands)
    return GridGeometry(
        left=(x_centers[0] - dx / 2) / scale,
        top=(y_centers[0] - dy / 2) / scale,
        cell_width=dx / scale,
        cell_height=dy / scale,
        size=size,
    )


def _colored_components(
    image: Image.Image,
) -> list[tuple[float, float, float, float, float]]:
    scale = min(1.0, 900 / image.width)
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    small = image.resize((width, height)).convert("HSV")
    raw = small.tobytes()
    pixels = bytearray(width * height)
    for index in range(width * height):
        saturation = raw[index * 3 + 1]
        value = raw[index * 3 + 2]
        if saturation >= 65 and value >= 55:
            pixels[index] = 1

    result: list[tuple[float, float, float, float, float]] = []
    for start in range(len(pixels)):
        if not pixels[start]:
            continue
        pixels[start] = 0
        stack = [start]
        area = 0
        x0 = x1 = start % width
        y0 = y1 = start // width
        while stack:
            position = stack.pop()
            x = position % width
            y = position // width
            area += 1
            x0, x1 = min(x0, x), max(x1, x)
            y0, y1 = min(y0, y), max(y1, y)
            neighbors = (
                position - 1 if x else -1,
                position + 1 if x + 1 < width else -1,
                position - width if y else -1,
                position + width if y + 1 < height else -1,
            )
            for neighbor in neighbors:
                if 0 <= neighbor < len(pixels) and pixels[neighbor]:
                    pixels[neighbor] = 0
                    stack.append(neighbor)

        component_width = x1 - x0 + 1
        component_height = y1 - y0 + 1
        fill = area / (component_width * component_height)
        if (
            component_width >= 24
            and component_height >= 24
            and 0.82 <= component_width / component_height <= 1.18
            and fill >= 0.84
        ):
            result.append(
                (
                    x0 / scale,
                    y0 / scale,
                    component_width / scale,
                    component_height / scale,
                    fill,
                )
            )
    return result


def _centers(values: list[float], tolerance: float) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or value - median(clusters[-1]) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [median(cluster) for cluster in clusters]


def locate_grid(image: Image.Image) -> GridGeometry:
    projected = _projection_grid(image)
    if projected is not None:
        return projected
    components = _colored_components(image)
    candidates: set[GridGeometry] = set()
    seen_groups: set[tuple[tuple[float, float, float, float, float], ...]] = set()
    for _, _, component_width, component_height, _ in components:
        group = tuple(
            component
            for component in components
            if abs(component[2] - component_width) < component_width * 0.10
            and abs(component[3] - component_height) < component_height * 0.10
        )
        if group in seen_groups:
            continue
        seen_groups.add(group)
        xs = _centers(
            [x + width / 2 for x, _, width, _, _ in group],
            component_width * 0.25,
        )
        ys = _centers(
            [y + height / 2 for _, y, _, height, _ in group],
            component_height * 0.25,
        )
        if not (3 <= len(xs) <= 12 and len(xs) == len(ys)):
            continue
        size = len(xs)
        # A cat icon can split or substantially cover the saturated cell
        # interior. A valid board has at most one cat per row, so tolerate up
        # to one missing component per row while deriving the regular grid.
        if not size * size - size <= len(group) <= size * size:
            continue
        dx = median(right - left for left, right in zip(xs, xs[1:]))
        dy = median(bottom - top for top, bottom in zip(ys, ys[1:]))
        if not (
            component_width <= dx <= component_width * 1.30
            and component_height <= dy <= component_height * 1.30
        ):
            continue
        if any(abs((right - left) - dx) > dx * 0.05 for left, right in zip(xs, xs[1:])):
            continue
        if any(abs((bottom - top) - dy) > dy * 0.05 for top, bottom in zip(ys, ys[1:])):
            continue
        occupied = {
            (
                min(range(size), key=lambda index: abs(xs[index] - (x + width / 2))),
                min(range(size), key=lambda index: abs(ys[index] - (y + height / 2))),
            )
            for x, y, width, height, _ in group
        }
        if len(occupied) != len(group):
            continue
        row_counts = [sum(y_index == row for _, y_index in occupied) for row in range(size)]
        column_counts = [sum(x_index == column for x_index, _ in occupied) for column in range(size)]
        if min(row_counts, default=0) < size - 1 or min(column_counts, default=0) < size - 1:
            continue
        candidates.add(
            GridGeometry(
                left=xs[0] - dx / 2,
                top=ys[0] - dy / 2,
                cell_width=dx,
                cell_height=dy,
                size=size,
            )
        )
    if len(candidates) != 1:
        raise BoardReadError(
            "No single complete Meowdoku grid found. Open a fresh board and keep it fully visible."
        )
    return candidates.pop()
