import argparse
import csv
from datetime import datetime
from pathlib import Path

import cv2

from capture import capture_screen
from game_detector import locate_game_area, crop_game


# ----------------------------------------------------
# Configuración de la cuadrícula validada hasta ahora
# ----------------------------------------------------

GRID_X0 = 0
GRID_Y0 = 125

CELL_WIDTH = 42
CELL_HEIGHT = 43


# ----------------------------------------------------
# Rutas del proyecto
# ----------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_DIR = PROJECT_ROOT / "dataset"
RAW_DIR = DATASET_DIR / "raw"

ANCHOR_TEMPLATE = (
    PROJECT_ROOT
    / "assets"
    / "templates"
    / "game_anchor.png"
)


def extract_cells(game_image):
    """
    Divide el tablero en celdas.

    Devuelve:
    [
        (row, col, cell_image),
        ...
    ]
    """

    cells = []

    height, width = game_image.shape[:2]

    row = 0
    y = GRID_Y0

    while y + CELL_HEIGHT <= height:

        col = 0
        x = GRID_X0

        while x + CELL_WIDTH <= width:

            cell = game_image[
                y:y + CELL_HEIGHT,
                x:x + CELL_WIDTH
            ]

            cells.append(
                (
                    row,
                    col,
                    cell
                )
            )

            col += 1
            x += CELL_WIDTH

        row += 1
        y += CELL_HEIGHT

    return cells


def collect_level(level):
    """
    Captura el juego y almacena todas
    las celdas del nivel actual.
    """

    print("Capturando pantalla...")

    screen = capture_screen()

    game_area = locate_game_area(
        screen,
        str(ANCHOR_TEMPLATE)
    )

    if game_area is None:
        print("ERROR: no se encontró Diamond Rush.")
        return

    print(
        f"Juego localizado con confianza "
        f"{game_area['confidence']:.4f}"
    )

    game = crop_game(
        screen,
        game_area
    )

    # Carpeta del nivel
    level_dir = (
        RAW_DIR
        / f"level_{level:03d}"
    )

    level_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # Para conservar también la captura completa del juego
    cv2.imwrite(
        str(level_dir / "game_area.png"),
        game
    )

    cells = extract_cells(game)

    metadata_path = (
        level_dir
        / "metadata.csv"
    )

    with open(
        metadata_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

        writer.writerow(
            [
                "file",
                "level",
                "row",
                "col"
            ]
        )

        for row, col, cell in cells:

            filename = (
                f"r{row:02d}_c{col:02d}.png"
            )

            output_path = (
                level_dir
                / filename
            )

            cv2.imwrite(
                str(output_path),
                cell
            )

            writer.writerow(
                [
                    filename,
                    level,
                    row,
                    col
                ]
            )

    print()
    print(
        f"{len(cells)} celdas guardadas."
    )

    print(
        f"Dataset: {level_dir}"
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--level",
        type=int,
        required=True,
        help="Número del nivel actual"
    )

    args = parser.parse_args()

    collect_level(
        args.level
    )


if __name__ == "__main__":
    main()