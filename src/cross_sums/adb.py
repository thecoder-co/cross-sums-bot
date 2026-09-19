"""ADB bridge for screenshot-driven Android computer use."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .native import NativeBridgeError


_FOREGROUND_PACKAGE = re.compile(
    r"(?:mResumedActivity|topResumedActivity)=ActivityRecord\{[^}]*\s(?P<package>[^/\s]+)/"
)
_DEVICE_LINE = re.compile(r"^(?P<serial>\S+)\s+(?P<state>device|offline|unauthorized)\b")
_SIZE = re.compile(r"(?P<width>\d+)x(?P<height>\d+)")


@dataclass(slots=True)
class AndroidTarget:
    """The device coordinate space used by ``input tap``."""

    id: str
    width: int
    height: int
    serial: str
    pid: int = 0


class ADBBridge:
    """Capture and control one connected Android device through ADB.

    The target dimensions are refreshed after every screenshot. This matters on
    devices that report an overridden display size or rotate while the game is
    open: taps are always expressed in the same pixel space as the PNG that was
    read by the board detector.
    """

    def __init__(
        self,
        *,
        serial: str | None = None,
        executable: str | Path | None = None,
        package_name: str = "com.JindoBlu.OfflineGames",
    ) -> None:
        self.serial = serial
        self.executable = self._find_executable(executable)
        self.package_name = package_name

    @staticmethod
    def _find_executable(executable: str | Path | None) -> Path:
        if executable is not None:
            path = Path(executable)
            if not path.is_file():
                raise NativeBridgeError(f"ADB executable was not found: {path}")
            return path

        candidates = [
            os.environ.get("ANDROID_HOME"),
            os.environ.get("ANDROID_SDK_ROOT"),
            str(Path.home() / "Library" / "Android" / "sdk"),
            str(Path.home() / "Android" / "Sdk"),
        ]
        for root in candidates:
            if root:
                path = Path(root) / "platform-tools" / "adb"
                if path.is_file():
                    return path
        found = shutil.which("adb")
        if found:
            return Path(found)
        raise NativeBridgeError(
            "ADB was not found; install Android platform-tools or pass --adb"
        )

    def _command(self, *arguments: object) -> list[str]:
        command = [str(self.executable)]
        if self.serial:
            command.extend(("-s", self.serial))
        command.extend(str(argument) for argument in arguments)
        return command

    def _run(self, *arguments: object, binary: bool = False) -> bytes | str:
        result = subprocess.run(
            self._command(*arguments),
            capture_output=True,
            text=not binary,
            check=False,
        )
        if result.returncode:
            detail = result.stderr if binary else result.stderr.strip()
            if isinstance(detail, bytes):
                detail = detail.decode(errors="replace").strip()
            raise NativeBridgeError(detail or "ADB command failed")
        return result.stdout

    def _connected_serials(self) -> list[str]:
        raw = self._run("devices")
        assert isinstance(raw, str)
        devices: list[tuple[str, str]] = []
        for line in raw.splitlines():
            match = _DEVICE_LINE.match(line.strip())
            if match:
                devices.append((match.group("serial"), match.group("state")))

        if self.serial:
            for serial, state in devices:
                if serial == self.serial:
                    if state == "device":
                        return [serial]
                    raise NativeBridgeError(
                        f"Android device {serial!r} is {state}; unlock it and authorize ADB"
                    )
            raise NativeBridgeError(f"Android device {self.serial!r} is not connected")

        ready = [serial for serial, state in devices if state == "device"]
        if not ready:
            if any(state == "unauthorized" for _, state in devices):
                raise NativeBridgeError(
                    "Android device is unauthorized; accept the USB debugging prompt"
                )
            raise NativeBridgeError("No Android device is connected through ADB")
        if len(ready) > 1:
            joined = ", ".join(ready)
            raise NativeBridgeError(
                f"Multiple Android devices are connected ({joined}); pass --device"
            )
        self.serial = ready[0]
        return ready

    def _display_size(self) -> tuple[int, int]:
        raw = self._run("shell", "wm", "size")
        assert isinstance(raw, str)
        matches = _SIZE.findall(raw)
        if not matches:
            raise NativeBridgeError("Could not determine the Android display size")
        width, height = (int(value) for value in matches[-1])
        return width, height

    def _foreground_package(self) -> str | None:
        raw = self._run("shell", "dumpsys", "activity", "activities")
        assert isinstance(raw, str)
        match = _FOREGROUND_PACKAGE.search(raw)
        return match.group("package") if match else None

    def find_window(self, _query: str) -> AndroidTarget:
        """Return the connected device, validating that the game is foregrounded."""

        self._connected_serials()
        foreground = self._foreground_package()
        if self.package_name and foreground and foreground != self.package_name:
            raise NativeBridgeError(
                f"Expected {self.package_name} in the foreground, found {foreground}"
            )
        width, height = self._display_size()
        return AndroidTarget(
            id=self.serial or "android",
            width=width,
            height=height,
            serial=self.serial or "",
        )

    def capture_window(self, target: AndroidTarget, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = self._run("exec-out", "screencap", "-p", binary=True)
        assert isinstance(raw, bytes)
        if not raw:
            raise NativeBridgeError("ADB returned an empty Android screenshot")
        destination.write_bytes(raw)
        try:
            with Image.open(destination) as image:
                target.width, target.height = image.size
        except (OSError, ValueError) as error:
            destination.unlink(missing_ok=True)
            raise NativeBridgeError("ADB returned an invalid Android screenshot") from error
        return destination

    def click(self, x: float, y: float) -> None:
        self._run("shell", "input", "tap", round(x), round(y))

    def activate(self, _pid: int) -> None:
        # ADB input is device-global; unlike a desktop window it does not need
        # activation. The foreground-package check happens before each board.
        return
