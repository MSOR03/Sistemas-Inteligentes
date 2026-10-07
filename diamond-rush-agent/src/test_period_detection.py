import cv2
import numpy as np

from grid_detector import (
    edge_energies,
    estimate_period,
    estimate_phase
)


BOARD_TOP = 120


image = cv2.imread(
    "../screenshots/game_area.png"
)

vertical, horizontal = edge_energies(
    image,
    board_top=BOARD_TOP
)


# ----------------------
# Periodicidad
# ----------------------

period_x, scores_x = estimate_period(
    vertical
)

period_y, scores_y = estimate_period(
    horizontal
)


print(
    f"Periodo horizontal (ancho celda): {period_x}"
)

print(
    f"Periodo vertical (alto celda): {period_y}"
)


# ----------------------
# Fase
# ----------------------

phase_x = estimate_phase(
    vertical,
    period_x
)

phase_y = estimate_phase(
    horizontal,
    period_y
)


print(
    f"Fase X: {phase_x}"
)

print(
    f"Fase Y relativa: {phase_y}"
)


# ----------------------
# Líneas estimadas
# ----------------------

x_lines = np.arange(
    phase_x,
    image.shape[1],
    period_x
)

y_lines_relative = np.arange(
    phase_y,
    image.shape[0] - BOARD_TOP,
    period_y
)

y_lines = (
    y_lines_relative + BOARD_TOP
)


print(
    "Líneas X:",
    x_lines
)

print(
    "Líneas Y:",
    y_lines
)


# ----------------------
# Dibujar resultado
# ----------------------

debug = image.copy()


for x in x_lines:

    cv2.line(
        debug,
        (int(x), BOARD_TOP),
        (int(x), image.shape[0]),
        (0, 255, 0),
        1
    )


for y in y_lines:

    cv2.line(
        debug,
        (0, int(y)),
        (image.shape[1], int(y)),
        (0, 0, 255),
        1
    )


cv2.imwrite(
    "../screenshots/grid_detected.png",
    debug
)

print(
    "Resultado guardado en grid_detected.png"
)