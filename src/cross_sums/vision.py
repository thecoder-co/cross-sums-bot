"""Screenshot -> grid geometry -> fixed digit shapes -> backtracking input."""
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .geometry import BoardGeometry, BoardReadError, locate_grid
from .model import Puzzle
from .template_ocr import recognize_puzzle


@dataclass(frozen=True, slots=True)
class DetectedPuzzle:
    puzzle: Puzzle
    geometry: BoardGeometry
    image_width: int
    image_height: int


def read_screenshot(bridge: object, path: Path) -> DetectedPuzzle:
    # The bridge argument is kept for existing programmatic callers; recognition
    # itself is portable Python and never invokes a native OCR service.
    with Image.open(path) as source:
        image = source.convert('RGB')
    geometry = locate_grid(image)
    return DetectedPuzzle(recognize_puzzle(image, geometry), geometry, *image.size)
