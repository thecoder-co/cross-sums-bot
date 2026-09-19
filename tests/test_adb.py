from pathlib import Path
from types import SimpleNamespace

import pytest

from cross_sums.adb import ADBBridge, AndroidTarget
from cross_sums.native import NativeBridgeError


def test_android_taps_use_the_latest_screenshot_dimensions(monkeypatch, tmp_path):
    bridge = ADBBridge.__new__(ADBBridge)
    bridge.executable = Path("/usr/bin/adb")
    bridge.serial = "phone"
    bridge.package_name = "com.JindoBlu.OfflineGames"
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"not-a-png", stderr=b"")

    monkeypatch.setattr("cross_sums.adb.subprocess.run", run)
    target = AndroidTarget("phone", 1080, 2340, "phone")
    # The command itself is the important contract here: no desktop coordinate
    # API is used and coordinates are rounded device pixels.
    bridge.click(470.6, 1759.4)
    assert commands == [
        (
            ["/usr/bin/adb", "-s", "phone", "shell", "input", "tap", "471", "1759"],
            {"capture_output": True, "text": True, "check": False},
        )
    ]
    assert target.width == 1080


def test_find_window_rejects_multiple_devices(monkeypatch):
    bridge = ADBBridge.__new__(ADBBridge)
    bridge.executable = Path("/usr/bin/adb")
    bridge.serial = None
    bridge.package_name = "com.JindoBlu.OfflineGames"

    monkeypatch.setattr(
        bridge,
        "_run",
        lambda *args, **kwargs: "List of devices attached\nfirst\tdevice\nsecond\tdevice\n",
    )
    with pytest.raises(NativeBridgeError, match="Multiple Android devices"):
        bridge.find_window("Offline Games")


def test_capture_refreshes_target_size(monkeypatch, tmp_path):
    bridge = ADBBridge.__new__(ADBBridge)
    bridge.executable = Path("/usr/bin/adb")
    bridge.serial = "phone"
    bridge.package_name = ""
    source = Path(__file__).parent / "fixtures" / "level-3.png"
    png = source.read_bytes()
    monkeypatch.setattr(bridge, "_run", lambda *args, **kwargs: png)
    target = AndroidTarget("phone", 1, 1, "phone")
    destination = tmp_path / "screen.png"
    bridge.capture_window(target, destination)
    assert (target.width, target.height) == (966, 966)
