from PIL import Image, ImageDraw

from meowdoku.solver import solve_unique
from meowdoku.vision import read_image

from test_meowdoku_solver import LIVE_REGIONS


PALETTE = {
    "M": (186, 55, 140),
    "G": (103, 160, 54),
    "B": (46, 101, 177),
    "Y": (190, 147, 14),
    "C": (33, 131, 143),
    "O": (194, 96, 43),
    "E": (20, 142, 77),
    "P": (117, 70, 180),
}


def board_image(
    *,
    cat: tuple[int, int] | None = None,
    marked_empty: tuple[int, int] | None = None,
) -> Image.Image:
    image = Image.new("RGB", (780, 980), (17, 19, 28))
    draw = ImageDraw.Draw(image)
    left, top, pitch, inset = 62, 110, 82, 4
    for row, regions in enumerate(LIVE_REGIONS):
        for column, region in enumerate(regions):
            x0 = left + column * pitch + inset
            y0 = top + row * pitch + inset
            x1 = left + (column + 1) * pitch - inset
            y1 = top + (row + 1) * pitch - inset
            draw.rounded_rectangle((x0, y0, x1, y1), radius=8, fill=PALETTE[region])
    if cat is not None:
        row, column = cat
        cx = left + (column + 0.5) * pitch
        cy = top + (row + 0.5) * pitch
        draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(30, 30, 30))
        draw.ellipse((cx - 13, cy - 10, cx + 13, cy + 16), fill=(235, 235, 235))
        draw.ellipse((cx - 9, cy - 5, cx - 4, cy), fill=(20, 20, 20))
        draw.ellipse((cx + 4, cy - 5, cx + 9, cy), fill=(20, 20, 20))
    if marked_empty is not None:
        row, column = marked_empty
        cx = left + (column + 0.5) * pitch
        cy = top + (row + 0.5) * pitch
        draw.line((cx - 20, cy - 20, cx + 20, cy + 20), fill="white", width=9)
        draw.line((cx + 20, cy - 20, cx - 20, cy + 20), fill="white", width=9)
    return image


def test_reads_regions_and_geometry_from_colored_cells() -> None:
    detected = read_image(board_image())
    assert detected.geometry.size == 8
    assert detected.puzzle.size == 8
    assert detected.puzzle.cats == ()
    assert solve_unique(detected.puzzle).selected_cells()[0] == (0, 7)


def test_recognizes_a_large_central_cat_icon() -> None:
    detected = read_image(board_image(cat=(0, 7)))
    assert detected.puzzle.cats == ((0, 7),)
    assert (0, 7) in solve_unique(detected.puzzle).selected_cells()


def test_recognizes_an_x_as_known_empty() -> None:
    detected = read_image(board_image(marked_empty=(0, 0)))
    assert detected.puzzle.known_empty == ((0, 0),)
    assert (0, 0) not in solve_unique(detected.puzzle).selected_cells()
