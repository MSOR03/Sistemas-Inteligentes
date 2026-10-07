import cv2
import numpy as np


def edge_energies(game_image, board_top=120):
    """
    Calcula energía de bordes verticales y horizontales.
    """

    board = game_image[board_top:, :]

    gray = cv2.cvtColor(
        board,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.GaussianBlur(
        gray,
        (3, 3),
        0
    )

    grad_x = cv2.Sobel(
        gray,
        cv2.CV_64F,
        1,
        0,
        ksize=3
    )

    grad_y = cv2.Sobel(
        gray,
        cv2.CV_64F,
        0,
        1,
        ksize=3
    )

    vertical_energy = np.sum(
        np.abs(grad_x),
        axis=0
    )

    horizontal_energy = np.sum(
        np.abs(grad_y),
        axis=1
    )

    return vertical_energy, horizontal_energy


def estimate_period(
    signal,
    min_period=30,
    max_period=55
):
    """
    Estima la periodicidad dominante mediante autocorrelación.
    """

    signal = signal.astype(float)

    # quitar media
    signal = signal - np.mean(signal)

    scores = []

    periods = range(
        min_period,
        max_period + 1
    )

    for lag in periods:

        a = signal[:-lag]
        b = signal[lag:]

        score = np.sum(a * b)

        scores.append(score)

    best_index = np.argmax(scores)

    best_period = list(periods)[best_index]

    return best_period, np.array(scores)


def estimate_phase(signal, period, window=4):
    """
    Estima el origen de la cuadrícula.

    En lugar de evaluar un único píxel,
    suma energía en una pequeña banda alrededor
    de cada posición periódica.
    """

    signal = signal.astype(float)

    best_phase = 0
    best_score = -np.inf

    n = len(signal)

    for phase in range(period):

        score = 0

        for pos in range(phase, n, period):

            start = max(0, pos - window)
            end = min(n, pos + window + 1)

            # Promedio local en torno al borde
            score += np.mean(signal[start:end])

        if score > best_score:
            best_score = score
            best_phase = phase

    return best_phase