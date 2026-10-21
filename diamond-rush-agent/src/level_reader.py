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

# Hueco ya rellenado con una roca: el clasificador
# lo distingue, pero en el tablero es piso normal.
FILLED = "f"
UNKNOWN = "?"

# Casilla del mapa que la cámara todavía no mostró
# (niveles más grandes que la pantalla, ver stitcher.py).
UNSEEN = "~"

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

# Lo único que se intenta distinguir en la fila tapada.
# El jugador también puede llegar a esa fila (nivel 8), y en
# el nivel 20 hay rocas: sin ROCK se leían como diamantes.
TOP_ROW_SYMBOLS = (WALL, FLOOR, DIAMOND, PLAYER, ROCK)

TOP_ROW_LINES = slice(TOP_ROW_VISIBLE_FROM, None)

# Todo lo que queda por encima de esta línea de la vista
# está tapado por el HUD, se mueva o no la cámara.
VIEW_TOP = GRID_Y0 + TOP_ROW_VISIBLE_FROM

# En un mapa armado con varias capturas, una celda vista solo
# en parte se clasifica como la fila tapada (con sus mismos
# símbolos) si se vio al menos una franja así de alta.
MIN_VISIBLE_LINES = CELL_HEIGHT - TOP_ROW_VISIBLE_FROM


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
# un piso se considera trampa de púas (piso <= 66, púas >= 86:
# en el nivel 6 una trampa al lado de un muro da solo 86).
SPIKE_DOTS = 76

# Cantidad de píxeles grisáceos (el fondo del hueco) a partir
# de la cual un piso se considera hueco (resto <= 102, huecos >= 245).
# Las púas levantadas también tienen gris: en otra pantalla
# dieron 180, así que el umbral queda entre ambos.
# Los huecos no usan templates: se parecen demasiado al
# borde superior de la lava en la miniatura de color.
HOLE_GRAY_PIXELS = 210

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

# Llaves y diamantes son los únicos objetos cian. En una zona
# en sombra la miniatura de color es casi todo fondo, y una
# llave se parecía más a un diamante en sombra (o un piso en
# sombra a una llave) que a su propio template. Contar el cian
# no depende del fondo: llaves 211-291, diamantes 270-308,
# puertas >= 402, jugador <= 13, todo lo demás 0.
CYAN_OBJECTS = (KEY, DIAMOND)
CYAN_RANGE = (100, 355)

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

# A veces el hueco rellenado se parece más a una roca que a su
# template. Con tanto negro alrededor no es una roca suelta
# (huecos rellenados >= 110, rocas sobre placa <= 67).
FILLED_ROCK_DARK_PIXELS = 90

# El jugador está animado y no siempre coincide con sus
# templates. Si ninguna celda lo reconoce, se toma la celda
# libre más parecida, siempre que no supere esta distancia.
PLAYER_FALLBACK_DISTANCE = 45

# Antes de esa distancia se busca el jugador con su template a
# resolución completa. Si el navegador dibuja el juego más chico
# (pantalla de 1366x768: escala 0.75) y la captura se agranda,
# la imagen queda borrosa: la miniatura del jugador se aleja de
# su template más que un piso, y la celda de arriba, donde solo
# asoma el sombrero, se parece más que la suya. Comparar a
# resolución completa no se confunde: el jugador da >= 0.89 y
# cualquier otra celda <= 0.48. Se prueban también los templates
# reflejados, porque el jugador mira hacia ambos lados.
PLAYER_MATCH_SCORE = 0.7

# Margen alrededor de la celda donde se busca el template:
# el sombrero asoma por encima de la casilla.
PLAYER_MATCH_MARGIN = 10


def player_match_score(game_image, row, col, templates):
    """
    Mejor coincidencia (TM_CCOEFF_NORMED) de los templates del
    jugador alrededor de la celda (row, col).
    """

    y = GRID_Y0 + row * CELL_HEIGHT
    x = X0 + col * CELL_WIDTH

    window = game_image[
        max(y - PLAYER_MATCH_MARGIN, 0):y + CELL_HEIGHT + PLAYER_MATCH_MARGIN,
        max(x - PLAYER_MATCH_MARGIN, 0):x + CELL_WIDTH + PLAYER_MATCH_MARGIN
    ]

    best = -1.0

    for template in templates:

        if (
            window.shape[0] < template.shape[0]
            or window.shape[1] < template.shape[1]
        ):
            continue

        result = cv2.matchTemplate(
            window,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        best = max(best, float(cv2.minMaxLoc(result)[1]))

    return best


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


def count_cyan_pixels(cell):

    inner = cell[4:-4, 4:-4].astype(int)

    return int(((inner[..., 0] - inner[..., 2]) > 40).sum())


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
                cell_features(image[TOP_ROW_LINES]),
                # Para las celdas vistas solo en parte.
                image
            )
        )

    return prepared


