from pathlib import Path

import cv2
import numpy as np


# cv2.imread y cv2.imwrite no aceptan rutas con caracteres fuera
# de ASCII en Windows (por ejemplo C:\Users\Sebastián\...): fallan
# sin avisar, devolviendo None o False. Leer y escribir los bytes
# con NumPy y codificar la imagen en memoria funciona con
# cualquier ruta y en cualquier sistema.


def read_image(path):
    """
    Lee una imagen BGR; None si no existe o no se puede leer.
    """

    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None

    if data.size == 0:
        return None

    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def write_image(path, image):
    """
    Guarda la imagen; el formato sale de la extensión.

    Devuelve False si no se pudo.
    """

    path = Path(path)

    ok, encoded = cv2.imencode(path.suffix or ".png", image)

    if not ok:
        return False

    try:
        encoded.tofile(str(path))
    except OSError:
        return False

    return True
