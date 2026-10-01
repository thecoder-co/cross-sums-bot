"""Recognize a Meowdoku board from a screenshot without OCR."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import dist
from pathlib import Path
from statistics import median

from PIL import Image

from .geometry import BoardReadError, GridGeometry, locate_grid
from .model import Cell, MeowdokuPuzzle


@dataclass(frozen=True, slots=True)
class DetectedMeowdoku:
    puzzle: MeowdokuPuzzle
    geometry: GridGeometry
    image_width: int
    image_height: int
    fingerprint: tuple[tuple[int, ...], ...]


def _background_color(
    image: Image.Image, geometry: GridGeometry, row: int, column: int
) -> tuple[int, int, int]:
    center_x, center_y = geometry.cell_center(row, column)
    candidates: list[tuple[int, int, int]] = []
    radius_x = geometry.cell_width * 0.39
    radius_y = geometry.cell_height * 0.39
    for y in range(
        max(0, round(center_y - radius_y)),
        min(image.height, round(center_y + radius_y + 1)),
    ):
        for x in range(
            max(0, round(center_x - radius_x)),
            min(image.width, round(center_x + radius_x + 1)),
        ):
            normalized_x = abs(x - center_x) / geometry.cell_width
            normalized_y = abs(y - center_y) / geometry.cell_height
            ring = max(normalized_x, normalized_y)
            red, green, blue = image.getpixel((x, y))
            if (
                0.31 <= ring <= 0.39
                and max(red, green, blue) - min(red, green, blue) >= 35
            ):
                candidates.append((red, green, blue))
    if not candidates:
        raise BoardReadError(f"Could not sample cell ({row}, {column})")
    bins = Counter(
        (red // 12, green // 12, blue // 12) for red, green, blue in candidates
    )
    winner, count = bins.most_common(1)[0]
    values = [
        color
        for color in candidates
        if tuple(channel // 12 for channel in color) == winner
    ]
    if count < max(8, len(candidates) * 0.12):
        raise BoardReadError(f"Cell ({row}, {column}) has no stable region color")
    return tuple(round(median(channel)) for channel in zip(*values))  # type: ignore[return-value]


def _cluster_regions(
    colors: list[list[tuple[int, int, int]]], expected: int
) -> tuple[tuple[int, ...], ...]:
    centers: list[list[tuple[int, int, int]]] = []
    labels: list[list[int]] = []
    for row in colors:
        output: list[int] = []
        for color in row:
            distances = [dist(color, tuple(map(median, zip(*cluster)))) for cluster in centers]
            if distances and min(distances) <= 34:
                label = min(range(len(distances)), key=distances.__getitem__)
                centers[label].append(color)
            else:
                label = len(centers)
                centers.append([color])
            output.append(label)
        labels.append(output)
    if len(centers) != expected:
        raise BoardReadError(
            f"Expected {expected} colored regions, recognized {len(centers)}"
        )
    if any(
        dist(color, tuple(map(median, zip(*centers[label])))) > 24
        for row_index, row in enumerate(colors)
        for column_index, color in enumerate(row)
        for label in (labels[row_index][column_index],)
    ):
        raise BoardReadError("A cell color was too ambiguous to classify safely")
    return tuple(tuple(row) for row in labels)


def _cell_marker(
    image: Image.Image,
    geometry: GridGeometry,
    row: int,
    column: int,
    background: tuple[int, int, int],
) -> str:
    center_x, center_y = geometry.cell_center(row, column)
    radius_x = max(2, round(geometry.cell_width * 0.28))
    radius_y = max(2, round(geometry.cell_height * 0.28))
    foreground = 0
    dark = 0
    white = 0
    total = 0
    for y in range(max(0, round(center_y - radius_y)), min(image.height, round(center_y + radius_y + 1))):
        for x in range(max(0, round(center_x - radius_x)), min(image.width, round(center_x + radius_x + 1))):
            total += 1
            pixel = image.getpixel((x, y))
            if dist(pixel, background) >= 48:
                foreground += 1
                luminance = sum(pixel) / 3
                if luminance < 90:
                    dark += 1
                if min(pixel) > 205:
                    white += 1
    if not total:
        return "ambiguous"
    foreground_coverage = foreground / total
    dark_coverage = dark / total
    white_coverage = white / total
    if dark_coverage >= 0.05 and foreground_coverage >= 0.16:
        return "cat"
    if white_coverage >= 0.10 and dark_coverage < 0.04:
        return "x"
    if foreground_coverage < 0.06:
        return "empty"
    return "ambiguous"


def _recognize_marks(
    image: Image.Image,
    geometry: GridGeometry,
    colors: list[list[tuple[int, int, int]]],
) -> tuple[tuple[Cell, ...], tuple[Cell, ...]]:
    """Recognize dark cat artwork while ignoring automatic white X marks."""

    cats: list[Cell] = []
    empty: list[Cell] = []
    for row in range(geometry.size):
        for column in range(geometry.size):
            marker = _cell_marker(image, geometry, row, column, colors[row][column])
            if marker == "cat":
                cats.append((row, column))
            elif marker == "x":
                empty.append((row, column))
            elif marker == "ambiguous":
                raise BoardReadError(
                    f"Cell ({row}, {column}) contains an ambiguous mark"
                )
    return tuple(cats), tuple(empty)


def read_image(image: Image.Image) -> DetectedMeowdoku:
    rgb = image.convert("RGB")
    geometry = locate_grid(rgb)
    colors = [
        [_background_color(rgb, geometry, row, column) for column in range(geometry.size)]
        for row in range(geometry.size)
    ]
    regions = _cluster_regions(colors, geometry.size)
    cats, empty = _recognize_marks(rgb, geometry, colors)
    try:
        puzzle = MeowdokuPuzzle(
            regions=regions,
            known_cats=cats,
            known_empty=empty,
        )
    except ValueError as error:
        raise BoardReadError(str(error)) from error
    return DetectedMeowdoku(
        puzzle=puzzle,
        geometry=geometry,
        image_width=rgb.width,
        image_height=rgb.height,
        fingerprint=regions,
    )


def read_screenshot(path: Path) -> DetectedMeowdoku:
    try:
        with Image.open(path) as source:
            return read_image(source)
    except (OSError, ValueError) as error:
        if isinstance(error, BoardReadError):
            raise
        raise BoardReadError(f"Could not read screenshot: {error}") from error