def classify_cell(cell, prepared, top_row=False, lines=None):
    """
    Devuelve (símbolo, distancia) de la celda.

    top_row: la celda está en la fila tapada por el HUD
    y solo se compara su franja visible.
    lines: franja visible (slice de líneas) de una celda vista
    solo en parte; se trata igual que la fila tapada.
    """

    if top_row:
        lines = TOP_ROW_LINES

    top_row = lines is not None

    if top_row:
        features = cell_features(cell[lines])
    else:
        features = cell_features(cell)

    best_symbol = UNKNOWN
    best_distance = float("inf")

    gray_pixels = count_gray_pixels(cell)

    is_pit = count_black_pixels(cell) >= FILLED_DARK_PIXELS

    # En la fila tapada asoma el diamante cian del HUD.
    cyan_low, cyan_high = CYAN_RANGE
    cyan_pixels = None if top_row else count_cyan_pixels(cell)

    for symbol, full, strip, image in prepared:

        if cyan_pixels is not None:

            if (
                (cyan_low <= cyan_pixels <= cyan_high)
                != (symbol in CYAN_OBJECTS)
            ):
                continue

            # La puerta verde tiene aún más cian. Su template
            # es casi todo muro: sin esto, un muro se parece a ella.
            if symbol == DOOR and cyan_pixels <= cyan_high:
                continue

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

        if not top_row:
            template = full
        elif lines == TOP_ROW_LINES:
            template = strip
        else:
            template = cell_features(image[lines])

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
        return best_symbol, best_distance

    if best_symbol == FILLED:
        return FLOOR, best_distance

    if (
        best_symbol == ROCK
        and count_black_pixels(cell) >= FILLED_ROCK_DARK_PIXELS
    ):
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


def visible_lines(seen_cell):
    """
    Franja más alta de líneas completamente vistas de una
    celda del mapa, como slice; None si no llega al mínimo.
    """

    rows = seen_cell.all(axis=1)

    best = (0, 0)
    start = None

    for index, seen in enumerate(list(rows) + [False]):

        if seen and start is None:
            start = index

        if not seen and start is not None:

            if index - start > best[1] - best[0]:
                best = (start, index)

            start = None

    if best[1] - best[0] < MIN_VISIBLE_LINES:
        return None

    return slice(*best)


def read_level(game_image, prepared, seen=None):
    """
    Convierte la imagen del juego en un tablero lógico.

    seen: en un mapa armado con varias capturas (stitcher.py),
    máscara de los píxeles que la cámara mostró. Una celda
    vista solo en parte se lee como la fila tapada por el HUD,
    y una que casi no se vio queda como UNSEEN. Sin máscara,
    la fila tapada es la primera.

    Devuelve una lista de filas, cada una una lista de símbolos.
    """

    height, width = game_image.shape[:2]

    grid = []

    player_templates = [
        full
        for symbol, full, _, _ in prepared
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

            if seen is None:

                partial = not grid

                symbol, _ = classify_cell(
                    cell,
                    prepared,
                    top_row=partial
                )

            else:

                lines = visible_lines(
                    seen[
                        y:y + CELL_HEIGHT,
                        x:x + CELL_WIDTH
                    ]
                )

                partial = lines != slice(0, CELL_HEIGHT)

                if lines is None:
                    symbol = UNSEEN
                else:
                    symbol, _ = classify_cell(
                        cell,
                        prepared,
                        lines=None if not partial else lines
                    )

            if (
                not partial
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

        player_images = [
            image
            for symbol, _, _, image in prepared
            if symbol == PLAYER
        ]

        player_images += [
            cv2.flip(image, 1)
            for image in player_images
        ]

        score, r, c = max(
            (
                player_match_score(game_image, r, c, player_images),
                r,
                c
            )
            for _, r, c in candidates
        )

        if score >= PLAYER_MATCH_SCORE:
            grid[r][c] = PLAYER

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


def view_cell(view, row, col, offset=(0, 0)):
    """
    Parte de la celda que se ve en una captura de la vista:
    lo que queda debajo del HUD y dentro de la imagen.

    offset: desplazamiento (vertical, horizontal) en píxeles
    de la cámara respecto del tablero; (0, 0) si no se movió.
    """

    y = GRID_Y0 + row * CELL_HEIGHT - offset[0]
    x = X0 + col * CELL_WIDTH - offset[1]

    top = max(y, VIEW_TOP)
    left = max(x, 0)

    return view[
        top:max(y + CELL_HEIGHT, top),
        left:max(x + CELL_WIDTH, left)
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
