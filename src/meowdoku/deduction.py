"""Named, human-readable deductions backed by CP-SAT verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .model import Cell, MeowdokuPuzzle
from .solver import classify_cell


DeductionAction = Literal["place_cat", "mark_empty"]


@dataclass(frozen=True, slots=True)
class Deduction:
    action: DeductionAction
    cell: Cell
    rule: str
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "cell": [self.cell[0] + 1, self.cell[1] + 1],
            "rule": self.rule,
            "explanation": self.explanation,
        }


def _cell_name(cell: Cell) -> str:
    return f"row {cell[0] + 1}, column {cell[1] + 1}"


def candidate_cells(puzzle: MeowdokuPuzzle) -> set[Cell]:
    known_cats = set(puzzle.known_cats)
    candidates: set[Cell] = set()
    used_rows = {row for row, _ in known_cats}
    used_columns = {column for _, column in known_cats}
    used_regions = {
        puzzle.regions[row][column] for row, column in known_cats
    }
    for row in range(puzzle.size):
        for column in range(puzzle.size):
            cell = (row, column)
            if cell in known_cats:
                candidates.add(cell)
                continue
            if cell in puzzle.known_empty:
                continue
            if row in used_rows or column in used_columns:
                continue
            if puzzle.regions[row][column] in used_regions:
                continue
            if any(
                max(abs(row - cat_row), abs(column - cat_column)) <= 1
                for cat_row, cat_column in known_cats
            ):
                continue
            candidates.add(cell)
    return candidates


def _group_deductions(
    puzzle: MeowdokuPuzzle, candidates: set[Cell]
) -> list[Deduction]:
    deductions: list[Deduction] = []
    known_cats = set(puzzle.known_cats)
    groups: list[tuple[str, int, set[Cell]]] = []
    for row in range(puzzle.size):
        groups.append(("row", row, {(row, column) for column in range(puzzle.size)}))
    for column in range(puzzle.size):
        groups.append(("column", column, {(row, column) for row in range(puzzle.size)}))
    for region in range(puzzle.size):
        groups.append(
            (
                "region",
                region,
                {
                    (row, column)
                    for row in range(puzzle.size)
                    for column in range(puzzle.size)
                    if puzzle.regions[row][column] == region
                },
            )
        )
    for kind, index, cells in groups:
        if cells & known_cats:
            continue
        remaining = cells & candidates
        if len(remaining) == 1:
            cell = next(iter(remaining))
            deductions.append(
                Deduction(
                    "place_cat",
                    cell,
                    f"single_candidate_{kind}",
                    f"{kind.title()} {index + 1} has only one possible cell, {_cell_name(cell)}.",
                )
            )
    return deductions


def _line_region_deductions(
    puzzle: MeowdokuPuzzle, candidates: set[Cell]
) -> list[Deduction]:
    deductions: list[Deduction] = []
    known_cats = set(puzzle.known_cats)
    known_empty = set(puzzle.known_empty)
    for region in range(puzzle.size):
        region_cells = {
            (row, column)
            for row in range(puzzle.size)
            for column in range(puzzle.size)
            if puzzle.regions[row][column] == region
        }
        if region_cells & known_cats:
            continue
        remaining = region_cells & candidates
        rows = {row for row, _ in remaining}
        columns = {column for _, column in remaining}
        if remaining and len(rows) == 1:
            row = next(iter(rows))
            for column in range(puzzle.size):
                cell = (row, column)
                if cell not in region_cells and cell not in known_empty and cell not in known_cats:
                    deductions.append(
                        Deduction(
                            "mark_empty",
                            cell,
                            "region_confined_to_row",
                            f"Region {region + 1}'s cat must be in row {row + 1}, so {_cell_name(cell)} cannot contain another cat.",
                        )
                    )
        if remaining and len(columns) == 1:
            column = next(iter(columns))
            for row in range(puzzle.size):
                cell = (row, column)
                if cell not in region_cells and cell not in known_empty and cell not in known_cats:
                    deductions.append(
                        Deduction(
                            "mark_empty",
                            cell,
                            "region_confined_to_column",
                            f"Region {region + 1}'s cat must be in column {column + 1}, so {_cell_name(cell)} cannot contain another cat.",
                        )
                    )
    return deductions


def deductions(puzzle: MeowdokuPuzzle) -> tuple[Deduction, ...]:
    """Return named deductions, retaining only moves proved by CP-SAT."""

    candidates = candidate_cells(puzzle)
    proposed = [
        *_group_deductions(puzzle, candidates),
        *_line_region_deductions(puzzle, candidates),
    ]
    verified: list[Deduction] = []
    seen: set[tuple[DeductionAction, Cell]] = set()
    for deduction in proposed:
        key = (deduction.action, deduction.cell)
        if key in seen:
            continue
        classification = classify_cell(puzzle, deduction.cell)
        expected = (
            "must_be_cat" if deduction.action == "place_cat" else "must_be_empty"
        )
        if classification == expected:
            verified.append(deduction)
            seen.add(key)

    if verified:
        return tuple(verified)

    for row in range(puzzle.size):
        for column in range(puzzle.size):
            cell = (row, column)
            if cell in puzzle.known_cats or cell in puzzle.known_empty:
                continue
            classification = classify_cell(puzzle, cell)
            if classification in {"must_be_cat", "must_be_empty"}:
                action: DeductionAction = (
                    "place_cat" if classification == "must_be_cat" else "mark_empty"
                )
                return (
                    Deduction(
                        action,
                        cell,
                        "constraint_contradiction",
                        f"Assuming the opposite at {_cell_name(cell)} makes the Meowdoku constraints impossible.",
                    ),
                )
    return ()


def next_hint(puzzle: MeowdokuPuzzle) -> Deduction | None:
    available = deductions(puzzle)
    return available[0] if available else None
