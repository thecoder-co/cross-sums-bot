from __future__ import annotations

from .model import Puzzle, Solution


class NoSolutionError(ValueError):
    """Raised when the board constraints cannot be satisfied."""


class MultipleSolutionsError(ValueError):
    """Raised when the puzzle does not have the promised unique solution."""


def _row_choices(row: tuple[int, ...], target: int) -> tuple[int, ...]:
    """Return bit masks for all subsets of ``row`` that total ``target``.

    This is itself a small backtracking search. Suffix sums make it stop as soon
    as the remaining values can no longer reach the target.
    """

    suffix = [0] * (len(row) + 1)
    for index in range(len(row) - 1, -1, -1):
        suffix[index] = suffix[index + 1] + row[index]

    choices: list[int] = []

    def visit(index: int, subtotal: int, mask: int) -> None:
        if subtotal > target or subtotal + suffix[index] < target:
            return
        if index == len(row):
            if subtotal == target:
                choices.append(mask)
            return

        # Try retaining the value first. This mirrors the visible circled-cell
        # representation and often finds the unique solution sooner.
        visit(index + 1, subtotal + row[index], mask | (1 << index))
        visit(index + 1, subtotal, mask)

    visit(0, 0, 0)
    return tuple(choices)


def find_solutions(puzzle: Puzzle, *, limit: int = 2) -> list[Solution]:
    """Find up to ``limit`` solutions using row choices and column pruning."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    choices = [
        _row_choices(row, target)
        for row, target in zip(puzzle.grid, puzzle.row_targets, strict=True)
    ]
    if any(not row_choices for row_choices in choices):
        return []

    # The maximum value still available in each column after each row is used
    # to reject a branch that can no longer reach a column target.
    suffix_available = [[0] * puzzle.columns for _ in range(puzzle.rows + 1)]
    for row_index in range(puzzle.rows - 1, -1, -1):
        for column in range(puzzle.columns):
            suffix_available[row_index][column] = (
                suffix_available[row_index + 1][column]
                + puzzle.grid[row_index][column]
            )

    results: list[Solution] = []
    masks = [0] * puzzle.rows
    column_sums = [0] * puzzle.columns

    # Cache dead states. Different row masks can converge to the same column
    # totals, after which their remaining search is identical.
    dead: set[tuple[int, tuple[int, ...]]] = set()

    def search(row_index: int) -> bool:
        state = (row_index, tuple(column_sums))
        if state in dead:
            return False
        result_count_before = len(results)

        if row_index == puzzle.rows:
            if tuple(column_sums) == puzzle.column_targets:
                results.append(
                    Solution(
                        tuple(
                            tuple(bool(mask & (1 << column)) for column in range(puzzle.columns))
                            for mask in masks
                        )
                    )
                )
            return len(results) >= limit

        row = puzzle.grid[row_index]
        for mask in choices[row_index]:
            added: list[tuple[int, int]] = []
            valid = True
            for column, value in enumerate(row):
                if mask & (1 << column):
                    column_sums[column] += value
                    added.append((column, value))

                target = puzzle.column_targets[column]
                if column_sums[column] > target:
                    valid = False
                elif (
                    column_sums[column] + suffix_available[row_index + 1][column]
                    < target
                ):
                    valid = False

            if valid:
                masks[row_index] = mask
                if search(row_index + 1):
                    return True

            for column, value in added:
                column_sums[column] -= value

        if len(results) == result_count_before:
            dead.add(state)
        return False

    search(0)
    return results


def solve_unique(puzzle: Puzzle) -> Solution:
    """Solve ``puzzle`` and verify the game's unique-solution promise."""

    solutions = find_solutions(puzzle, limit=2)
    if not solutions:
        raise NoSolutionError("the puzzle has no solution")
    if len(solutions) > 1:
        raise MultipleSolutionsError("the puzzle has more than one solution")
    return solutions[0]


def verify_solution(puzzle: Puzzle, solution: Solution) -> bool:
    if len(solution.selected) != puzzle.rows:
        return False
    if any(len(row) != puzzle.columns for row in solution.selected):
        return False

    row_sums = tuple(
        sum(value for value, selected in zip(row, mask, strict=True) if selected)
        for row, mask in zip(puzzle.grid, solution.selected, strict=True)
    )
    column_sums = tuple(
        sum(
            puzzle.grid[row][column]
            for row in range(puzzle.rows)
            if solution.selected[row][column]
        )
        for column in range(puzzle.columns)
    )
    return row_sums == puzzle.row_targets and column_sums == puzzle.column_targets
