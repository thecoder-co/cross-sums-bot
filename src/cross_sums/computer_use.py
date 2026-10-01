from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from PIL import Image

from .adb import ADBBridge, AndroidTarget
from .model import Solution
from .native import MacOSBridge, NativeBridgeError, Window, temporary_png
from .solver import solve_unique, verify_solution
from .template_ocr import marked_cells, recognize_puzzle
from .vision import BoardReadError, DetectedPuzzle, read_screenshot


@dataclass(frozen=True, slots=True)
class AutomationOptions:
    window_query: str = "Offline Games"
    wait_seconds: float = 15.0
    click_pause: float = 0.005
    mode: str = "keep-only"
    dry_run: bool = False
    max_levels: int | None = None
    debug_directory: Path | None = None


def _screen_point(
    detected: DetectedPuzzle,
    window: Window,
    point: tuple[float, float],
) -> tuple[float, float]:
    """Convert a screenshot point into the active bridge's input coordinates."""

    scale_x = window.width / detected.image_width
    scale_y = window.height / detected.image_height
    if isinstance(window, AndroidTarget):
        # Android's input tap coordinates start at the full-screen origin; the
        # screenshot and target dimensions are kept in the same pixel space by
        # ADBBridge.capture_window.
        return point[0] * scale_x, point[1] * scale_y
    return window.x + point[0] * scale_x, window.y + point[1] * scale_y


def _android_tool_y(image: Image.Image, geometry) -> float:
    """Find the Android tool-toggle row from its dark control backgrounds."""

    pencil_x = geometry.pencil_center()[0]
    eraser_x = geometry.eraser_center()[0]
    padding = geometry.cell_width * 0.9
    x_start = max(0, round(min(pencil_x, eraser_x) - padding))
    x_end = min(image.width, round(max(pencil_x, eraser_x) + padding))
    y_start = max(0, round(geometry.bottom + geometry.cell_height * 0.2))
    y_end = min(
        image.height,
        round(image.height - geometry.cell_height * 0.2),
    )
    if x_start >= x_end or y_start >= y_end:
        raise RuntimeError("Could not search for the Android tool toggle")

    pixels = image.load()
    scores: list[tuple[int, int]] = []
    for y in range(y_start, y_end):
        score = 0
        for x in range(x_start, x_end):
            red, green, blue = pixels[x, y]
            luminance = (red + green + blue) / 3
            # Offline Games' selected and unselected controls are both neutral
            # dark fills; the surrounding background is darker than this band.
            if (
                20 <= luminance <= 105
                and max(red, green, blue) - min(red, green, blue) <= 35
            ):
                score += 1
        scores.append((score, y))

    best = max(score for score, _ in scores)
    if best < 20:
        raise RuntimeError("Could not locate the Android tool toggle")
    active_rows = [y for score, y in scores if score >= best * 0.85]
    return float(median(active_rows))


def _android_tool_point(
    image: Image.Image,
    geometry,
    tool: str,
) -> tuple[float, float]:
    if tool == "pencil":
        x = geometry.pencil_center()[0]
    elif tool == "eraser":
        x = geometry.eraser_center()[0]
    else:
        raise ValueError(f"unsupported Android tool: {tool}")
    return x, _android_tool_y(image, geometry)


def _android_tool_luminance(
    image: Image.Image,
    center: tuple[float, float],
    radius: float,
) -> float:
    pixels = image.load()
    x_center, y_center = center
    inner = radius * 0.42
    outer = radius * 0.65
    values: list[float] = []
    for y in range(
        max(0, round(y_center - outer)),
        min(image.height, round(y_center + outer + 1)),
    ):
        for x in range(
            max(0, round(x_center - outer)),
            min(image.width, round(x_center + outer + 1)),
        ):
            distance = ((x - x_center) ** 2 + (y - y_center) ** 2) ** 0.5
            if inner <= distance <= outer:
                red, green, blue = pixels[x, y]
                values.append((red + green + blue) / 3)
    if not values:
        raise RuntimeError("Could not sample the Android tool toggle")
    return sum(values) / len(values)


def _android_selected_tool(image: Image.Image, geometry) -> str:
    y = _android_tool_y(image, geometry)
    radius = geometry.cell_width
    eraser = _android_tool_luminance(
        image, (geometry.eraser_center()[0], y), radius
    )
    pencil = _android_tool_luminance(
        image, (geometry.pencil_center()[0], y), radius
    )
    if abs(eraser - pencil) < 8:
        raise RuntimeError("Could not verify which Android tool is selected")
    return "eraser" if eraser > pencil else "pencil"


