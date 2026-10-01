"""OR-Tools CP-SAT model for Meowdoku constraints and proof queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ortools.sat.python import cp_model

from .model import Cell, MeowdokuPuzzle, MeowdokuSolution, _cats_are_legal


class NoSolutionError(ValueError):
    pass


class MultipleSolutionsError(ValueError):
    pass


CellClassification = Literal[
    "must_be_cat",
    "must_be_empty",
    "undetermined",
    "current_board_is_contradictory",
]


@dataclass(slots=True)
class ConstraintModel:
    model: cp_model.CpModel
    cells: tuple[tuple[cp_model.IntVar, ...], ...]


def build_model(
    puzzle: MeowdokuPuzzle,
    *,
    assume_cats: tuple[Cell, ...] = (),
    assume_empty: tuple[Cell, ...] = (),
) -> ConstraintModel:
    """Translate all board rules and current marks into a CP-SAT model."""

    model = cp_model.CpModel()
    cells = tuple(
        tuple(
            model.new_bool_var(f"cat_{row}_{column}")
            for column in range(puzzle.size)
        )
        for row in range(puzzle.size)
    )

    for row in cells:
        model.add_exactly_one(row)
    for column in range(puzzle.size):
        model.add_exactly_one(cells[row][column] for row in range(puzzle.size))
    for region in range(puzzle.size):
        model.add_exactly_one(
            cells[row][column]
            for row in range(puzzle.size)
            for column in range(puzzle.size)
            if puzzle.regions[row][column] == region
        )

    # Row and column constraints already prevent orthogonal contact. These
    # constraints add the two downward diagonals exactly once per pair.
    for row in range(puzzle.size - 1):
        for column in range(puzzle.size):
            for other_column in (column - 1, column + 1):
                if 0 <= other_column < puzzle.size:
                    model.add(
                        cells[row][column] + cells[row + 1][other_column] <= 1
                    )

    for row, column in (*puzzle.known_cats, *assume_cats):
        model.add(cells[row][column] == 1)
    for row, column in (*puzzle.known_empty, *assume_empty):
        model.add(cells[row][column] == 0)
    return ConstraintModel(model, cells)


class _SolutionCollector(cp_model.CpSolverSolutionCallback):
    def __init__(
        self,
        cells: tuple[tuple[cp_model.IntVar, ...], ...],
        limit: int | None,
    ) -> None:
        super().__init__()
        self.cells = cells
        self.limit = limit
        self.solutions: list[MeowdokuSolution] = []

    def on_solution_callback(self) -> None:
        cats = tuple(
            (row, column)
            for row, values in enumerate(self.cells)
            for column, cell in enumerate(values)
            if self.value(cell)
        )
        self.solutions.append(MeowdokuSolution(cats))
        if self.limit is not None and len(self.solutions) >= self.limit:
            self.stop_search()


def find_solutions(
    puzzle: MeowdokuPuzzle, *, limit: int | None = None
) -> tuple[MeowdokuSolution, ...]:
    if limit is not None and limit < 1:
        raise ValueError("solution limit must be at least one")
    constraint_model = build_model(puzzle)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    collector = _SolutionCollector(constraint_model.cells, limit)
    solver.SearchForAllSolutions(constraint_model.model, collector)
    return tuple(collector.solutions)


def has_solution(
    puzzle: MeowdokuPuzzle,
    *,
    assume_cats: tuple[Cell, ...] = (),
    assume_empty: tuple[Cell, ...] = (),
) -> bool:
    constraint_model = build_model(
        puzzle,
        assume_cats=assume_cats,
        assume_empty=assume_empty,
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    return solver.solve(constraint_model.model) in (
        cp_model.FEASIBLE,
        cp_model.OPTIMAL,
    )


def classify_cell(puzzle: MeowdokuPuzzle, target: Cell) -> CellClassification:
    row, column = target
    if not (0 <= row < puzzle.size and 0 <= column < puzzle.size):
        raise ValueError("target cell is outside the board")
    if target in puzzle.known_cats:
        return "must_be_cat"
    if target in puzzle.known_empty:
        return "must_be_empty"

    possible_with_cat = has_solution(puzzle, assume_cats=(target,))
    possible_without_cat = has_solution(puzzle, assume_empty=(target,))
    if possible_with_cat and not possible_without_cat:
        return "must_be_cat"
    if not possible_with_cat and possible_without_cat:
        return "must_be_empty"
    if possible_with_cat and possible_without_cat:
        return "undetermined"
    return "current_board_is_contradictory"


def solve_unique(puzzle: MeowdokuPuzzle) -> MeowdokuSolution:
    solutions = find_solutions(puzzle, limit=2)
    if not solutions:
        raise NoSolutionError("Meowdoku board has no solution")
    if len(solutions) > 1:
        raise MultipleSolutionsError("Meowdoku board has multiple solutions")
    return solutions[0]


def verify_solution(puzzle: MeowdokuPuzzle, solution: MeowdokuSolution) -> bool:
    cats = solution.selected_cells()
    if len(cats) != puzzle.size or len(set(cats)) != puzzle.size:
        return False
    if any(
        not (0 <= row < puzzle.size and 0 <= column < puzzle.size)
        for row, column in cats
    ):
        return False
    if not set(puzzle.known_cats).issubset(cats):
        return False
    if set(puzzle.known_empty) & set(cats):
        return False
    if not _cats_are_legal(puzzle.regions, cats):
        return False
    return {puzzle.regions[row][column] for row, column in cats} == set(
        range(puzzle.size)
    )
