import cv2
import os

from capture import capture_screen
from game_detector import locate_anchor


def main():

    os.makedirs("../screenshots", exist_ok=True)

    image = capture_screen()

    result = locate_anchor(
        image,
        "../assets/templates/game_anchor.png"
    )

    if result is None:
        print("No se encontró el juego.")
        return

    x = result["x"]
    y = result["y"]
    w = result["width"]
    h = result["height"]

    confidence = result["confidence"]

    print("Ancla encontrada.")
    print(f"x = {x}")
    print(f"y = {y}")
    print(f"confianza = {confidence:.4f}")

    cv2.rectangle(
        image,
        (x, y),
        (x + w, y + h),
        (0, 255, 0),
        3
    )

    cv2.imwrite(
        "../screenshots/template_detection.png",
        image
    )


if __name__ == "__main__":
    main()