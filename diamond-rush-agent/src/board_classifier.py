import cv2
import numpy as np

from cell_classifier import (
    load_templates,
    classify_cell
)


X0 = 0
Y0 = 125

CELL_WIDTH = 42
CELL_HEIGHT = 43


SYMBOLS = {
    "WALL": "#",
    "FLOOR": ".",
    "DIAMOND": "D",
    "PLAYER": "P"
}


def classify_board(
    image,
    templates
):

    height, width = image.shape[:2]

    board = []

    row = 0
    y = Y0

    while y + CELL_HEIGHT <= height:

        board_row = []

        col = 0
        x = X0

        while x + CELL_WIDTH <= width:

            cell = image[
                y:y + CELL_HEIGHT,
                x:x + CELL_WIDTH
            ]

            label, score, scores = classify_cell(
                cell,
                templates
            )

            board_row.append(
                (
                    label,
                    score
                )
            )

            col += 1
            x += CELL_WIDTH

        board.append(
            board_row
        )

        row += 1
        y += CELL_HEIGHT

    return board


def print_board(board):

    print()

    for row in board:

        line = ""

        for label, score in row:

            symbol = SYMBOLS.get(
                label,
                "?"
            )

            line += symbol + " "

        print(line)

    print()