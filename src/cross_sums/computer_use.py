from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .model import Solution
from .native import MacOSBridge, NativeBridgeError, Window, temporary_png
from .solver import solve_unique, verify_solution
from .template_ocr import marked_cells, recognize_puzzle
from .vision import BoardReadError, DetectedPuzzle, read_screenshot


@dataclass(frozen=True, slots=True)
class AutomationOptions:
    window_query: str = "Offline Games"
    wait_seconds: float = 18.0
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
    """Convert a screenshot-pixel point to global macOS point coordinates."""

    scale_x = window.width / detected.image_width
    scale_y = window.height / detected.image_height
    return window.x + point[0] * scale_x, window.y + point[1] * scale_y


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

    # Select the pencil/circle tool, located directly below the board center.
    bridge.click(*_screen_point(detected, window, detected.geometry.pencil_center()))
    time.sleep(0.12)
    _click_cells(
        bridge,
        window,
        detected,
        solution.selected_cells(),
        pause=click_pause,
    )

    if mode == "keep-and-erase":
        bridge.click(*_screen_point(detected, window, detected.geometry.eraser_center()))
        time.sleep(0.12)
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
            time.sleep(0.35)
            bridge.click(
                *_screen_point(
                    detected, current, detected.geometry.pencil_center()
                )
            )
            time.sleep(0.12)
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
    if options.wait_seconds < 0 or options.click_pause < 0:
        raise ValueError("wait and click-pause must not be negative")
    if options.max_levels is not None and options.max_levels < 1:
        raise ValueError("max-levels must be at least 1")
    print("cross-sums 0.2.0: fixed-glyph reader (no Vision OCR)", flush=True)
    bridge = MacOSBridge()
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
