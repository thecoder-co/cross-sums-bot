# Cross Sums Bot

A small `uv` Python project with two deliberately separate parts:

1. **Backtracking** turns a number grid and its row/column clues into the unique
   boolean cell-selection mask.
2. **Computer use** finds the **Offline Games** window on macOS, captures only
   that window, finds the grid directly from its cell backgrounds, reads each
   digit using bundled font templates, runs the solver, and clicks the retained cells.

The computer-use paths refuse to click if the board is incomplete, a clue is
impossible, no solution exists, or more than one solution exists. The Android
path uses ADB screenshots and taps, so it works without macOS Screen Recording
or Accessibility permissions.

## Requirements

- [`uv`](https://docs.astral.sh/uv/)
- macOS, Xcode Command Line Tools (`swiftc`), Screen Recording permission, and
  Accessibility permission for the desktop `play` command
- Android platform-tools (`adb`) and USB debugging for the `android` command

The native bridge uses Core Graphics and AppKit for window control and clicks.
It is compiled automatically on first use. Screenshot reading uses Pillow alone;
`scan` and `solve` also work without macOS or Swift.

## Reader strategy (version 0.2.0)

The reader does not call Vision or learn digits from the current level. It finds
the regular lattice of dark cell interiors, segments the white digits, and
compares them against a fixed, bundled alphabet of `0` through `9` extracted
from the manually verified reference Level 2. Each comparison checks both the
best match and its separation from the next-best digit. Large targets are read
separately from the small remaining-sum labels.

This reader targets the **dark theme and font shown in your screenshots**. Start
on a fresh, unmarked board. Changed themes/fonts, partly erased cells, overlays,
and uncertain digits cause an explicit error rather than a guessed click. The
last failing capture is saved to `work/debug/failed-board.png` (or `--debug-dir`).
The test fixtures contain unseen Levels 3–5; tests compare all 49 cells and 14
clues at four image scales and with the board translated within the image. A
captured Level 7 fixture also verifies that grid detection adapts to 8×8 boards
(64 cells and 16 clues) instead of assuming every level contains 49 cells.

## Setup and checks

```bash
uv sync
uv run pytest
uv run cross-sums --version
uv run cross-sums solve examples/level-2.json
```

The example is the Level 2 board in the supplied screenshots. The version command
must print `cross-sums 0.2.0 (fixed-glyph reader)`. If you still get the old
`single-digit candidates; expected at least 49` error, the command is loading
another copy of the project. Run it from the updated project directory or use
`uv run --project /absolute/path/to/updated/project cross-sums play`.

To replay a screenshot without touching the game:

```bash
uv run cross-sums scan tests/fixtures/level-5.png
```

## Use it safely

Open Cross Sums in **Offline Games** and leave the full board visible. First run
a read-only pass:

```bash
uv run cross-sums play --dry-run --debug-dir work/debug
```

The first run can prompt for macOS Screen Recording permission. If permissions
change, restart the terminal/Codex app before trying again. Inspect the JSON in
`work/debug`, then enable clicking:

```bash
uv run cross-sums play
```

The default `keep-only` mode selects the pencil/circle control and clicks every
cell the solution retains. It then waits fifteen seconds for the game's cleanup
animation before scanning the next board. Immediately after marking, it rereads
the unchanged board, detects circles, and retries only the cells whose clicks did
not register. An unexpected circle stops the run instead of risking more input.
If the animation is still running, it retries the read up to three times, waiting
another 15 seconds each time. It never repeats clicks on the previous puzzle.
Stop the loop with **Ctrl-C**.

If this version of Offline Games requires every rejected cell to be explicitly
erased, use:

```bash
uv run cross-sums play --mode keep-and-erase
```

Useful controls:

```text
--max-levels 10       stop after ten boards
--wait 20             override the 15-second wait between boards
--click-pause 0.08    click more slowly
--window "Offline Games"  change the window/app-name match
```

## Android / ADB computer use

Connect an Android device with USB debugging enabled, open Cross Sums in
Offline Games, and leave the full board visible. The Android command reads the
device screenshot, solves the board, and derives every tap from the detected
board geometry. It locates the tool toggle in each screenshot and verifies the
requested tool is selected before tapping cells. It does not assume a
1080×2340 screen, Android density, or a particular aspect ratio; screenshot
dimensions and tool position are refreshed for each board.

Start with a read-only pass:

```bash
uv run cross-sums android --dry-run --debug-dir work/android
```

Then enable taps:

```bash
uv run cross-sums android --max-levels 1
```

If more than one device is connected, select one with `--device SERIAL`. Use
`--adb /path/to/adb` when `adb` is not on `PATH`, and `--package PACKAGE` when
the installed game uses a different package name. `--click-pause` defaults to
0.08 seconds on Android to allow the Unity input queue to settle.

The game window may move or resize between boards: every iteration finds it
again and converts screenshot pixels back to macOS screen coordinates. Brief
macOS window-server capture failures are retried twice before the run stops.

## Puzzle JSON format

```json
{
  "grid": [
    [1, 2],
    [3, 4]
  ],
  "row_targets": [1, 4],
  "column_targets": [1, 4]
}
```

`selected[row][column]` in the output is `true` for a retained/circled number.

## How the backtracking works

For each row, a small recursive search enumerates only subsets that equal that
row's clue. A second recursive search chooses one such subset per row. At every
step it tracks column totals and abandons a branch when a total is already too
large or the values in the remaining rows cannot make it large enough. Search
continues until two solutions are found, allowing the program to enforce the
game's unique-solution promise before any click is sent.
