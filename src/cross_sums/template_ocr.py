"""Fixed-font digit recognition; no text OCR or per-level training required."""
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image

from .geometry import BoardGeometry, BoardReadError
from .model import Puzzle


@dataclass(frozen=True, slots=True)
class _Component:
    left: int
    top: int
    right: int
    bottom: int
    area: int

    @property
    def aspect(self) -> float:
        return (self.right - self.left) / (self.bottom - self.top)


def _components(image: Image.Image, box: tuple[float, ...]) -> list[_Component]:
    left, top, right, bottom = (int(round(value)) for value in box)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    if right <= left or bottom <= top:
        return []
    crop = image.crop((left, top, right, bottom)).convert('L')
    width, height = crop.size
    pixels = crop.load()
    foreground = {(x,y) for y in range(height) for x in range(width) if pixels[x,y] >= 175}
    found = []
    while foreground:
        start = foreground.pop()
        queue = deque([start])
        min_x = max_x = start[0]
        min_y = max_y = start[1]
        area = 1
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if neighbor not in foreground:
                    continue
                foreground.remove(neighbor)
                queue.append(neighbor)
                area += 1
                min_x, max_x = min(min_x,neighbor[0]), max(max_x,neighbor[0])
                min_y, max_y = min(min_y,neighbor[1]), max(max_y,neighbor[1])
        if area >= 8 and max_x-min_x >= 2 and max_y-min_y >= 6:
            found.append(_Component(left+min_x,top+min_y,left+max_x+1,top+max_y+1,area))
    return sorted(found, key=lambda component: component.left)


def _normalize(image: Image.Image, component: _Component) -> bytes:
    glyph = image.crop((component.left,component.top,component.right,component.bottom)).convert('L')
    normalized = glyph.point(lambda value: 255 if value >= 175 else 0).resize(
        (24,36), Image.Resampling.NEAREST)
    return bytes(1 if value else 0 for value in normalized.tobytes())


@lru_cache(maxsize=1)
def _templates() -> dict[int, tuple[tuple[int, float], ...]]:
    raw = json.loads((Path(__file__).parent / 'assets' / 'digits.json').read_text())
    return {int(digit): tuple((int.from_bytes(bytes.fromhex(sample['bits']), 'big'), sample['aspect'])
                             for sample in samples)
            for digit, samples in raw['templates'].items()}


def _classify(image: Image.Image, component: _Component, label: str) -> int:
    glyph = int.from_bytes(_normalize(image, component), 'big')
    # Compare per-class minima, not individual templates: two samples of the
    # same digit are not an ambiguity. Aspect preserves the distinction of 1.
    scores = sorted((min(
        (glyph ^ reference).bit_count() / (24 * 36)
        + .20*abs(component.aspect-aspect)
        for reference,aspect in samples), digit)
        for digit,samples in _templates().items())
    (distance, digit), (runner_up, _) = scores[:2]
    if distance > .22 or runner_up - distance < .035:
        raise BoardReadError(f'Uncertain digit in {label}: shape distance {distance:.3f}, '
                             f'margin {runner_up-distance:.3f}. No clicks sent.')
    return digit


def _cell_box(g: BoardGeometry, row: int, column: int) -> tuple[float, ...]:
    return (g.left+(column+.12)*g.cell_width, g.top+(row+.12)*g.cell_height,
            g.left+(column+.88)*g.cell_width, g.top+(row+.88)*g.cell_height)


def _read_number(image: Image.Image, box: tuple[float, ...], label: str,
                 *, cell: bool = False, allow_marked: bool = False) -> int:
    components = _components(image, box)
    if cell and allow_marked:
        # The full-cell crop contains a separate closed ring around a marked
        # digit. Remove the ring only; classify the central glyph normally.
        components = [c for c in components
                      if c.bottom-c.top < (box[3]-box[1])*.68]
    if not components:
        raise BoardReadError(f'No digit in {label}; wait for a fresh, unmarked board.')
    if not cell:
        # Discard only the small top-left remaining-sum label. Never invent a
        # missing target or substitute its remaining sum.
        tallest = max(c.bottom-c.top for c in components)
        components = [c for c in components if c.bottom-c.top >= tallest*.70]
    required = (1,) if cell else (1,2,3)
    if len(components) not in required:
        raise BoardReadError(f'Unexpected markings in {label}; start with a fresh board.')
    # Ensure a target/glyph is full height; this rejects partial animation frames.
    if any(c.bottom-c.top < (box[3]-box[1])*.30 for c in components):
        raise BoardReadError(f'Incomplete digit in {label}.')
    digits = [_classify(image,c,label) for c in components]
    value = int(''.join(map(str,digits)))
    if cell and not 1 <= value <= 9:
        raise BoardReadError(f'Invalid cell value in {label}: {value}')
    return value


def recognize_puzzle(image: Image.Image, g: BoardGeometry, *, allow_marked: bool = False) -> Puzzle:
    def cell_box(r,c):
        if allow_marked:
            return (g.left+(c+.025)*g.cell_width,g.top+(r+.025)*g.cell_height,
                    g.left+(c+.975)*g.cell_width,g.top+(r+.975)*g.cell_height)
        return _cell_box(g,r,c)
    grid = tuple(tuple(_read_number(image,cell_box(r,c),f'cell ({r+1}, {c+1})',
                                   cell=True,allow_marked=allow_marked)
                       for c in range(g.columns)) for r in range(g.rows))
    rows = tuple(_read_number(image,
        (g.left-.80*g.cell_width, g.top+(r+.12)*g.cell_height,
         g.left-.04*g.cell_width, g.top+(r+.88)*g.cell_height),f'row {r+1} target')
        for r in range(g.rows))
    columns = tuple(_read_number(image,
        (g.left+(c+.12)*g.cell_width,g.top-.80*g.cell_height,
         g.left+(c+.88)*g.cell_width,g.top-.04*g.cell_height),f'column {c+1} target')
        for c in range(g.columns))
    try:
        puzzle = Puzzle(grid,rows,columns)
        if sum(rows) != sum(columns):
            raise ValueError('row and column target totals differ')
        return puzzle
    except ValueError as error:
        raise BoardReadError(f'Invalid board reading: {error}') from error


def marked_cells(image: Image.Image, g: BoardGeometry) -> set[tuple[int,int]]:
    marked = set()
    for r in range(g.rows):
        for c in range(g.columns):
            box = (g.left+(c+.025)*g.cell_width,g.top+(r+.025)*g.cell_height,
                   g.left+(c+.975)*g.cell_width,g.top+(r+.975)*g.cell_height)
            if any(component.right-component.left > g.cell_width*.65
                   and component.bottom-component.top > g.cell_height*.65
                   for component in _components(image,box)):
                marked.add((r,c))
    return marked
