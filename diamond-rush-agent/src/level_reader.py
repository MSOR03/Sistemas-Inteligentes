import cv2
import numpy as np

from board_classifier import (
    X0,
    Y0,
    CELL_WIDTH,
    CELL_HEIGHT
)


# ----------------------------------------------------
# Símbolos del tablero lógico
# ----------------------------------------------------

WALL = "#"
FLOOR = "."
DIAMOND = "D"
PLAYER = "P"
EXIT = "E"
LAVA = "L"
SPIKE = "S"
KEY = "K"
DOOR = "G"
ROCK = "R"
HOLE = "H"
PLATE = "O"
GATE = "B"
RAISED = "X"

# Estatua dorada: meta del nivel, como la salida,
# pero no exige recoger los diamantes.
CHECKPOINT = "C"

# Hueco ya rellenado con una roca: el clasificador
# lo distingue, pero en el tablero es piso normal.
FILLED = "f"
UNKNOWN = "?"

# El prefijo del nombre del template define la clase:
# wall_03.png -> WALL, key_01.png -> KEY, ...
SYMBOLS = {
    "WALL": WALL,
    "FLOOR": FLOOR,
    "DIAMOND": DIAMOND,
    "PLAYER": PLAYER,
    "EXIT": EXIT,
    "LAVA": LAVA,
    "SPIKE": SPIKE,
    "KEY": KEY,
    "DOOR": DOOR,
    "ROCK": ROCK,
    "PLATE": PLATE,
    "GATE": GATE,
    "CHECKPOINT": CHECKPOINT,
    "FILLED": FILLED
}


# ----------------------------------------------------
# Geometría del tablero
# ----------------------------------------------------

# La primera fila del tablero queda debajo del HUD: solo se
# ve su franja inferior. Casi siempre es muro, pero algunos
# niveles tienen ahí un pasillo con diamantes.
GRID_Y0 = Y0 - CELL_HEIGHT

# Primera línea visible de las celdas de esa fila.
TOP_ROW_VISIBLE_FROM = 21

# Lo único que se intenta distinguir en la fila tapada
# (los huecos se detectan aparte, ver TOP_ROW_HOLE_GRAY_PIXELS).
TOP_ROW_SYMBOLS = (WALL, FLOOR, DIAMOND, ROCK)

# En la fila tapada solo se cuentan los grises de la franja
# visible: las hojas del HUD sí son grisáceas. Hueco >= 241,
# piso <= 0 en esa franja.
TOP_ROW_HOLE_GRAY_PIXELS = 120


# ----------------------------------------------------
# Parámetros del clasificador
# ----------------------------------------------------

FEATURE_SIZE = 8

# Distancia de color máxima para aceptar un template.
# En los niveles del dataset la peor celda correcta da ~30.
UNKNOWN_DISTANCE = 38

# Una celda desconocida pero muy clara es un muro
# con una decoración que no está en los templates.
WALL_BRIGHTNESS = 140

# Cantidad de píxeles de "agujeros" a partir de la cual
# un piso se considera trampa de púas (piso <= 66, púas >= 115).
SPIKE_DOTS = 90

# Cantidad de píxeles grisáceos (el fondo del hueco) a partir
# de la cual un piso se considera hueco (resto <= 102, huecos >= 271).
# Los huecos no usan templates: se parecen demasiado al
# borde superior de la lava en la miniatura de color.
HOLE_GRAY_PIXELS = 180

# Rango de píxeles grisáceos que debe tener una celda para
# aceptar ciertas clases. En la miniatura de color una reja
# se confunde con piso en sombra, y una placa con la salida:
# las rejas tienen >= 757 grises, la salida >= 384, las
# placas <= 45 y el piso <= 133.
GATE_GRAY_PIXELS = 600

GRAY_RANGE = {
    GATE: (GATE_GRAY_PIXELS, float("inf")),
    PLATE: (0, 150)
}

# Las púas ya activadas (levantadas) son puntas gris claro
# sobre el piso: píxeles grisáceos y más brillantes que la
# tierra. Se cuentan solo en el centro de la celda, porque
# en los bordes asoman los muros y enredaderas vecinos.
# Púas levantadas >= 25; cualquier otro piso 0.
RAISED_BRIGHTNESS = 75
RAISED_MARGIN = 8
RAISED_PIXELS = 12

# Un hueco rellenado es una roca rodeada por el borde negro
# del foso; una roca sobre el piso casi no tiene negro
# (hueco rellenado: 110 píxeles, rocas <= 27).
FILLED_DARK_PIXELS = 60

# El jugador está animado y no siempre coincide con sus
# templates. Si ninguna celda lo reconoce, se toma la celda
# libre más parecida, siempre que no supere esta distancia.
PLAYER_FALLBACK_DISTANCE = 45


def base_label(label):
    """
    WALL_03 -> WALL
    """

    return label.split("_")[0]


def cell_features(cell):
    """
    Reduce la celda a una miniatura de color.

    Comparar color en baja resolución tolera pequeños
    desplazamientos y distingue bien piso, muro y objetos.
    """

    small = cv2.resize(
        cell,
        (FEATURE_SIZE, FEATURE_SIZE),
        interpolation=cv2.INTER_AREA
    )

    return small.astype(np.float32)


def count_dark_dots(cell):
    """
    Cuenta píxeles mucho más oscuros que su entorno.

    Los agujeros de las púas son demasiado pequeños
    para sobrevivir a la miniatura de color.
    """

    gray = cv2.cvtColor(
        cell,
        cv2.COLOR_BGR2GRAY
    )

    background = cv2.medianBlur(gray, 15)

    dots = (
        background.astype(int) - gray.astype(int)
    ) > 18

    return int(dots[4:-4, 4:-4].sum())


