from dataclasses import dataclass
from statistics import median

from PIL import Image, ImageChops


class BoardReadError(ValueError):
    """The screenshot cannot be read confidently as a fresh Cross Sums board."""


@dataclass(frozen=True, slots=True)
class BoardGeometry:
    left: float
    top: float
    cell_width: float
    cell_height: float
    rows: int
    columns: int

    @property
    def right(self) -> float:
        return self.left + self.cell_width * self.columns

    @property
    def bottom(self) -> float:
        return self.top + self.cell_height * self.rows

    def cell_center(self, row: int, column: int) -> tuple[float, float]:
        return (self.left + (column + .5) * self.cell_width,
                self.top + (row + .5) * self.cell_height)

    def pencil_center(self) -> tuple[float, float]:
        return (self.left + self.right) / 2, self.bottom + self.cell_height * 1.42

    def eraser_center(self) -> tuple[float, float]:
        x, y = self.pencil_center()
        return x - self.cell_width * 1.05, y


def _cell_regions(image: Image.Image) -> list[tuple[float, float, float, float]]:
    """Segment the dark blue cell interiors, regardless of their printed digits.

    Work on a bounded-resolution mask. Each filled cell is a connected region;
    white text forms holes, so missed or unreadable text does not affect bounds.
    This palette is specific to the supplied Offline Games dark theme.
    """
    scale = min(1.0, 850 / image.width)
    small = image.resize((round(image.width * scale), round(image.height * scale)))
    red, green, blue = small.convert('RGB').split()
    mask = ImageChops.multiply(red.point(lambda v: 255 if v < 14 else 0),
                              green.point(lambda v: 255 if v < 14 else 0))
    mask = ImageChops.multiply(mask, blue.point(lambda v: 255 if v < 26 else 0))
    mask = ImageChops.multiply(mask, ImageChops.subtract(blue, red).point(
        lambda v: 255 if v >= 3 else 0))
    width, height = mask.size
    pixels = bytearray(mask.tobytes())
    result = []
    for start in range(len(pixels)):
        if not pixels[start]:
            continue
        pixels[start] = 0
        stack = [start]
        area = 0
        x0 = x1 = start % width
        y0 = y1 = start // width
        while stack:
            position = stack.pop()
            x, y = position % width, position // width
            area += 1
            x0, x1 = min(x0, x), max(x1, x)
            y0, y1 = min(y0, y), max(y1, y)
            neighbors = (position - 1 if x else -1,
                         position + 1 if x + 1 < width else -1,
                         position - width, position + width)
            for neighbor in neighbors:
                if 0 <= neighbor < len(pixels) and pixels[neighbor]:
                    pixels[neighbor] = 0
                    stack.append(neighbor)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if w > 15 and h > 15 and .85 < w / h < 1.15 and area / (w * h) > .60:
            result.append((x0 / scale, y0 / scale, w / scale, h / scale))
    return result


def _centers(values: list[float], tolerance: float) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or value - median(clusters[-1]) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [median(cluster) for cluster in clusters]


def locate_grid(image: Image.Image) -> BoardGeometry:
    regions = _cell_regions(image)
    candidates = set()
    seen_groups = set()
    for _, _, width, height in regions:
        group = [r for r in regions
                 if abs(r[2] - width) < width * .08 and abs(r[3] - height) < height * .08]
        key = tuple(group)
        if key in seen_groups:
            continue
        seen_groups.add(key)
        xs = _centers([x + w / 2 for x, y, w, h in group], width * .15)
        ys = _centers([y + h / 2 for x, y, w, h in group], height * .15)
        if not (3 <= len(xs) <= 12 and 3 <= len(ys) <= 12):
            continue
        if len(group) != len(xs) * len(ys):
            continue
        dx = median(b - a for a, b in zip(xs, xs[1:]))
        dy = median(b - a for a, b in zip(ys, ys[1:]))
        if not (width <= dx < width * 1.25 and height <= dy < height * 1.25):
            continue
        if any(abs((b - a) - dx) > dx * .04 for a, b in zip(xs, xs[1:])):
            continue
        if any(abs((b - a) - dy) > dy * .04 for a, b in zip(ys, ys[1:])):
            continue
        occupied = {(min(range(len(xs)), key=lambda i: abs(xs[i] - (x + w / 2))),
                     min(range(len(ys)), key=lambda i: abs(ys[i] - (y + h / 2))))
                    for x, y, w, h in group}
        if len(occupied) != len(xs) * len(ys):
            continue
        candidates.add(BoardGeometry(xs[0] - dx / 2, ys[0] - dy / 2,
                                     dx, dy, len(ys), len(xs)))
    if len(candidates) != 1:
        raise BoardReadError('No single complete Cross Sums grid found. Open a fresh board in the dark theme.')
    return candidates.pop()
