"""Coordinate conversion shared by desktop and Android automation."""

from __future__ import annotations

from typing import Protocol


class Target(Protocol):
    width: float
    height: float


def screen_point(
    target: Target,
    point: tuple[float, float],
    *,
    image_width: int,
    image_height: int,
    desktop_origin: tuple[float, float] | None,
) -> tuple[float, float]:
    """Map screenshot pixels to the coordinate space used by an input bridge.

    Android screenshots and input taps share an origin, so ``desktop_origin``
    is ``None``. Desktop captures are window-local and therefore add the
    window's screen origin after scaling.
    """

    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")
    x = point[0] * target.width / image_width
    y = point[1] * target.height / image_height
    if desktop_origin is not None:
        x += desktop_origin[0]
        y += desktop_origin[1]
    return x, y
