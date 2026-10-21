from pathlib import Path

import cv2
import numpy as np
from image_io import read_image, write_image

from board_classifier import (
    X0,
    CELL_WIDTH,
    CELL_HEIGHT
)
from level_reader import (
    GRID_Y0,
    VIEW_TOP,
    read_level
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

BUTTON_TEMPLATE = (
    PROJECT_ROOT
    / "assets"
    / "templates"
    / "walkthrough.png"
)


# ----------------------------------------------------
# Geometría de la vista
# ----------------------------------------------------

# Columnas del tablero que entran en la vista. A la derecha
# queda una franja oscura que no es parte del nivel.
VIEW_COLUMNS = 10
VIEW_WIDTH = X0 + VIEW_COLUMNS * CELL_WIDTH

# Debajo de esta línea solo asoma una fila incompleta: no se
# usa para seguir a la cámara (sí se guarda en el mapa).
REGISTER_BOTTOM = GRID_Y0 + 12 * CELL_HEIGHT

# El botón WALKTHROUGH no se mueve con el nivel. Casi siempre
# está dentro del HUD, pero en algunos niveles (el 20) baja al
# borde inferior y tapa parte del tablero. Su template es el
# texto; el panel oscuro lo rodea con este margen
# (arriba, abajo, izquierda, derecha).
BUTTON_THRESHOLD = 0.75
BUTTON_MARGIN = (25, 15, 20, 35)


# ----------------------------------------------------
# Seguimiento de la cámara
# ----------------------------------------------------

# Desplazamiento máximo de la cámara entre dos capturas
# (vertical, horizontal). Se captura tras cada paso, así que
# dos casillas sobran.
MAX_SHIFT = (2 * CELL_HEIGHT, 2 * CELL_WIDTH)

# Correlación mínima para aceptar la posición de la cámara.
# Por debajo, la captura no se usa (por ejemplo, el nivel
# terminó y la pantalla cambió).
MIN_MATCH = 0.6

# Margen del lienzo alrededor de la primera vista, en celdas.
MARGIN_ROWS = 30
MARGIN_COLS = 15


class MapOverflow(Exception):
    """
    La cámara salió del lienzo reservado para el mapa.
    """


_button = None


def button_template():

    global _button

    if _button is None:
        _button = read_image(str(BUTTON_TEMPLATE))

    return _button


def visible_mask(frame):
    """
    Píxeles de la captura que muestran el nivel: debajo del
    HUD, dentro de las columnas del tablero y fuera del botón
    WALKTHROUGH.
    """

    height, width = frame.shape[:2]

    mask = np.zeros((height, width), dtype=bool)
    mask[VIEW_TOP:, :VIEW_WIDTH] = True

    template = button_template()

    if template is not None:

        result = cv2.matchTemplate(
            frame,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        _, score, _, (x, y) = cv2.minMaxLoc(result)

        # Dentro del HUD ya queda fuera de la máscara (su borde
        # roza la franja visible de la fila tapada).
        if score >= BUTTON_THRESHOLD and y > VIEW_TOP:

            top, bottom, left, right = BUTTON_MARGIN
            h, w = template.shape[:2]

            mask[
                max(y - top, 0):y + h + bottom,
                max(x - left, 0):x + w + right
            ] = False

    return mask


def crop(array, y, x, height, width):
    """
    Recorte que rellena con ceros lo que cae fuera del arreglo.
    """

    out = np.zeros(
        (height, width) + array.shape[2:],
        dtype=array.dtype
    )

    top, left = max(y, 0), max(x, 0)
    bottom = min(y + height, array.shape[0])
    right = min(x + width, array.shape[1])

    if bottom > top and right > left:
        out[
            top - y:bottom - y,
            left - x:right - x
        ] = array[top:bottom, left:right]

    return out


class LevelMap:
    """
    Mapa de un nivel más grande que la pantalla, armado con
    las capturas que se van tomando mientras la cámara sigue
    al jugador.

    Coordenadas del mapa: la casilla (0, 0) es la que estaba
    en la casilla (0, 0) de la primera captura; puede haber
    casillas con índices negativos. El tablero que devuelve
    read() empieza en la casilla self.origin.
    """

    def __init__(self, frame):

        height, width = frame.shape[:2]

        self.pad = (
            MARGIN_ROWS * CELL_HEIGHT,
            MARGIN_COLS * CELL_WIDTH
        )

        self.canvas = np.zeros(
            (height + 2 * self.pad[0], width + 2 * self.pad[1], 3),
            dtype=np.uint8
        )

        self.seen = np.zeros(
            self.canvas.shape[:2],
            dtype=bool
        )

        # Desplazamiento en píxeles de la vista actual
        # respecto de la primera captura.
        self.camera = (0, 0)

        # Casilla del mapa que es la (0, 0) del tablero, y su
        # tamaño (filas, columnas). Mientras se explora siguen
        # a lo visto; freeze() los fija para planificar.
        self.origin = (0, 0)
        self.size = None
        self.frozen = False

        self.paint(frame)

    # ------------------------------------------------
    # Cámara
    # ------------------------------------------------

    @property
    def offset(self):
        """
        Desplazamiento de la vista respecto del tablero de
        read(), como lo espera level_reader.view_cell().
        """

        return (
            self.camera[0] - self.origin[0] * CELL_HEIGHT,
            self.camera[1] - self.origin[1] * CELL_WIDTH
        )

    def view_origin(self):
        """
        Píxel del lienzo donde cae la esquina de la vista.
        """

        return (
            self.pad[0] + self.camera[0],
            self.pad[1] + self.camera[1]
        )

    def paint(self, frame):

        mask = visible_mask(frame)

        y, x = self.view_origin()
        height, width = mask.shape

        if (
            y < 0
            or x < 0
            or y + height > self.canvas.shape[0]
            or x + width > self.canvas.shape[1]
        ):
            raise MapOverflow(
                f"La cámara salió del mapa: {self.camera}"
            )

        self.canvas[y:y + height, x:x + width][mask] = frame[mask]
        self.seen[y:y + height, x:x + width] |= mask

    def locate(self, frame):
        """
        Busca dónde está ahora la cámara comparando el centro
        de la captura con lo que se vio en la posición anterior.

        Devuelve (cámara, correlación).
        """

        mask = visible_mask(frame)

        rows = mask[:, :VIEW_WIDTH].all(axis=1)

        bottom = VIEW_TOP

        while bottom < REGISTER_BOTTOM and rows[bottom]:
            bottom += 1

        shift_y, shift_x = MAX_SHIFT

        template = frame[
            VIEW_TOP + shift_y:bottom - shift_y,
            shift_x:VIEW_WIDTH - shift_x
        ]

        y, x = self.view_origin()

        search = self.canvas[
            y + VIEW_TOP:y + bottom,
            x:x + VIEW_WIDTH
        ]

        # Primero a media resolución, luego se afina.
        coarse = cv2.matchTemplate(
            cv2.resize(search, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
            cv2.resize(template, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
            cv2.TM_CCOEFF_NORMED
        )

        _, _, _, (cx, cy) = cv2.minMaxLoc(coarse)

        th, tw = template.shape[:2]

        top = max(2 * cy - 3, 0)
        left = max(2 * cx - 3, 0)

        fine = cv2.matchTemplate(
            search[top:top + th + 6, left:left + tw + 6],
            template,
            cv2.TM_CCOEFF_NORMED
        )

        _, score, _, (fx, fy) = cv2.minMaxLoc(fine)

        camera = (
            self.camera[0] + top + fy - shift_y,
            self.camera[1] + left + fx - shift_x
        )

        return camera, score

    def offset_of(self, frame):
        """
        Desplazamiento (como offset) de una captura, sin
        agregarla al mapa; el actual si no se puede ubicar.
        """

        camera, score = self.locate(frame)

        if score < MIN_MATCH:
            return self.offset

        return (
            camera[0] - self.origin[0] * CELL_HEIGHT,
            camera[1] - self.origin[1] * CELL_WIDTH
        )

    def update(self, frame):
        """
        Sigue a la cámara y agrega la captura al mapa.

        Devuelve False si la captura no se pudo ubicar.
        """

        camera, score = self.locate(frame)

        if score < MIN_MATCH:
            print(
                f"AVISO: no pude ubicar la captura en el mapa "
                f"(correlación {score:.2f}); la ignoro."
            )
            return False

        if camera != self.camera:
            print(f"La cámara se movió a {camera}.")

        self.camera = camera
        self.paint(frame)

        return True

    # ------------------------------------------------
    # Tablero
    # ------------------------------------------------

    def seen_cells(self):
        """
        Rango de casillas (fila0, col0, fila1, col1) del mapa
        con algún píxel visto.
        """

        ys = np.flatnonzero(self.seen.any(axis=1))
        xs = np.flatnonzero(self.seen.any(axis=0))

        def cell(pixel, pad, start, size):
            return (pixel - pad - start) // size

        return (
            cell(ys[0], self.pad[0], GRID_Y0, CELL_HEIGHT),
            cell(xs[0], self.pad[1], X0, CELL_WIDTH),
            cell(ys[-1], self.pad[0], GRID_Y0, CELL_HEIGHT),
            cell(xs[-1], self.pad[1], X0, CELL_WIDTH)
        )

    def fit(self, margin):

        r0, c0, r1, c1 = self.seen_cells()

        self.origin = (r0 - margin, c0 - margin)
        self.size = (
            r1 - r0 + 1 + 2 * margin,
            c1 - c0 + 1 + 2 * margin
        )

    def freeze(self):
        """
        Fija el tablero a lo visto: a partir de aquí las
        casillas del tablero ya no cambian de índice.
        """

        self.fit(0)
        self.frozen = True

    def crop(self, array):
        """
        Recorta el lienzo con la geometría de una captura:
        la fila 0 del tablero empieza en GRID_Y0.
        """

        rows, cols = self.size

        return crop(
            array,
            self.pad[0] + self.origin[0] * CELL_HEIGHT,
            self.pad[1] + self.origin[1] * CELL_WIDTH,
            GRID_Y0 + rows * CELL_HEIGHT,
            X0 + cols * CELL_WIDTH
        )

    def image(self):

        return self.crop(self.canvas)

    def read(self, templates):
        """
        Tablero lógico del mapa. Mientras se explora incluye
        un borde de casillas sin ver (UNSEEN) alrededor.
        """

        if not self.frozen:
            self.fit(1)

        return read_level(
            self.image(),
            templates,
            self.crop(self.seen)
        )

    def to_map(self, cell):

        return (
            cell[0] + self.origin[0],
            cell[1] + self.origin[1]
        )

    def to_grid(self, cell):

        return (
            cell[0] - self.origin[0],
            cell[1] - self.origin[1]
        )

    def save(self, path):

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        write_image(str(path), self.image())
