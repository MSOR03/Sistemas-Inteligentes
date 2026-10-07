import os
import cv2

from capture import capture_screen
from game_detector import detect_game_candidates


def main():

    os.makedirs(
        "../screenshots",
        exist_ok=True
    )

    print("Capturando pantalla...")

    image = capture_screen()

    candidates = detect_game_candidates(image)

    print(
        f"Se encontraron {len(candidates)} candidatos."
    )

    # Dibujar máximo los 15 más grandes
    for i, candidate in enumerate(
        candidates[:15]
    ):

        x, y, w, h, area = candidate

        print(
            f"{i}: "
            f"x={x}, y={y}, "
            f"w={w}, h={h}, "
            f"area={area}"
        )

        # Rectángulo
        cv2.rectangle(
            image,
            (x, y),
            (x + w, y + h),
            (0, 255, 0),
            3
        )

        # Número del candidato
        cv2.putText(
            image,
            str(i),
            (x + 5, y + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

    output_path = "../screenshots/detection_test.png"

    cv2.imwrite(
        output_path,
        image
    )

    print(
        f"Resultado guardado en: {output_path}"
    )


if __name__ == "__main__":
    main()