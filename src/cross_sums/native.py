from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class NativeBridgeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Window:
    id: int
    owner: str
    name: str
    pid: int
    x: float
    y: float
    width: float
    height: float


class MacOSBridge:
    """Small wrapper around native macOS window and click APIs."""

    def __init__(self) -> None:
        if os.uname().sysname != "Darwin":
            raise NativeBridgeError("computer use is supported only on macOS")
        self.executable = self._compile_helper()

    @staticmethod
    def _source_path() -> Path:
        return Path(__file__).with_name("native_bridge.swift")

    def _compile_helper(self) -> Path:
        source = self._source_path()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
        cache_root = Path(
            os.environ.get(
                "CROSS_SUMS_CACHE_DIR",
                Path.home() / "Library" / "Caches" / "cross-sums-bot",
            )
        )
        cache_root.mkdir(parents=True, exist_ok=True)
        executable = cache_root / f"native-bridge-{digest}"
        if executable.exists():
            return executable

        swiftc = shutil.which("swiftc")
        if not swiftc:
            raise NativeBridgeError(
                "Swift is unavailable; install the Xcode Command Line Tools"
            )
        temporary = executable.with_suffix(".building")
        result = subprocess.run(
            [swiftc, "-O", str(source), "-o", str(temporary)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            temporary.unlink(missing_ok=True)
            raise NativeBridgeError(
                "Could not compile the native helper:\n" + result.stderr.strip()
            )
        temporary.replace(executable)
        return executable

    def _run(self, *arguments: object) -> Any:
        result = subprocess.run(
            [str(self.executable), *(str(value) for value in arguments)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise NativeBridgeError(result.stderr.strip() or "native helper failed")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise NativeBridgeError("native helper returned invalid JSON") from error

    def find_window(self, query: str) -> Window:
        return Window(**self._run("find-window", query))

    def capture_window(self, window: Window, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["/usr/sbin/screencapture", "-x", "-o", "-l", str(window.id), str(destination)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode or not destination.exists():
            raise NativeBridgeError(
                "Window capture failed. Allow Screen Recording for your terminal or Codex. "
                + result.stderr.strip()
            )
        return destination

    def click(self, x: float, y: float) -> None:
        # Successful click emits no JSON, so invoke it directly.
        result = subprocess.run(
            [str(self.executable), "click", str(x), str(y)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise NativeBridgeError(
                "Click failed. Allow Accessibility control for your terminal or Codex. "
                + result.stderr.strip()
            )

    def activate(self, pid: int) -> None:
        result = subprocess.run(
            [str(self.executable), "activate", str(pid)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise NativeBridgeError(result.stderr.strip() or "could not activate the game")


def temporary_png() -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix="cross-sums-", suffix=".png")
    os.close(descriptor)
    path = Path(raw_path)
    path.unlink(missing_ok=True)
    return path
