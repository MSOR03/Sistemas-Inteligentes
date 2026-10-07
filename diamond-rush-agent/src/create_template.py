import cv2
import pyautogui
import numpy as np
import os


def main():

    os.makedirs("../assets/templates", exist_ok=True)

    screenshot = pyautogui.screenshot()
    image = np.array(screenshot)
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    print("Selecciona únicamente el engranaje del juego.")
    print("Presiona ENTER cuando termines.")

    roi = cv2.selectROI(
        "Seleccionar ancla",
        image,
        showCrosshair=True,
        fromCenter=False
    )

    x, y, w, h = roi

    if w == 0 or h == 0:
        print("No se seleccionó ninguna región.")
        return

    template = image[
        y:y+h,
        x:x+w
    ]

    cv2.imwrite(
        "../assets/templates/game_anchor.png",
        template
    )

    cv2.destroyAllWindows()

    print("Template guardado correctamente.")


if __name__ == "__main__":
    main()