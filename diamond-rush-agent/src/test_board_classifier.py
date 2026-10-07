import cv2

from cell_classifier import load_templates
from board_classifier import (
    classify_board,
    print_board
)


image = cv2.imread(
    "../screenshots/game_area.png"
)


templates = load_templates(
    "../assets/templates/cells"
)


print(
    "Templates cargados:",
    templates.keys()
)


board = classify_board(
    image,
    templates
)


print_board(
    board
)