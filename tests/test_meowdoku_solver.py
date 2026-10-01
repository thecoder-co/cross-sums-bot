from itertools import permutations

import pytest

from meowdoku.model import MeowdokuPuzzle, MeowdokuSolution
from meowdoku.solver import (
    MultipleSolutionsError,
    NoSolutionError,
    classify_cell,
    find_solutions,
    solve_unique,
    verify_solution,
)


LIVE_REGIONS = [
    ["M", "M", "M", "M", "M", "M", "M", "G"],
    ["M", "M", "M", "M", "M", "M", "B", "G"],
    ["Y", "M", "M", "M", "M", "M", "B", "G"],
    ["Y", "M", "C", "M", "M", "M", "B", "O"],
    ["Y", "M", "C", "M", "E", "M", "B", "O"],
    ["Y", "Y", "Y", "M", "E", "O", "O", "O"],
    ["Y", "Y", "P", "O", "O", "O", "O", "O"],
    ["Y", "P", "P", "O", "O", "O", "O", "O"],
]


def _brute_force(puzzle: MeowdokuPuzzle) -> set[tuple[tuple[int, int], ...]]:
    answers = set()
    for columns in permutations(range(puzzle.size)):
        cats = tuple(enumerate(columns))
        solution = MeowdokuSolution(cats)
        if verify_solution(puzzle, solution):
            answers.add(cats)
    return answers


def test_solves_live_eight_by_eight_board_uniquely() -> None:
    puzzle = MeowdokuPuzzle.from_dict({"regions": LIVE_REGIONS})
    solution = solve_unique(puzzle)
    assert solution.selected_cells() == (
        (0, 7),
        (1, 3),
        (2, 6),
        (3, 2),
        (4, 4),
        (5, 0),
        (6, 5),
        (7, 1),
    )
    assert verify_solution(puzzle, solution)
    assert {solution.selected_cells() for solution in find_solutions(puzzle)} == _brute_force(puzzle)


def test_preset_cat_is_retained() -> None:
    puzzle = MeowdokuPuzzle.from_dict(
        {"regions": LIVE_REGIONS, "cats": [[0, 7]]}
    )
    assert (0, 7) in solve_unique(puzzle).selected_cells()


def test_known_empty_is_enforced_and_cells_can_be_proved() -> None:
    puzzle = MeowdokuPuzzle.from_dict(
        {
            "regions": LIVE_REGIONS,
            "known_cats": [[0, 7]],
            "known_empty": [[0, 0], [1, 7]],
        }
    )
    assert classify_cell(puzzle, (0, 7)) == "must_be_cat"
    assert classify_cell(puzzle, (0, 0)) == "must_be_empty"
    assert classify_cell(puzzle, (1, 3)) == "must_be_cat"


def test_three_vertical_regions_have_no_solution() -> None:
    puzzle = MeowdokuPuzzle.from_dict(
        {"regions": [[0, 1, 2], [0, 1, 2], [0, 1, 2]]}
    )
    with pytest.raises(NoSolutionError):
        solve_unique(puzzle)


def test_four_vertical_regions_have_multiple_solutions() -> None:
    puzzle = MeowdokuPuzzle.from_dict(
        {"regions": [[0, 1, 2, 3] for _ in range(4)]}
    )
    with pytest.raises(MultipleSolutionsError):
        solve_unique(puzzle)


def test_rejects_disconnected_region() -> None:
    with pytest.raises(ValueError, match="not orthogonally connected"):
        MeowdokuPuzzle.from_dict(
            {
                "regions": [
                    [0, 1, 1],
                    [2, 1, 2],
                    [0, 2, 2],
                ]
            }
        )


def test_rejects_touching_preset_cats() -> None:
    with pytest.raises(ValueError, match="known cats violate"):
        MeowdokuPuzzle.from_dict(
            {
                "regions": [[0, 1, 2], [0, 1, 2], [0, 1, 2]],
                "cats": [[0, 0], [1, 1]],
            }
        )