def count_gray_pixels(cell):
    """
    Cuenta píxeles sin el tono rojizo de la tierra.

    El fondo de un hueco es gris; el piso, las púas
    y las sombras de los muros son siempre marrones.
    """

    inner = cell[4:-4, 4:-4].astype(int)

    tint = inner[..., 2] - inner[..., 0]

    # tint muy negativo es el cian de una llave, no un hueco.
    gray = (tint < 25) & (tint > -20)

    return int(gray.sum())


def count_black_pixels(cell):

    inner = cell[4:-4, 4:-4].astype(int)

    return int((inner.mean(axis=2) < 30).sum())


def count_raised_pixels(cell):

    inner = cell[
        RAISED_MARGIN:-RAISED_MARGIN,
        RAISED_MARGIN:-RAISED_MARGIN
    ].astype(int)

    tint = inner[..., 2] - inner[..., 0]

    raised = (
        (tint < 25)
        & (tint > -20)
        & (inner.mean(axis=2) > RAISED_BRIGHTNESS)
    )

    return int(raised.sum())


def prepare_templates(templates):
    """
    Precalcula las características de cada template.

    Recibe el diccionario de load_templates().
    """

    prepared = []

    for label, image in templates.items():

        symbol = SYMBOLS.get(
            base_label(label)
        )

        if symbol is None:
            print(
                f"Template ignorado (clase desconocida): {label}"
            )
            continue

        prepared.append(
            (
                symbol,
                cell_features(image),
                cell_features(image[TOP_ROW_VISIBLE_FROM:])
            )
        )

    return prepared


def classify_cell(cell, prepared, top_row=False):
    """
    Devuelve (símbolo, distancia) de la celda.

    top_row: la celda está en la fila tapada por el HUD
    y solo se compara su franja visible.
    """

    if top_row:
        features = cell_features(cell[TOP_ROW_VISIBLE_FROM:])
    else:
        features = cell_features(cell)

    best_symbol = UNKNOWN
    best_distance = float("inf")

    gray_pixels = count_gray_pixels(cell)

    is_pit = count_black_pixels(cell) >= FILLED_DARK_PIXELS

    for symbol, full, strip in prepared:

        if symbol == FILLED and not is_pit:
            continue

        if top_row and symbol not in TOP_ROW_SYMBOLS:
            continue

        low, high = GRAY_RANGE.get(
            symbol,
            (0, float("inf"))
        )

        if not low <= gray_pixels <= high:
            continue

        template = strip if top_row else full

        distance = float(
            np.abs(features - template).mean()
        )

        if distance < best_distance:
            best_distance = distance
            best_symbol = symbol

    if best_distance > UNKNOWN_DISTANCE:

        if features.mean() > WALL_BRIGHTNESS:
            best_symbol = WALL
        else:
            best_symbol = UNKNOWN

    if top_row:

        if (
            best_symbol == FLOOR
            and count_gray_pixels(cell[TOP_ROW_VISIBLE_FROM - 4:])
            >= TOP_ROW_HOLE_GRAY_PIXELS
        ):
            best_symbol = HOLE

        return best_symbol, best_distance

    if best_symbol == FILLED:
        return FLOOR, best_distance

    if best_symbol in (FLOOR, SPIKE):

        if gray_pixels >= GATE_GRAY_PIXELS:
            # Tanto gris solo lo tienen los barrotes de una reja,
            # aunque la miniatura se parezca más al piso.
            best_symbol = GATE
        elif gray_pixels >= HOLE_GRAY_PIXELS:
            best_symbol = HOLE
        elif count_raised_pixels(cell) >= RAISED_PIXELS:
            best_symbol = RAISED
        elif count_dark_dots(cell) >= SPIKE_DOTS:
            best_symbol = SPIKE
        else:
            best_symbol = FLOOR

    return best_symbol, best_distance


def read_level(game_image, prepared):
    """
    Convierte la imagen del juego en un tablero lógico.

    Devuelve una lista de filas, cada una una lista de símbolos.
    """

    height, width = game_image.shape[:2]

    grid = []

    player_templates = [
        full
        for symbol, full, _ in prepared
        if symbol == PLAYER
    ]

    # (distancia al jugador, fila, columna) de las celdas
    # donde podría estar un jugador no reconocido.
    candidates = []

    y = GRID_Y0

    while y + CELL_HEIGHT <= height:

        row = []

        x = X0

        while x + CELL_WIDTH <= width:

            cell = game_image[
                y:y + CELL_HEIGHT,
                x:x + CELL_WIDTH
            ]

            symbol, _ = classify_cell(
                cell,
                prepared,
                top_row=not grid
            )

            if (
                grid
                and player_templates
                and symbol in (FLOOR, SPIKE, HOLE, UNKNOWN)
            ):

                features = cell_features(cell)

                candidates.append(
                    (
                        min(
                            float(np.abs(features - t).mean())
                            for t in player_templates
                        ),
                        len(grid),
                        len(row)
                    )
                )

            row.append(symbol)

            x += CELL_WIDTH

        grid.append(row)

        y += CELL_HEIGHT

    if candidates and not find_cells(grid, PLAYER):

        distance, r, c = min(candidates)

        if distance <= PLAYER_FALLBACK_DISTANCE:
            grid[r][c] = PLAYER

    return grid


def find_cells(grid, symbol):

    return [
        (r, c)
        for r, row in enumerate(grid)
        for c, value in enumerate(row)
        if value == symbol
    ]


def cell_image(game_image, row, col):

    y = GRID_Y0 + row * CELL_HEIGHT
    x = X0 + col * CELL_WIDTH

    return game_image[
        y:y + CELL_HEIGHT,
        x:x + CELL_WIDTH
    ]


def format_grid(grid):

    return "\n".join(
        " ".join(row)
        for row in grid
    )
