from types import SimpleNamespace

import pytest

from meowdoku import automation
from meowdoku.automation import AutomationOptions, _long_press, _screen_cell, apply_solution
from meowdoku.cli import _options, build_parser
from meowdoku.geometry import GridGeometry
from meowdoku.model import MeowdokuPuzzle, MeowdokuSolution
from meowdoku.vision import DetectedMeowdoku
from puzzle_automation import AndroidTarget, Window


def detected() -> DetectedMeowdoku:
    puzzle = MeowdokuPuzzle.from_dict(
        {"regions": [[0, 1, 2], [0, 1, 2], [0, 1, 2]]}
    )
    return DetectedMeowdoku(
        puzzle=puzzle,
        geometry=GridGeometry(30, 60, 100, 100, 3),
        image_width=360,
        image_height=480,
        fingerprint=puzzle.regions,
    )


def test_android_cell_coordinates_do_not_add_a_desktop_origin() -> None:
    target = AndroidTarget("phone", 720, 960, "phone")
    assert _screen_cell(detected(), target, (1, 2)) == (560, 420)


def test_macos_cell_coordinates_include_the_window_origin() -> None:
    target = Window(1, "Offline Games", "Offline Games", 9, 100, 200, 720, 960)
    assert _screen_cell(detected(), target, (1, 2)) == (660, 620)


def test_cat_input_uses_one_long_press() -> None:
    presses = []
    bridge = type(
        "Bridge",
        (),
        {
            "long_press": lambda self, *point, duration_ms: presses.append(
                (point, duration_ms)
            )
        },
    )()
    options = AutomationOptions()
    _long_press(bridge, (12.5, 24.5), options.press_duration)
    assert presses == [((12.5, 24.5), 1500)]


def test_cli_can_override_long_press_duration() -> None:
    arguments = build_parser().parse_args(["play", "--press-duration", "2.25"])
    assert _options(arguments).press_duration == 2.25


def test_transient_cat_does_not_authorize_another_click(monkeypatch) -> None:
    initial = detected()
    marked_puzzle = MeowdokuPuzzle(
        initial.puzzle.regions,
        known_cats=((0, 2),),
    )
    marked = DetectedMeowdoku(
        marked_puzzle,
        initial.geometry,
        initial.image_width,
        initial.image_height,
        initial.fingerprint,
    )
    target = Window(1, "Offline Games", "Offline Games", 9, 100, 200, 720, 960)
    presses = []
    bridge = SimpleNamespace(
        activate=lambda _pid: None,
        long_press=lambda *point, duration_ms: presses.append((point, duration_ms)),
    )
    monkeypatch.setattr(
        automation,
        "_validated_current_board",
        lambda *_args: (target, initial),
    )
    monkeypatch.setattr(automation, "_capture", lambda *_args: target)
    observed = iter((marked, initial))
    monkeypatch.setattr(automation, "read_screenshot", lambda _path: next(observed))
    monkeypatch.setattr(automation.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="did not persist"):
        apply_solution(
            bridge,
            target,
            initial,
            MeowdokuSolution(((0, 2),)),
            AutomationOptions(verify_wait=0, stability_wait=0),
        )
    assert presses == [((660, 420), 1500)]
