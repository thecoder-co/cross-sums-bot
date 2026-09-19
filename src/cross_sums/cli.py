from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .computer_use import AutomationOptions, run
from .model import Puzzle
from .solver import solve_unique
from .vision import read_screenshot


def _solution_payload(puzzle: Puzzle) -> dict[str, object]:
    solution = solve_unique(puzzle)
    return {
        **puzzle.to_dict(),
        "selected": [list(row) for row in solution.selected],
        "selected_cells": [list(cell) for cell in solution.selected_cells()],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cross-sums",
        description="Solve Cross Sums with backtracking or automate Offline Games on macOS.",
    )
    parser.add_argument('--version', action='version', version='cross-sums 0.2.0 (fixed-glyph reader)')
    commands = parser.add_subparsers(dest="command", required=True)

    solve = commands.add_parser("solve", help="solve a puzzle JSON file")
    solve.add_argument("puzzle", type=Path)

    scan = commands.add_parser("scan", help="read and solve a screenshot without clicking")
    scan.add_argument("image", type=Path)

    play = commands.add_parser("play", help="find the game and solve boards in a loop")
    play.add_argument("--window", default="Offline Games", help="window title or app name")
    play.add_argument("--wait", type=float, default=18.0, help="seconds between boards")
    play.add_argument("--click-pause", type=float, default=0.005)
    play.add_argument(
        "--mode",
        choices=("keep-only", "keep-and-erase"),
        default="keep-only",
        help="click retained cells only, or explicitly process every cell",
    )
    play.add_argument("--dry-run", action="store_true", help="read and solve once; never click")
    play.add_argument("--max-levels", type=int)
    play.add_argument("--debug-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "solve":
            puzzle = Puzzle.from_dict(json.loads(arguments.puzzle.read_text()))
            print(json.dumps(_solution_payload(puzzle), indent=2))
        elif arguments.command == "scan":
            detected = read_screenshot(None, arguments.image)
            print(json.dumps(_solution_payload(detected.puzzle), indent=2))
        else:
            run(
                AutomationOptions(
                    window_query=arguments.window,
                    wait_seconds=arguments.wait,
                    click_pause=arguments.click_pause,
                    mode=arguments.mode,
                    dry_run=arguments.dry_run,
                    max_levels=arguments.max_levels,
                    debug_directory=arguments.debug_dir,
                )
            )
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
