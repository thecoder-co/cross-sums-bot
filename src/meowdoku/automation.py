"""Guarded screenshot-to-input automation for Offline Games Meowdoku."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from puzzle_automation import ADBBridge, AndroidTarget, MacOSBridge, NativeBridgeError
from puzzle_automation.bridges import temporary_png
from puzzle_automation.coordinates import screen_point

from .geometry import BoardReadError
from .model import Cell, MeowdokuSolution
from .solver import solve_unique, verify_solution
from .vision import DetectedMeowdoku, read_screenshot


OFFLINE_GAMES_ANDROID_PACKAGE = "com.JindoBlu.OfflineGames"


@dataclass(frozen=True, slots=True)
class AutomationOptions:
    window_query: str = "Offline Games"
    wait_seconds: float = 15.0
    press_duration: float = 1.5
    verify_wait: float = 0.5
    stability_wait: float = 1.25
    dry_run: bool = False
    max_levels: int | None = None
    debug_directory: Path | None = None


def _screen_cell(
    detected: DetectedMeowdoku,
    target,
    cell: Cell,
) -> tuple[float, float]:
    origin = None if isinstance(target, AndroidTarget) else (target.x, target.y)
    return screen_point(
        target,
        detected.geometry.cell_center(*cell),
        image_width=detected.image_width,
        image_height=detected.image_height,
        desktop_origin=origin,
    )


def _capture(bridge, options: AutomationOptions, destination: Path):
    last_error: NativeBridgeError | None = None
    for attempt in range(3):
        target = bridge.find_window(options.window_query)
        try:
            bridge.capture_window(target, destination)
            return target
        except NativeBridgeError as error:
            last_error = error
            if attempt == 2:
                break
            time.sleep(0.5)
    assert last_error is not None
    raise last_error


def _same_target(first, second) -> bool:
    return (
        first.id,
        round(first.width),
        round(first.height),
    ) == (
        second.id,
        round(second.width),
        round(second.height),
    )


def _long_press(
    bridge,
    point: tuple[float, float],
    duration_seconds: float,
) -> None:
    duration_ms = round(duration_seconds * 1_000)
    if duration_ms <= 0:
        raise ValueError("press-duration must be greater than zero")
    bridge.long_press(*point, duration_ms=duration_ms)


def _validated_current_board(
    bridge,
    options: AutomationOptions,
    expected_target,
    expected: DetectedMeowdoku,
    path: Path,
) -> tuple[object, DetectedMeowdoku]:
    target = _capture(bridge, options, path)
    if not _same_target(expected_target, target):
        raise RuntimeError("Game target changed while solving; no more input sent")
    current = read_screenshot(path)
    if current.fingerprint != expected.fingerprint:
        raise RuntimeError("Meowdoku board changed while solving; no more input sent")
    return target, current


def apply_solution(
    bridge,
    target,
    detected: DetectedMeowdoku,
    solution: MeowdokuSolution,
    options: AutomationOptions,
) -> None:
    """Place missing cats, verifying the board after every long press."""

    expected = set(solution.selected_cells())
    initial = set(detected.puzzle.cats)
    if not initial.issubset(expected):
        raise RuntimeError("The board already contains a cat outside the solution")
    pending = [cell for cell in solution.selected_cells() if cell not in initial]
    if not pending:
        return

    path = temporary_png()
    try:
        for index, cell in enumerate(pending):
            target, current = _validated_current_board(
                bridge, options, target, detected, path
            )
            observed = set(current.puzzle.cats)
            if not observed.issubset(expected):
                raise RuntimeError("An unexpected cat appeared; no more input sent")
            if cell in observed:
                continue

            # Capture/verification can occur while another app owns focus.
            # Activate only after the last read and immediately before input.
            bridge.activate(target.pid)
            if not isinstance(target, AndroidTarget):
                time.sleep(1.0)
            _long_press(
                bridge,
                _screen_cell(current, target, cell),
                options.press_duration,
            )
            time.sleep(options.verify_wait)
            after_target = _capture(bridge, options, path)
            if not _same_target(target, after_target):
                raise RuntimeError("Game target changed after a long press; stopped")
            try:
                after = read_screenshot(path)
            except BoardReadError:
                if index == len(pending) - 1:
                    return
                raise RuntimeError(
                    "Board disappeared before all cats were verified; stopped"
                )
            if after.fingerprint != detected.fingerprint:
                if index == len(pending) - 1:
                    return
                raise RuntimeError("Board advanced before all cats were placed; stopped")
            after_cats = set(after.puzzle.cats)
            if not after_cats.issubset(expected):
                raise RuntimeError("An unexpected cat appeared after input; stopped")
            if cell not in after_cats:
                raise RuntimeError(
                    f"Could not verify the cat at ({cell[0]}, {cell[1]}); stopped without retrying"
                )

            # Rejected placements can show a short-lived cat animation. Never
            # let that transient frame authorize the next click: the same cat
            # must still be present after the animation has settled.
            time.sleep(options.stability_wait)
            stable_target = _capture(bridge, options, path)
            if not _same_target(target, stable_target):
                raise RuntimeError("Game target changed during mark verification; stopped")
            try:
                stable = read_screenshot(path)
            except BoardReadError:
                if index == len(pending) - 1:
                    return
                raise RuntimeError(
                    "Board disappeared before the cat placement remained stable; stopped"
                )
            if stable.fingerprint != detected.fingerprint:
                if index == len(pending) - 1:
                    return
                raise RuntimeError("Board changed before the cat placement remained stable; stopped")
            stable_cats = set(stable.puzzle.cats)
            if not stable_cats.issubset(expected) or cell not in stable_cats:
                raise RuntimeError(
                    f"Cat at ({cell[0]}, {cell[1]}) did not persist after animation; stopped"
                )
    finally:
        path.unlink(missing_ok=True)


def _save_debug(
    directory: Path,
    level: int,
    screenshot: Path,
    detected: DetectedMeowdoku,
    solution: MeowdokuSolution,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    image_destination = directory / f"level-{level:03d}.png"
    image_destination.write_bytes(screenshot.read_bytes())
    payload = {
        **detected.puzzle.to_dict(),
        "solution": [list(cell) for cell in solution.selected_cells()],
        "geometry": {
            "left": detected.geometry.left,
            "top": detected.geometry.top,
            "cell_width": detected.geometry.cell_width,
            "cell_height": detected.geometry.cell_height,
            "size": detected.geometry.size,
        },
    }
    (directory / f"level-{level:03d}.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )


def _read_next_board(
    bridge,
    options: AutomationOptions,
    screenshot: Path,
    previous_fingerprint: tuple[tuple[int, ...], ...] | None,
):
    for attempt in range(4):
        target = _capture(bridge, options, screenshot)
        try:
            detected = read_screenshot(screenshot)
            if detected.fingerprint == previous_fingerprint:
                raise BoardReadError("The previous board has not advanced yet")
            return target, detected
        except BoardReadError:
            if previous_fingerprint is None or attempt == 3:
                raise
            time.sleep(options.wait_seconds)
    raise AssertionError("unreachable")


def run(options: AutomationOptions) -> None:
    _run_loop(options, MacOSBridge())


def run_android(
    options: AutomationOptions,
    *,
    device_serial: str | None = None,
    adb_path: str | Path | None = None,
    package_name: str = OFFLINE_GAMES_ANDROID_PACKAGE,
) -> None:
    _run_loop(
        options,
        ADBBridge(
            serial=device_serial,
            executable=adb_path,
            package_name=package_name,
        ),
    )


def _run_loop(options: AutomationOptions, bridge) -> None:
    if (
        options.wait_seconds < 0
        or options.press_duration <= 0
        or options.verify_wait < 0
        or options.stability_wait < 0
    ):
        raise ValueError(
            "wait, verify-wait, and stability-wait must not be negative, "
            "and press-duration must be greater than zero"
        )
    if options.max_levels is not None and options.max_levels < 1:
        raise ValueError("max-levels must be at least one")

    level = 0
    previous_fingerprint = None
    while options.max_levels is None or level < options.max_levels:
        screenshot = temporary_png()
        try:
            target, detected = _read_next_board(
                bridge, options, screenshot, previous_fingerprint
            )
            solution = solve_unique(detected.puzzle)
            if not verify_solution(detected.puzzle, solution):
                raise RuntimeError("Internal verification rejected the solver result")
            level += 1
            print(
                f"Board {level}: {detected.puzzle.size}x{detected.puzzle.size}, "
                f"{len(solution.selected_cells())} cats",
                flush=True,
            )
            if options.debug_directory:
                _save_debug(
                    options.debug_directory, level, screenshot, detected, solution
                )
            if options.dry_run:
                print("Dry run: no clicks sent.", flush=True)
                return
            apply_solution(bridge, target, detected, solution, options)
            previous_fingerprint = detected.fingerprint
            if options.max_levels is None or level < options.max_levels:
                time.sleep(options.wait_seconds)
        except (ValueError, RuntimeError) as error:
            if screenshot.exists():
                directory = options.debug_directory or Path("work/meowdoku")
                directory.mkdir(parents=True, exist_ok=True)
                failure = directory / "failed-board.png"
                shutil.copyfile(screenshot, failure)
                raise RuntimeError(
                    f"{error} Screenshot saved to {failure.resolve()}"
                ) from error
            raise
        finally:
            screenshot.unlink(missing_ok=True)
