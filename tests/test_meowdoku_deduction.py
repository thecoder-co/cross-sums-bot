from meowdoku.deduction import deductions, next_hint
from meowdoku.model import MeowdokuPuzzle
from meowdoku.solver import classify_cell

from test_meowdoku_solver import LIVE_REGIONS


def test_region_confined_to_column_produces_a_verified_explanation() -> None:
    puzzle = MeowdokuPuzzle.from_dict({"regions": LIVE_REGIONS})
    hints = deductions(puzzle)
    hint = next(
        item for item in hints if item.rule == "region_confined_to_column"
    )
    assert hint.action == "mark_empty"
    assert hint.cell[1] == 7
    assert classify_cell(puzzle, hint.cell) == "must_be_empty"
    assert "column 8" in hint.explanation


def test_next_hint_returns_a_cp_sat_proved_move() -> None:
    puzzle = MeowdokuPuzzle.from_dict(
        {
            "regions": LIVE_REGIONS,
            "known_cats": [[0, 7]],
            "known_empty": [[0, column] for column in range(7)],
        }
    )
    hint = next_hint(puzzle)
    assert hint is not None
    expected = "must_be_cat" if hint.action == "place_cat" else "must_be_empty"
    assert classify_cell(puzzle, hint.cell) == expected
