import time

import numpy as np
import pyautogui

from level_reader import (
    cell_features,
    view_cell
)


# PyAutoGUI añade una pausa propia tras cada llamada;
# el ritmo lo controla únicamente step_delay.
pyautogui.PAUSE = 0


DELTAS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1)
}

# Tiempo que se mantiene pulsada cada flecha.
KEY_HOLD = 0.06

# Veces que se pulsa una flecha antes de dar el movimiento por fallido.
MAX_PRESSES = 3

# Segundos que se espera a que el jugador cambie de casilla.
MOVE_TIMEOUT = 1.0

# Segundos máximos esperando a que termine la animación.
SETTLE_TIMEOUT = 1.0

POLL_INTERVAL = 0.03

# Cambio mínimo (diferencia media de color en la miniatura)
# para aceptar que el jugador salió de su casilla y entró en
# la siguiente. La animación de reposo queda muy por debajo.
LEFT_CELL_CHANGE = 10

# La casilla de destino debe cambiar casi tanto como la de
# origen. Si el jugador choca (una reja cerrada, por ejemplo)
# gira y su sombrero asoma en la casilla vecina, pero ese
# cambio es mucho menor que el de la casilla que ocupa.
ENTERED_CELL_RATIO = 0.6

# Dos capturas seguidas más parecidas que esto: ya no hay animación.
STILL_CHANGE = 1.5


def press(move):

    pyautogui.keyDown(move)
    time.sleep(KEY_HOLD)
    pyautogui.keyUp(move)


def cell_change(image_a, image_b, cell, offset=(0, 0), offset_b=None):
    """
    offset_b: desplazamiento de la cámara en image_b, si se
    movió desde image_a (por defecto, el mismo).
    """

    if offset_b is None:
        offset_b = offset

    # En la fila tapada por el HUD solo se compara la franja
    # visible: con la celda entera el HUD diluye el cambio y
    # un paso hacia esa fila parece no haber ocurrido.
    piece_a = view_cell(image_a, *cell, offset)
    piece_b = view_cell(image_b, *cell, offset_b)

    if piece_a.size == 0 or piece_b.size == 0:
        return 0.0

    return float(
        np.abs(
            cell_features(piece_a)
            - cell_features(piece_b)
        ).mean()
    )


def wait_for_move(
    grab,
    before,
    origin,
    target,
    offset=(0, 0),
    camera=None
):
    """
    Espera a que el jugador pase de origin a target.

    camera: mapa del nivel si la cámara puede moverse. Si
    sigue al jugador, en pantalla el jugador no cambia de
    lugar: hay que comparar cada casilla del nivel donde
    está ahora, no donde estaba.

    Devuelve False si el tablero sigue igual: la tecla
    se perdió o el movimiento no es posible.
    """

    deadline = time.monotonic() + MOVE_TIMEOUT

    while time.monotonic() < deadline:

        time.sleep(POLL_INTERVAL)

        frame = grab()

        now = offset if camera is None else camera.offset_of(frame)

        left = cell_change(before, frame, origin, offset, now)
        entered = cell_change(before, frame, target, offset, now)

        if (
            left > LEFT_CELL_CHANGE
            and entered > LEFT_CELL_CHANGE
            and entered > ENTERED_CELL_RATIO * left
        ):
            return True

    return False


def wait_until_still(grab, cells, offset=(0, 0)):
    """
    Espera a que las casillas dejen de cambiar, para no
    pulsar la siguiente flecha en mitad de una animación
    (empujar una roca o abrir una puerta tarda más que caminar).
    """

    deadline = time.monotonic() + SETTLE_TIMEOUT

    previous = grab()

    while time.monotonic() < deadline:

        time.sleep(POLL_INTERVAL)

        frame = grab()

        if all(
            cell_change(previous, frame, cell, offset) < STILL_CHANGE
            for cell in cells
        ):
            return

        previous = frame


def inside(image, cell, offset=(0, 0)):

    piece = view_cell(image, *cell, offset)

    return (
        cell[0] >= 0
        and cell[1] >= 0
        and piece.shape[0] > 0
        and piece.shape[1] > 0
    )


def execute_plan(
    plan,
    start,
    grab,
    step_delay=0.05,
    on_move=None,
    camera=None,
    ends_in_exit=True
):
    """
    Envía los movimientos al juego con las flechas del teclado,
    comprobando en pantalla que cada uno se realizó antes de
    enviar el siguiente.

    start: casilla (fila, columna) del jugador.
    grab:  función que devuelve la imagen actual del juego.

    on_move: función (casilla del jugador, casilla siguiente
    en la misma dirección) llamada tras cada movimiento; si
    devuelve True, la ejecución se detiene ahí.

    Devuelve (movimientos completados, estado). El estado es
    "done", "blocked" (el siguiente movimiento no tuvo efecto)
    o "interrupted" (on_move pidió parar).

    camera: mapa del nivel (stitcher.LevelMap) si el nivel no
    cabe en pantalla. Las casillas se buscan en la vista con su
    desplazamiento, y tras cada paso se le muestra la captura
    para seguir a la cámara.
    ends_in_exit: el último paso entra en la salida y no se
    comprueba (al explorar sí hay que comprobarlo).

    La ventana del juego debe tener el foco.
    Mover el mouse a una esquina de la pantalla aborta
    la ejecución (fail-safe de PyAutoGUI).
    """

    pos = start

    for index, move in enumerate(plan):

        dr, dc = DELTAS[move]

        target = (pos[0] + dr, pos[1] + dc)
        beyond = (target[0] + dr, target[1] + dc)

        offset = camera.offset if camera is not None else (0, 0)

        if ends_in_exit and index == len(plan) - 1:
            # El último paso entra en la salida y el nivel
            # cambia: no queda tablero que comprobar.
            press(move)
            time.sleep(step_delay)
            return len(plan), "done"

        before = grab()

        for _ in range(MAX_PRESSES):

            press(move)

            if wait_for_move(grab, before, pos, target, offset, camera):
                break

        else:
            return index, "blocked"

        wait_until_still(
            grab,
            [
                cell
                for cell in (pos, target, beyond)
                if inside(before, cell, offset)
            ],
            offset
        )

        if camera is not None:
            camera.update(grab())

        time.sleep(step_delay)

        pos = target

        if on_move is not None and on_move(pos, beyond):
            return index + 1, "interrupted"

    return len(plan), "done"
