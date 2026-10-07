import cv2
import os

from capture import capture_screen
from game_detector import (
    locate_game_area,
    crop_game
)


def main():

    os.makedirs(
        "../screenshots",
        exist_ok=True
    )

    image = capture_screen()

    game_area = locate_game_area(
        image,
        "../assets/templates/game_anchor.png"
    )

    if game_area is None:
        print("No se encontró Diamond Rush.")
        return

    print("Juego encontrado:")
    print(
        f"x={game_area['x']}, "
        f"y={game_area['y']}, "
        f"w={game_area['width']}, "
        f"h={game_area['height']}"
    )

    print(
        f"Confianza: "
        f"{game_area['confidence']:.4f}"
    )

    game = crop_game(
        image,
        game_area
    )

    cv2.imwrite(
        "../screenshots/game_area.png",
        game
    )

    # También dibujamos el rectángulo
    debug = image.copy()

    x = game_area["x"]
    y = game_area["y"]
    w = game_area["width"]
    h = game_area["height"]

    cv2.rectangle(
        debug,
        (x, y),
        (x+w, y+h),
        (0, 255, 0),
        3
    )

    cv2.imwrite(
        "../screenshots/game_area_debug.png",
        debug
    )

    print(
        "Se generaron game_area.png "
        "y game_area_debug.png"
    )


if __name__ == "__main__":
    main()