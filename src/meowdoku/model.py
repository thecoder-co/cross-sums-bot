"""Validated Meowdoku puzzle and solution models."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable


Cell = tuple[int, int]


def _normalize_regions(rows: Iterable[Iterable[object]]) -> tuple[tuple[int, ...], ...]:
    normalized: dict[object, int] = {}
    result: list[tuple[int, ...]] = []
    for row in rows:
        output: list[int] = []
        for value in row:
            try:
                region = normalized.setdefault(value, len(normalized))
            except TypeError as error:
                raise ValueError("region identifiers must be scalar values") from error
            output.append(region)
        result.append(tuple(output))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class MeowdokuPuzzle:
    regions: tuple[tuple[int, ...], ...]
    known_cats: tuple[Cell, ...] = ()
    known_empty: tuple[Cell, ...] = ()

    def __post_init__(self) -> None:
        size = len(self.regions)
        if size < 3:
            raise ValueError("a Meowdoku board must be at least 3x3")
        if any(len(row) != size for row in self.regions):
            raise ValueError("Meowdoku regions must form a square board")

        region_ids = {region for row in self.regions for region in row}
        if region_ids != set(range(size)):
            raise ValueError(f"an {size}x{size} board must contain exactly {size} regions")
        for region in region_ids:
            if not self._region_is_connected(region):
                raise ValueError(f"region {region} is not orthogonally connected")

        self._validate_cells(self.known_cats, "known cat")
        self._validate_cells(self.known_empty, "known empty cell")
        if set(self.known_cats) & set(self.known_empty):
            raise ValueError("a cell cannot be both a known cat and known empty")
        if not _cats_are_legal(self.regions, self.known_cats):
            raise ValueError("known cats violate Meowdoku constraints")

    @property
    def size(self) -> int:
        return len(self.regions)

    @property
    def cats(self) -> tuple[Cell, ...]:
        """Compatibility alias for screenshot/automation callers."""

        return self.known_cats

    def _validate_cells(self, cells: tuple[Cell, ...], label: str) -> None:
        if len(set(cells)) != len(cells):
            raise ValueError(f"{label}s must be unique")
        for row, column in cells:
            if not (0 <= row < self.size and 0 <= column < self.size):
                raise ValueError(f"{label} is outside the board")

    def _region_is_connected(self, region: int) -> bool:
        cells = {
            (row, column)
            for row, values in enumerate(self.regions)
            for column, value in enumerate(values)
            if value == region
        }
        pending = deque([next(iter(cells))])
        visited: set[Cell] = set()
        while pending:
            cell = pending.popleft()
            if cell in visited:
                continue
            visited.add(cell)
            row, column = cell
            for neighbor in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            ):
                if neighbor in cells and neighbor not in visited:
                    pending.append(neighbor)
        return visited == cells

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "MeowdokuPuzzle":
        raw_regions = payload.get("regions")
        if not isinstance(raw_regions, list):
            raise ValueError("regions must be a list of rows")
        if any(not isinstance(row, list) for row in raw_regions):
            raise ValueError("every regions row must be a list")
        raw_cats = payload.get("known_cats", payload.get("cats", []))
        if not isinstance(raw_cats, list):
            raise ValueError("known_cats must be a list of [row, column] pairs")
        raw_empty = payload.get("known_empty", [])
        if not isinstance(raw_empty, list):
            raise ValueError("known_empty must be a list of [row, column] pairs")

        def parse_cells(values: list[object], name: str) -> tuple[Cell, ...]:
            cells: list[Cell] = []
            for cell in values:
                if (
                    not isinstance(cell, list)
                    or len(cell) != 2
                    or not all(isinstance(value, int) for value in cell)
                ):
                    raise ValueError(
                        f"{name} must contain [row, column] integer pairs"
                    )
                cells.append((cell[0], cell[1]))
            return tuple(cells)

        return cls(
            _normalize_regions(raw_regions),
            parse_cells(raw_cats, "known_cats"),
            parse_cells(raw_empty, "known_empty"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "regions": [list(row) for row in self.regions],
            "known_cats": [list(cell) for cell in self.known_cats],
            "known_empty": [list(cell) for cell in self.known_empty],
        }


@dataclass(frozen=True, slots=True)
class MeowdokuSolution:
    cats: tuple[Cell, ...]

    def selected_cells(self) -> tuple[Cell, ...]:
        return tuple(sorted(self.cats))

    def selected_matrix(self, size: int) -> tuple[tuple[bool, ...], ...]:
        selected = set(self.cats)
        return tuple(
            tuple((row, column) in selected for column in range(size))
            for row in range(size)
        )


def _cats_are_legal(
    regions: tuple[tuple[int, ...], ...], cats: Iterable[Cell]
) -> bool:
    placed = tuple(cats)
    rows = [row for row, _ in placed]
    columns = [column for _, column in placed]
    region_ids = [regions[row][column] for row, column in placed]
    if len(rows) != len(set(rows)):
        return False
    if len(columns) != len(set(columns)):
        return False
    if len(region_ids) != len(set(region_ids)):
        return False
    return all(
        max(abs(row_a - row_b), abs(column_a - column_b)) > 1
        for index, (row_a, column_a) in enumerate(placed)
        for row_b, column_b in placed[index + 1 :]
    )
