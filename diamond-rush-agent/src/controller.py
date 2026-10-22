import time

import numpy as np
import pyautogui

import config
from level_reader import (
    DIAMOND,
    FLOOR,
    HOLE,
    PLAYER,
    ROCK,
    WALL,
    cell_features,
    find_cells,
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

# Tiempos de los movimientos: se ajustan en .env (ver config.py).

# Tiempo que se mantiene pulsada cada flecha.
KEY_HOLD = config.KEY_HOLD

# Veces que se pulsa una flecha antes de dar el movimiento por fallido.
MAX_PRESSES = config.MAX_PRESSES

# Segundos que se espera a que el jugador cambie de casilla.
MOVE_TIMEOUT = config.MOVE_TIMEOUT

# Segundos máximos esperando a que termine la animación.
SETTLE_TIMEOUT = config.SETTLE_TIMEOUT

POLL_INTERVAL = config.POLL_INTERVAL

# Tiempo sin cambios para dar una animación por terminada.
STILL_TIME = config.STILL_TIME

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

    Devuelve la captura en la que se vio el movimiento, o None
    si el tablero sigue igual: la tecla se perdió o el
    movimiento no es posible.
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
            return frame

    return None


def wait_for_change(grab, before, origin, target, offset=(0, 0)):
    """
    Espera a que cambie la casilla del jugador o la de destino
    (para el último paso, que entra en la salida). Devuelve
    False si en MOVE_TIMEOUT no cambió nada: la tecla se perdió.
    """

    deadline = time.monotonic() + MOVE_TIMEOUT

    while time.monotonic() < deadline:

        time.sleep(POLL_INTERVAL)

        frame = grab()

        if (
            cell_change(before, frame, origin, offset) > LEFT_CELL_CHANGE
            or cell_change(before, frame, target, offset) > LEFT_CELL_CHANGE
        ):
            return True

    return False


def wait_until_still(grab, cells, offset=(0, 0), previous=None):
    """
    Espera a que las casillas dejen de cambiar, para no
    pulsar la siguiente flecha en mitad de una animación
    (empujar una roca o abrir una puerta tarda más que caminar).

    previous: una captura reciente para empezar a comparar (se
    ahorra una captura). Devuelve la última captura, ya quieta.
    """

    deadline = time.monotonic() + SETTLE_TIMEOUT

    if previous is None:
        previous = grab()

    # Se compara contra la última captura en la que algo cambió, no
    # contra la anterior: así un movimiento lento, que cambia poco
    # entre captura y captura, no pasa por quieto. Y tiene que estar
    # así durante STILL_TIME, por rápido que se capture.
    quiet_since = time.monotonic()

    while time.monotonic() < deadline:

        time.sleep(POLL_INTERVAL)

        frame = grab()

        if any(
            cell_change(previous, frame, cell, offset) >= STILL_CHANGE
            for cell in cells
        ):
            previous = frame
            quiet_since = time.monotonic()
            continue

        if time.monotonic() - quiet_since >= STILL_TIME:
            return frame

    return grab()


def inside(image, cell, offset=(0, 0)):

    piece = view_cell(image, *cell, offset)

    return (
        cell[0] >= 0
        and cell[1] >= 0
        and piece.shape[0] > 0
        and piece.shape[1] > 0
    )


# Se apaga si un tramo con la flecha pulsada se queda corto: el
# juego no sigue moviendo al jugador, y probar en cada tramo solo
# haría perder tiempo. Vale para toda la sesión.
_hold_works = True


def walking_run(plan, index, pos, grid, rocks, holes, stop):
    """
    Cuántos movimientos desde plan[index] se pueden hacer
    manteniendo la flecha pulsada; 0 si no conviene.

    Solo un tramo recto por piso, diamantes o huecos ya
    rellenados, sin rocas, y que termina contra un muro: si
    la tecla se suelta un poco tarde, el jugador choca con el
    muro y no pasa nada. Si terminara en piso, se pasaría a la
    casilla siguiente, que el plan no tiene prevista.

    rocks, holes: rocas y huecos sin rellenar en este momento.
    stop: índice del plan donde termina la búsqueda del tramo.
    """

    move = plan[index]
    dr, dc = DELTAS[move]

    rows, cols = len(grid), len(grid[0])

    def inside_board(cell):
        return 0 <= cell[0] < rows and 0 <= cell[1] < cols

    def walkable(cell):

        if not inside_board(cell) or cell in rocks:
            return False

        symbol = grid[cell[0]][cell[1]]

        if symbol == HOLE:
            return cell not in holes

        return symbol in (FLOOR, DIAMOND, PLAYER)

    length = 0
    cell = pos

    while index + length < stop and plan[index + length] == move:

        nxt = (cell[0] + dr, cell[1] + dc)

        if not walkable(nxt):
            return 0

        length += 1
        cell = nxt

    if length < config.HOLD_MIN_RUN:
        return 0

    after = (cell[0] + dr, cell[1] + dc)

    if inside_board(after) and grid[after[0]][after[1]] != WALL:
        return 0

    return length


def hold_run(move, cells, grab):
    """
    Mantiene pulsada la flecha hasta que el jugador entra en la
    última casilla del tramo, y luego cuenta en pantalla hasta
    dónde llegó.

    cells: casillas del tramo, sin la de partida.
    Devuelve cuántas recorrió (puede ser menos si el juego no
    mueve al jugador mientras la tecla sigue pulsada).
    """

    before = grab()

    # Casillas del tramo en las que ya entró, y desde cuándo no
    # avanza: si no entra en la siguiente en MOVE_TIMEOUT, se
    # suelta la tecla (el juego no lo mueve, o algo lo bloquea).
    entered = 0
    progress_at = time.monotonic()

    pyautogui.keyDown(move)

    try:
        while entered < len(cells):

            time.sleep(POLL_INTERVAL)

            frame = grab()

            while (
                entered < len(cells)
                and cell_change(before, frame, cells[entered]) > LEFT_CELL_CHANGE
            ):
                entered += 1
                progress_at = time.monotonic()

            if time.monotonic() - progress_at > MOVE_TIMEOUT:
                break
    finally:
        pyautogui.keyUp(move)

    wait_until_still(grab, cells)

    frame = grab()

    # Las casillas de piso por las que pasó vuelven a verse como
    # antes; las que siguen a donde se detuvo no cambiaron nunca.
    # La última que cambió es donde está (o un diamante recogido
    # antes de ella, que también es parte del recorrido).
    reached = 0

    for number, cell in enumerate(cells, 1):
        if cell_change(before, frame, cell) > LEFT_CELL_CHANGE:
            reached = number

    return reached


def execute_plan(
    plan,
    start,
    grab,
    step_delay=config.STEP_DELAY,
    on_move=None,
    camera=None,
    ends_in_exit=True,
    grid=None,
    timings=None
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
    grid: tablero al empezar el plan. Con DR_HOLD_KEYS=1 permite
    recorrer los tramos rectos manteniendo la flecha pulsada.
    timings: lista a la que se agrega, por cada paso comprobado,
    (segundos hasta ver al jugador moverse, segundos hasta que
    la imagen quedó quieta), para saber dónde se va el tiempo.

    La ventana del juego debe tener el foco.
    Mover el mouse a una esquina de la pantalla aborta
    la ejecución (fail-safe de PyAutoGUI).
    """

    pos = start

    # Para mantener la flecha pulsada hay que saber cómo está el
    # tablero en cada momento: dónde quedan las rocas empujadas y
    # qué huecos se rellenaron.
    global _hold_works

    holding = (
        config.HOLD_KEYS
        and grid is not None
        and camera is None
    )

    if holding:
        rocks = set(find_cells(grid, ROCK))
        holes = set(find_cells(grid, HOLE))

    last = len(plan) - 1 if ends_in_exit else len(plan)

    # Índice donde mantener la flecha no funcionó: ahí se pulsa.
    no_hold = None

    # Última captura con el juego quieto. Sirve como "antes" del
    # siguiente movimiento y ahorra una captura por paso; se
    # descarta cuando algo pudo cambiar la pantalla desde entonces.
    still = None

    index = 0

    while index < len(plan):

        move = plan[index]

        dr, dc = DELTAS[move]

        run = 0

        if holding and _hold_works and index != no_hold:
            run = walking_run(plan, index, pos, grid, rocks, holes, last)

        if run:

            cells = [
                (pos[0] + dr * step, pos[1] + dc * step)
                for step in range(1, run + 1)
            ]

            still = None

            reached = hold_run(move, cells, grab)

            if reached < run:

                _hold_works = False

                print(
                    f"Con la flecha pulsada el jugador avanzó {reached} "
                    f"de {run} casillas: sigo con una pulsación por casilla."
                )

            if reached == 0:
                no_hold = index
                continue

            pos = cells[reached - 1]
            index += reached

            time.sleep(step_delay)

            # Ninguna casilla del tramo es una placa y detrás del
            # último hay un muro, pero se avisa igual que siempre.
            if on_move is not None and on_move(pos, (pos[0] + dr, pos[1] + dc)):
                return index, "interrupted"

            continue

        target = (pos[0] + dr, pos[1] + dc)
        beyond = (target[0] + dr, target[1] + dc)

        offset = camera.offset if camera is not None else (0, 0)

        if ends_in_exit and index == len(plan) - 1:
            # El último paso entra en la salida y el nivel cambia:
            # no se puede comprobar como los demás, pero sí que
            # pasó algo. Si la pulsación se pierde, el nivel no
            # termina y el agente lo daría por ganado.
            before = still if still is not None else grab()

            for _ in range(MAX_PRESSES):

                press(move)

                if wait_for_change(grab, before, pos, target, offset):
                    break

            time.sleep(step_delay)
            return len(plan), "done"

        before = still if still is not None else grab()

        pressed_at = time.perf_counter()

        for _ in range(MAX_PRESSES):

            press(move)

            moved = wait_for_move(grab, before, pos, target, offset, camera)

            if moved is not None:
                break

            # Solo se vuelve a pulsar si la tecla se perdió: ni la
            # casilla del jugador ni la de destino cambiaron. Si algo
            # cambió sin ser el movimiento esperado, el jugador no
            # está donde se cree; pulsar otra vez lo alejaría más.
            # Mejor parar y volver a leer el tablero.
            now = grab()

            if (
                cell_change(before, now, pos, offset) > LEFT_CELL_CHANGE
                or cell_change(before, now, target, offset) > LEFT_CELL_CHANGE
            ):
                return index, "blocked"

        else:
            return index, "blocked"

        moved_at = time.perf_counter()

        still = wait_until_still(
            grab,
            [
                cell
                for cell in (pos, target, beyond)
                if inside(before, cell, offset)
            ],
            offset,
            moved
        )

        if timings is not None:
            timings.append((
                moved_at - pressed_at,
                time.perf_counter() - moved_at
            ))

        if camera is not None:
            camera.update(still)
            still = None

        time.sleep(step_delay)

        if holding and target in rocks:

            # El movimiento empujó una roca: o quedó más allá, o
            # cayó en un hueco y lo rellenó.
            rocks.discard(target)

            if beyond in holes:
                holes.discard(beyond)
            else:
                rocks.add(beyond)

        pos = target

        index += 1

        if on_move is not None:

            started = time.perf_counter()

            if on_move(pos, beyond):
                return index, "interrupted"

            # Si on_move hizo algo (pisó una placa y esperó a ver
            # las rejas), la pantalla pudo cambiar: la captura
            # guardada ya no vale. Si no hizo nada, vuelve al
            # instante.
            if time.perf_counter() - started > 0.005:
                still = None

    return len(plan), "done"
