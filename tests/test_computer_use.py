from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from cross_sums.adb import AndroidTarget
from cross_sums import computer_use
from cross_sums.computer_use import AutomationOptions
from cross_sums.geometry import BoardGeometry, BoardReadError
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


def test_screen_point_maps_android_coordinates_without_desktop_origin():
    detected = detected_board(object())
    target = AndroidTarget("phone", 100, 150, "phone")

    assert computer_use._screen_point(detected, target, (12, 34)) == (12, 34)


def android_tool_fixture(selected="eraser"):
    image = Image.new("RGB", (400, 600), (16, 16, 25))
    geometry = BoardGeometry(100, 50, 40, 40, 5, 5)
    draw = ImageDraw.Draw(image)
    y = 480
    for name, x in (("eraser", 158), ("pencil", 200)):
        fill = (66, 65, 82) if name == selected else (25, 24, 33)
        draw.ellipse((x - 32, y - 32, x + 32, y + 32), fill=fill, outline=(0, 0, 0), width=4)
    return image, geometry


def test_android_tool_is_located_from_visible_controls():
    image, geometry = android_tool_fixture()

    point = computer_use._android_tool_point(image, geometry, "pencil")

    assert point == pytest.approx((200, 480), abs=2)
    assert computer_use._android_selected_tool(image, geometry) == "eraser"


def test_android_tool_selection_is_verified_before_return(monkeypatch, tmp_path):
    image, geometry = android_tool_fixture()
    target = AndroidTarget("phone", 400, 600, "phone")
    detected = SimpleNamespace(geometry=geometry, image_width=400, image_height=600)
    clicks = []
    state = {"selected": "eraser"}

    def capture(_target, destination):
        current, _ = android_tool_fixture(state["selected"])
        current.save(destination)

    def click(x, y):
        clicks.append((x, y))
        state["selected"] = "pencil"

    bridge = SimpleNamespace(capture_window=capture, click=click)
    monkeypatch.setattr(computer_use.time, "sleep", lambda _seconds: None)

    computer_use._select_tool(
        bridge,
        target,
        detected,
        "pencil",
        settle_seconds=0,
    )

    assert clicks == [pytest.approx((200, 480), abs=2)]


def test_android_aborts_before_cells_if_tool_stays_wrong(monkeypatch, tmp_path):
    image, geometry = android_tool_fixture()
    target = AndroidTarget("phone", 400, 600, "phone")
    detected = SimpleNamespace(geometry=geometry, image_width=400, image_height=600)
    clicks = []

    def capture(_target, destination):
        image.save(destination)

    bridge = SimpleNamespace(
        activate=lambda _pid: None,
        capture_window=capture,
        click=lambda x, y: clicks.append((x, y)),
    )
    monkeypatch.setattr(computer_use.time, "sleep", lambda _seconds: None)
    solution = SimpleNamespace(selected_cells=lambda: ((0, 0),))

    with pytest.raises(RuntimeError, match="did not select the pencil"):
        computer_use.apply_solution(
            bridge,
            target,
            detected,
            solution,
            mode="keep-only",
            click_pause=0,
        )

    assert len(clicks) == 2
    assert all(y > 400 for _x, y in clicks)


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
