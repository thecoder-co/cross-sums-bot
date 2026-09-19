from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Puzzle:
    """A Cross Sums board.

    ``grid[row][column]`` is the value printed in a cell. A solution selects a
    subset of cells such that every selected row and column sum equals its clue.
    """

    grid: tuple[tuple[int, ...], ...]
    row_targets: tuple[int, ...]
    column_targets: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.grid:
            raise ValueError("grid must have at least one row")
        columns = len(self.grid[0])
        if columns == 0:
            raise ValueError("grid must have at least one column")
        if any(len(row) != columns for row in self.grid):
            raise ValueError("all grid rows must have the same length")
        if len(self.row_targets) != len(self.grid):
            raise ValueError("there must be one target per row")
        if len(self.column_targets) != columns:
            raise ValueError("there must be one target per column")
        if any(value <= 0 for row in self.grid for value in row):
            raise ValueError("cell values must be positive")
        if any(target < 0 for target in self.row_targets + self.column_targets):
            raise ValueError("targets cannot be negative")
        for row, target in zip(self.grid, self.row_targets, strict=True):
            if target > sum(row):
                raise ValueError(f"row target {target} exceeds available sum {sum(row)}")
        for column, target in enumerate(self.column_targets):
            available = sum(row[column] for row in self.grid)
            if target > available:
                raise ValueError(
                    f"column target {target} exceeds available sum {available}"
                )

    @property
    def rows(self) -> int:
        return len(self.grid)

    @property
    def columns(self) -> int:
        return len(self.grid[0])

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Puzzle:
        return cls(
            grid=tuple(tuple(int(cell) for cell in row) for row in value["grid"]),
            row_targets=tuple(int(target) for target in value["row_targets"]),
            column_targets=tuple(int(target) for target in value["column_targets"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "grid": [list(row) for row in self.grid],
            "row_targets": list(self.row_targets),
            "column_targets": list(self.column_targets),
        }


@dataclass(frozen=True, slots=True)
class Solution:
    """Boolean selection mask returned by the backtracking solver."""

    selected: tuple[tuple[bool, ...], ...]

    def selected_cells(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (row, column)
            for row, values in enumerate(self.selected)
            for column, selected in enumerate(values)
            if selected
        )

    def rejected_cells(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (row, column)
            for row, values in enumerate(self.selected)
            for column, selected in enumerate(values)
            if not selected
        )