def _select_tool(
    bridge,
    window,
    detected: DetectedPuzzle,
    tool: str,
    *,
    settle_seconds: float,
) -> None:
    """Select a tool and verify it visually before any cell clicks."""

    if tool not in {"pencil", "eraser"}:
        raise ValueError(f"unsupported tool: {tool}")

    if not isinstance(window, AndroidTarget):
        point = (
            detected.geometry.pencil_center()
            if tool == "pencil"
            else detected.geometry.eraser_center()
        )
        bridge.click(*_screen_point(detected, window, point))
        time.sleep(settle_seconds)
        return

    screenshot = temporary_png()
    try:
        for attempt in range(3):
            bridge.capture_window(window, screenshot)
            with Image.open(screenshot) as source:
                image = source.convert("RGB")
            if _android_selected_tool(image, detected.geometry) == tool:
                return
            if attempt == 2:
                raise RuntimeError(
                    f"Android did not select the {tool} tool after two retries"
                )
            bridge.click(
                *_screen_point(
                    detected,
                    window,
                    _android_tool_point(image, detected.geometry, tool),
                )
            )
            time.sleep(settle_seconds)
    finally:
        screenshot.unlink(missing_ok=True)


def _click_cells(
    bridge: MacOSBridge,
    window: Window,
    detected: DetectedPuzzle,
    cells: tuple[tuple[int, int], ...],
    *,
    pause: float,
) -> None:
    for row, column in cells:
        bridge.click(
            *_screen_point(detected, window, detected.geometry.cell_center(row, column))
        )
        time.sleep(pause)


def _capture_window(
    bridge: MacOSBridge,
    options: AutomationOptions,
    destination: Path,
) -> Window:
    """Capture the game, tolerating brief macOS window-server failures."""

    last_error: NativeBridgeError | None = None
    for attempt in range(3):
        window = bridge.find_window(options.window_query)
        try:
            bridge.capture_window(window, destination)
            return window
        except NativeBridgeError as error:
            last_error = error
            if attempt == 2:
                break
            print(
                f"Window capture failed temporarily; retrying ({attempt + 1}/2).",
                flush=True,
            )
            time.sleep(0.5)
    assert last_error is not None
    raise last_error


def apply_solution(
    bridge: MacOSBridge,
    window: Window,
    detected: DetectedPuzzle,
    solution: Solution,
    *,
    mode: str,
    click_pause: float,
) -> None:
    """Mark a verified solution in the game window."""

    if mode not in {"keep-only", "keep-and-erase"}:
        raise ValueError(f"unsupported click mode: {mode}")

    # Mouse events target the foreground app. Activating by PID prevents an
    # overlapping terminal window from receiving the solution clicks.
    bridge.activate(window.pid)
    time.sleep(0.35)

    _select_tool(
        bridge,
        window,
        detected,
        "pencil",
        settle_seconds=max(0.12, click_pause * 2),
    )
    _click_cells(
        bridge,
        window,
        detected,
        solution.selected_cells(),
        pause=click_pause,
    )

    if mode == "keep-and-erase":
        _select_tool(
            bridge,
            window,
            detected,
            "eraser",
            settle_seconds=max(0.12, click_pause * 2),
        )
        _click_cells(
            bridge,
            window,
            detected,
            solution.rejected_cells(),
            pause=click_pause,
        )


def _verify_marks(
    bridge: MacOSBridge,
    window: Window,
    detected: DetectedPuzzle,
    solution: Solution,
    options: AutomationOptions,
) -> None:
    """Retry dropped input only after verifying every digit and target is unchanged."""

    path = temporary_png()
    try:
        for attempt in range(3):
            current = _capture_window(bridge, options, path)
            if (current.id, current.width, current.height) != (
                window.id,
                window.width,
                window.height,
            ):
                raise RuntimeError("Game window changed while marking; stopped.")
            with Image.open(path) as source:
                image = source.convert("RGB")
            try:
                puzzle = recognize_puzzle(
                    image, detected.geometry, allow_marked=True
                )
            except BoardReadError:
                # Successful completion removes digits/targets. There is no
                # longer a complete board to retry; the next read verifies progress.
                return
            if puzzle != detected.puzzle:
                return
            marked = marked_cells(image,detected.geometry)
            expected = set(solution.selected_cells())
            if marked - expected:
                raise RuntimeError("Unexpected circles appeared; stopped.")
            missing = expected - marked
            if not missing:
                return
            if attempt == 2:
                raise RuntimeError("Some clicks did not register after two retries.")
            print(
                f"Retrying {len(missing)} unregistered marks on the verified board.",
                flush=True,
            )
            bridge.activate(current.pid)
            _select_tool(
                bridge,
                current,
                detected,
                "pencil",
                settle_seconds=max(0.12, options.click_pause * 2),
            )
            _click_cells(
                bridge,
                current,
                detected,
                tuple(sorted(missing)),
                pause=max(0.1, options.click_pause),
            )
    finally:
        path.unlink(missing_ok=True)


