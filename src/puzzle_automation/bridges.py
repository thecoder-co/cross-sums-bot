"""Stable, puzzle-neutral access to the existing screen bridges.

The compatibility imports keep the proven Cross Sums bridge implementation in
one place while letting new puzzle packages depend on a neutral namespace.
"""

from cross_sums.adb import ADBBridge, AndroidTarget
from cross_sums.native import MacOSBridge, NativeBridgeError, Window, temporary_png

__all__ = [
    "ADBBridge",
    "AndroidTarget",
    "MacOSBridge",
    "NativeBridgeError",
    "Window",
    "temporary_png",
]
