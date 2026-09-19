from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from cross_sums.vision import BoardReadError, read_screenshot
from cross_sums.solver import solve_unique, verify_solution


FIXTURES = Path(__file__).parent / 'fixtures'
EXPECTED = {
    3: (
        ((4,5,7,3,4,6,2),(4,6,4,4,4,8,9),(7,7,7,4,2,6,3),
         (3,4,1,8,3,7,9),(7,8,8,4,7,2,4),(3,9,4,9,6,5,5),(8,9,4,6,9,3,6)),
        (11,19,33,10,8,9,22), (10,44,11,10,6,22,9)),
    4: (
        ((9,2,4,1,8,5,4),(2,9,6,8,5,8,8),(2,2,8,2,7,8,8),
         (1,6,2,2,2,5,7),(3,7,8,7,2,5,2),(8,5,4,8,2,7,5),(9,5,6,8,2,6,3)),
        (11,37,10,3,23,16,14), (11,16,10,26,7,27,17)),
    5: (
        ((2,8,4,4,9,5,6),(4,8,1,5,9,7,2),(4,8,7,3,5,5,8),
         (5,8,5,8,7,5,4),(8,9,5,5,3,4,9),(9,6,9,7,4,3,7),(2,6,9,9,5,4,3)),
        (19,9,30,13,14,11,2), (6,41,18,3,4,5,21)),
    7: (
        (
            (1,7,4,1,6,2,2,4),
            (8,2,9,7,8,7,9,6),
            (5,7,4,1,6,1,5,3),
            (2,3,4,3,4,7,8,6),
            (6,2,4,9,6,2,5,7),
            (6,1,1,2,9,3,3,5),
            (1,5,9,8,4,4,6,9),
            (2,1,9,4,8,8,9,2),
        ),
        (3,15,14,23,17,21,5,4),
        (9,12,9,27,10,5,13,17),
    ),
}


class NoTextOCR:
    def recognize_text(self, *_args):
        raise AssertionError('Board reading must not depend on Vision OCR')


@pytest.mark.parametrize('level', [3,4,5])
@pytest.mark.parametrize('scale', [.5,.75,1,1.4])
def test_real_boards_read_without_any_text_ocr(level, scale, tmp_path):
    with Image.open(FIXTURES / f'level-{level}.png') as im:
        resized = im.resize((round(im.width*scale), round(im.height*scale)))
        canvas = Image.new('RGB', (resized.width+130, resized.height+180), '#20252a')
        canvas.paste(resized,(57,83))
        path=tmp_path/'board.png'
        canvas.save(path)
    detected=read_screenshot(NoTextOCR(),path)
    grid,rows,columns=EXPECTED[level]
    assert detected.puzzle.grid==grid
    assert detected.puzzle.row_targets==rows
    assert detected.puzzle.column_targets==columns
    assert verify_solution(detected.puzzle,solve_unique(detected.puzzle))


def test_missing_cell_is_rejected(tmp_path):
    original=read_screenshot(NoTextOCR(),FIXTURES/'level-5.png')
    g=original.geometry
    with Image.open(FIXTURES/'level-5.png') as im:
        drawing=ImageDraw.Draw(im)
        x,y=g.cell_center(0,0)
        drawing.rectangle((x-g.cell_width*.35,y-g.cell_height*.35,
                           x+g.cell_width*.35,y+g.cell_height*.35),fill=(6,6,12))
        path=tmp_path/'missing.png';im.save(path)
    with pytest.raises(BoardReadError):
        read_screenshot(NoTextOCR(),path)


def test_reader_adapts_to_eight_by_eight_board(tmp_path):
    detected = read_screenshot(NoTextOCR(), FIXTURES / "level-7.png")
    grid, rows, columns = EXPECTED[7]

    assert detected.puzzle.rows == 8
    assert detected.puzzle.columns == 8
    assert detected.puzzle.grid == grid
    assert detected.puzzle.row_targets == rows
    assert detected.puzzle.column_targets == columns
    assert verify_solution(detected.puzzle, solve_unique(detected.puzzle))


def test_non_board_is_rejected(tmp_path):
    path=tmp_path/'menu.png'
    Image.new('RGB',(900,1000),'#0f1012').save(path)
    with pytest.raises(BoardReadError):
        read_screenshot(NoTextOCR(),path)