def _save_debug(
    directory: Path,
    level: int,
    screenshot: Path,
    detected: DetectedPuzzle,
    solution: Solution,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    image_destination = directory / f"level-{level:03d}.png"
    image_destination.write_bytes(screenshot.read_bytes())
    record = {
        **detected.puzzle.to_dict(),
        "selected": [list(row) for row in solution.selected],
        "geometry": {
            "left": detected.geometry.left,
            "top": detected.geometry.top,
            "cell_width": detected.geometry.cell_width,
            "cell_height": detected.geometry.cell_height,
        },
    }
    (directory / f"level-{level:03d}.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )


def _read_next_board(bridge, options, screenshot, last_puzzle):
    # The game can still be clearing cells after the requested 15-second wait.
    # Retry reads only, never replay solution clicks into the completed board.
    for attempt in range(4):
        window = _capture_window(bridge, options, screenshot)
        try:
            detected = read_screenshot(bridge, screenshot)
            if detected.puzzle == last_puzzle:
                raise BoardReadError("The previous board has not advanced yet.")
            return window, detected
        except BoardReadError:
            if last_puzzle is None or attempt == 3:
                raise
            print(
                f"Next board is not ready; waiting another {options.wait_seconds:g}s "
                f"({attempt + 1}/3).",
                flush=True,
            )
            time.sleep(options.wait_seconds)
    raise AssertionError("unreachable")


def run(options: AutomationOptions) -> None:
    _run_loop(options, MacOSBridge())


def run_android(
    options: AutomationOptions,
    *,
    device_serial: str | None = None,
    adb_path: str | Path | None = None,
    package_name: str = "com.JindoBlu.OfflineGames",
) -> None:
    """Solve boards on a connected Android device through ADB."""

    _run_loop(
        options,
        ADBBridge(
            serial=device_serial,
            executable=adb_path,
            package_name=package_name,
        ),
    )


def _run_loop(options: AutomationOptions, bridge) -> None:
    if options.wait_seconds < 0 or options.click_pause < 0:
        raise ValueError("wait and click-pause must not be negative")
    if options.max_levels is not None and options.max_levels < 1:
        raise ValueError("max-levels must be at least 1")
    print("cross-sums 0.2.0: fixed-glyph reader (no Vision OCR)", flush=True)
    level = 0
    last_puzzle = None
    while options.max_levels is None or level < options.max_levels:
        screenshot = temporary_png()
        try:
            window, detected = _read_next_board(bridge, options, screenshot, last_puzzle)
            solution = solve_unique(detected.puzzle)
            if not verify_solution(detected.puzzle, solution):
                raise RuntimeError("internal check rejected the solver result")

            level += 1
            print(
                f"Board {level}: {detected.puzzle.rows}x{detected.puzzle.columns}, "
                f"{len(solution.selected_cells())} cells retained", flush=True
            )
            if options.debug_directory:
                _save_debug(
                    options.debug_directory, level, screenshot, detected, solution
                )
            if options.dry_run:
                print("Dry run: no clicks sent.")
                return

            apply_solution(
                bridge,
                window,
                detected,
                solution,
                mode=options.mode,
                click_pause=options.click_pause,
            )
            _verify_marks(bridge, window, detected, solution, options)
            last_puzzle = detected.puzzle
            print(f"Waiting {options.wait_seconds:g}s for the next board (Ctrl-C to stop)...", flush=True)
            time.sleep(options.wait_seconds)
        except (ValueError, RuntimeError) as error:
            if screenshot.exists():
                directory = options.debug_directory or Path("work/debug")
                directory.mkdir(parents=True, exist_ok=True)
                failure = directory / "failed-board.png"
                shutil.copyfile(screenshot, failure)
                raise RuntimeError(f'{error} Screenshot saved to {failure.resolve()}') from error
            raise
        finally:
            screenshot.unlink(missing_ok=True)
