from types import SimpleNamespace

import pytest

from cross_sums import computer_use
from cross_sums.computer_use import AutomationOptions
from cross_sums.geometry import BoardReadError
from cross_sums.native import NativeBridgeError


class FakeImage:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def convert(self, _mode):
        return self


def detected_board(puzzle):
    geometry = SimpleNamespace(
        pencil_center=lambda: (50, 130),
        cell_center=lambda row, column: (column * 10 + 5, row * 10 + 5),
    )
    return SimpleNamespace(
        puzzle=puzzle,
        geometry=geometry,
        image_width=100,
        image_height=150,
    )


def game_window():
    return SimpleNamespace(id=7, width=100, height=150, x=20, y=30, pid=99)


def fake_bridge(window):
    return SimpleNamespace(
        find_window=lambda _query: window,
        capture_window=lambda *_args: None,
        activate=lambda _pid: None,
        click=lambda *_point: None,
    )


def test_default_wait_allows_game_cleanup_animation() -> None:
    assert AutomationOptions().wait_seconds == 15.0


def test_transient_window_capture_is_retried(monkeypatch, tmp_path):
    window = game_window()
    attempts = []

    def capture(_window, _path):
        attempts.append(1)
        if len(attempts) < 3:
            raise NativeBridgeError("window server is busy")

    bridge = SimpleNamespace(
        find_window=lambda _query: window,
        capture_window=capture,
    )
    sleeps = []
    monkeypatch.setattr(computer_use.time, "sleep", sleeps.append)

    result = computer_use._capture_window(
        bridge, AutomationOptions(), tmp_path / "capture.png"
    )

    assert result is window
    assert len(attempts) == 3
    assert sleeps == [0.5, 0.5]


def test_transition_and_unchanged_board_are_retried_without_clicks(
    monkeypatch, tmp_path
):
    old, new = object(), object()
    events = iter(
        [
            BoardReadError("animation"),
            SimpleNamespace(puzzle=old),
            SimpleNamespace(puzzle=new),
        ]
    )
    captures, sleeps = [], []

    def read(*_):
        event = next(events)
        if isinstance(event, Exception):
            raise event
        return event

    bridge = SimpleNamespace(
        find_window=lambda _: "window",
        capture_window=lambda *args: captures.append(args),
    )
    monkeypatch.setattr(computer_use, "read_screenshot", read)
    monkeypatch.setattr(computer_use.time, "sleep", sleeps.append)
    window, result = computer_use._read_next_board(
        bridge, AutomationOptions(), tmp_path / "capture.png", old
    )
    assert result.puzzle is new
    assert len(captures) == 3
    assert sleeps == [15, 15]


def test_nonadvancing_board_stops_after_bounded_retries(monkeypatch, tmp_path):
    old = object()
    bridge = SimpleNamespace(
        find_window=lambda _: "window", capture_window=lambda *_: None
    )
    monkeypatch.setattr(
        computer_use, "read_screenshot", lambda *_: SimpleNamespace(puzzle=old)
    )
    monkeypatch.setattr(computer_use.time, "sleep", lambda _: None)
    with pytest.raises(BoardReadError, match="not advanced"):
        computer_use._read_next_board(
            bridge, AutomationOptions(), tmp_path / "capture.png", old
        )


def test_mark_verification_retries_only_missing_cells(monkeypatch):
    puzzle = object()
    detected = detected_board(puzzle)
    solution = SimpleNamespace(selected_cells=lambda: ((0, 0), (1, 2), (3, 4)))
    window = game_window()
    observed_marks = iter(
        [
            {(0, 0), (3, 4)},
            {(0, 0), (1, 2), (3, 4)},
        ]
    )
    retried = []

    monkeypatch.setattr(computer_use.Image, "open", lambda _path: FakeImage())
    monkeypatch.setattr(
        computer_use,
        "recognize_puzzle",
        lambda *_args, **_kwargs: puzzle,
    )
    monkeypatch.setattr(
        computer_use, "marked_cells", lambda *_args: next(observed_marks)
    )
    monkeypatch.setattr(computer_use.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        computer_use,
        "_click_cells",
        lambda _bridge, _window, _detected, cells, **_kwargs: retried.append(cells),
    )

    computer_use._verify_marks(
        fake_bridge(window), window, detected, solution, AutomationOptions()
    )

    assert retried == [((1, 2),)]


def test_mark_verification_stops_on_unexpected_circle(monkeypatch):
    puzzle = object()
    detected = detected_board(puzzle)
    solution = SimpleNamespace(selected_cells=lambda: ((0, 0),))
    window = game_window()

    monkeypatch.setattr(computer_use.Image, "open", lambda _path: FakeImage())
    monkeypatch.setattr(
        computer_use,
        "recognize_puzzle",
        lambda *_args, **_kwargs: puzzle,
    )
    monkeypatch.setattr(
        computer_use, "marked_cells", lambda *_args: {(0, 0), (2, 2)}
    )

    with pytest.raises(RuntimeError, match="Unexpected circles"):
        computer_use._verify_marks(
            fake_bridge(window), window, detected, solution, AutomationOptions()
        )
