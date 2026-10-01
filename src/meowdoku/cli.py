"""Command-line interface for the Meowdoku solver and automation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .automation import (
    OFFLINE_GAMES_ANDROID_PACKAGE,
    AutomationOptions,
    run,
    run_android,
)
from .deduction import next_hint
from .model import MeowdokuPuzzle
from .solver import classify_cell, solve_unique
from .vision import read_screenshot


def _payload(puzzle: MeowdokuPuzzle) -> dict[str, object]:
    solution = solve_unique(puzzle)
    return {
        **puzzle.to_dict(),
        "solution": [list(cell) for cell in solution.selected_cells()],
        "selected": [list(row) for row in solution.selected_matrix(puzzle.size)],
    }


def _automation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--wait", type=float, default=15.0)
    parser.add_argument(
        "--press-duration",
        type=float,
        default=1.5,
        help="seconds to hold each solution cell (default: 1.5)",
    )
    parser.add_argument("--verify-wait", type=float, default=0.5)
    parser.add_argument("--stability-wait", type=float, default=1.25)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-levels", type=int)
    parser.add_argument("--debug-dir", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meowdoku",
        description="Solve or automate Offline Games Meowdoku on macOS and Android.",
    )
    parser.add_argument("--version", action="version", version="meowdoku 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)

    solve = commands.add_parser("solve", help="solve a puzzle JSON file")
    solve.add_argument("puzzle", type=Path)

    scan = commands.add_parser("scan", help="read and solve a screenshot without clicking")
    scan.add_argument("image", type=Path)

    classify = commands.add_parser(
        "classify", help="prove whether one JSON-board cell is a cat, empty, or undetermined"
    )
    classify.add_argument("puzzle", type=Path)
    classify.add_argument("row", type=int, help="one-based row")
    classify.add_argument("column", type=int, help="one-based column")

    hint = commands.add_parser("hint", help="return one named, CP-SAT-verified deduction")
    hint.add_argument("puzzle", type=Path)

    play = commands.add_parser("play", help="solve the visible macOS Offline Games board")
    play.add_argument("--window", default="Offline Games")
    _automation_arguments(play)

    android = commands.add_parser("android", help="solve Offline Games through ADB")
    android.add_argument("--device", dest="device_serial")
    android.add_argument("--adb", type=Path)
    android.add_argument("--package", default=OFFLINE_GAMES_ANDROID_PACKAGE)
    _automation_arguments(android)
    return parser


def _options(arguments: argparse.Namespace) -> AutomationOptions:
    return AutomationOptions(
        window_query=getattr(arguments, "window", "Offline Games"),
        wait_seconds=arguments.wait,
        press_duration=arguments.press_duration,
        verify_wait=arguments.verify_wait,
        stability_wait=arguments.stability_wait,
        dry_run=arguments.dry_run,
        max_levels=arguments.max_levels,
        debug_directory=arguments.debug_dir,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "solve":
            puzzle = MeowdokuPuzzle.from_dict(json.loads(arguments.puzzle.read_text()))
            print(json.dumps(_payload(puzzle), indent=2))
        elif arguments.command == "scan":
            print(json.dumps(_payload(read_screenshot(arguments.image).puzzle), indent=2))
        elif arguments.command == "classify":
            puzzle = MeowdokuPuzzle.from_dict(json.loads(arguments.puzzle.read_text()))
            target = (arguments.row - 1, arguments.column - 1)
            print(
                json.dumps(
                    {
                        "cell": [arguments.row, arguments.column],
                        "classification": classify_cell(puzzle, target),
                    },
                    indent=2,
                )
            )
        elif arguments.command == "hint":
            puzzle = MeowdokuPuzzle.from_dict(json.loads(arguments.puzzle.read_text()))
            hint = next_hint(puzzle)
            print(json.dumps(hint.to_dict() if hint else None, indent=2))
        elif arguments.command == "play":
            run(_options(arguments))
        else:
            run_android(
                _options(arguments),
                device_serial=arguments.device_serial,
                adb_path=arguments.adb,
                package_name=arguments.package,
            )
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
