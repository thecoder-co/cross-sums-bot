"""Reusable screenshot and input bridges for puzzle automation."""

from .bridges import ADBBridge, AndroidTarget, MacOSBridge, NativeBridgeError, Window
from .coordinates import screen_point

__all__ = [
    "ADBBridge",
    "AndroidTarget",
    "MacOSBridge",
    "NativeBridgeError",
    "Window",
    "screen_point",
]
