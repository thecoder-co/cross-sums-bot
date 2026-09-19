from cross_sums.model import Puzzle, Solution
from cross_sums.solver import (
    MultipleSolutionsError,
    NoSolutionError,
    find_solutions,
    solve_unique,
    verify_solution,
)


LEVEL_2 = Puzzle(
    grid=(
        (1, 8, 2, 8, 9, 9, 3),
        (1, 7, 6, 1, 8, 8, 5),
        (8, 3, 5, 2, 9, 8, 9),
        (2, 5, 8, 5, 4, 8, 8),
        (4, 8, 6, 1, 3, 4, 1),
        (8, 1, 1, 4, 4, 1, 5),
        (2, 2, 1, 7, 8, 8, 2),
    ),
    row_targets=(22, 6, 10, 17, 23, 6, 21),
    column_targets=(11, 19, 17, 17, 15, 12, 14),
)


def test_solves_reference_level() -> None:
    solution = solve_unique(LEVEL_2)
    assert verify_solution(LEVEL_2, solution)
    assert solution.selected == (
        (True, True, True, True, False, False, True),
        (False, False, False, True, False, False, True),
        (True, False, False, True, False, False, False),
        (False, False, True, True, True, False, False),
        (False, True, True, True, True, True, True),
        (False, True, False, False, False, False, True),
        (True, True, True, False, True, True, False),
    )


def test_finds_no_solution() -> None:
    puzzle = Puzzle(grid=((1,),), row_targets=(0,), column_targets=(1,))
    assert find_solutions(puzzle) == []
    try:
        solve_unique(puzzle)
    except NoSolutionError:
        pass
    else:
        raise AssertionError("expected NoSolutionError")


def test_rejects_multiple_solutions() -> None:
    puzzle = Puzzle(
        grid=((1, 1), (1, 1)), row_targets=(1, 1), column_targets=(1, 1)
    )
    try:
        solve_unique(puzzle)
    except MultipleSolutionsError:
        pass
    else:
        raise AssertionError("expected MultipleSolutionsError")


def test_verify_rejects_wrong_shape() -> None:
    assert not verify_solution(LEVEL_2, Solution(((True,),)))

