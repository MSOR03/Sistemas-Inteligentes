import cv2
import numpy as np
import matplotlib.pyplot as plt

from grid_detector import detect_grid_lines


image = cv2.imread(
    "../screenshots/game_area.png"
)

vertical, horizontal = detect_grid_lines(
    image,
    board_top=120
)


# -----------------------------
# Bordes verticales
# -----------------------------

plt.figure(figsize=(12, 4))

plt.plot(vertical)

plt.title(
    "Energía de bordes verticales"
)

plt.xlabel("X")

plt.ylabel("Intensidad")

plt.grid()

plt.savefig(
    "../screenshots/grid_vertical.png"
)

plt.close()


# -----------------------------
# Bordes horizontales
# -----------------------------

plt.figure(figsize=(12, 4))

plt.plot(horizontal)

plt.title(
    "Energía de bordes horizontales"
)

plt.xlabel("Y relativo al tablero")

plt.ylabel("Intensidad")

plt.grid()

plt.savefig(
    "../screenshots/grid_horizontal.png"
)

plt.close()

print(
    "Gráficas generadas correctamente."
)