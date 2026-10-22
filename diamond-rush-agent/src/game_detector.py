import cv2

from image_io import read_image


GAME_OFFSET_X = -28
GAME_OFFSET_Y = -39

GAME_WIDTH = 452
GAME_HEIGHT = 638


_templates = {}


def load_template(template_path):
    """
    Lee el template una sola vez: find_scale lo usa en cada
    escala que prueba.
    """

    template = _templates.get(template_path)

    if template is None:

        template = read_image(template_path)

        if template is None:
            raise FileNotFoundError(
                f"No se encontró el template: {template_path}"
            )

        _templates[template_path] = template

    return template


def locate_anchor(
    image,
    template_path,
    threshold=0.80
):
    template = load_template(template_path)

    result = cv2.matchTemplate(
        image,
        template,
        cv2.TM_CCOEFF_NORMED
    )

    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < threshold:
        return None

    h, w = template.shape[:2]
    x, y = max_loc

    return {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "confidence": max_val
    }


def scaled_image(image, scale):

    if scale == 1.0:
        return image

    return cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC
    )


# Factor al que se reduce la pantalla para la búsqueda gruesa.
COARSE_FACTOR = 0.5


def find_scale(image, template_path):
    """
    Busca el factor por el que hay que escalar la pantalla
    para que el juego quede en su tamaño nativo (por ejemplo
    1.5 si el navegador está con zoom al 67%).
    """

    template = load_template(template_path)

    h, w = template.shape[:2]

    # La búsqueda gruesa se hace sobre la pantalla a la mitad:
    # cada matchTemplate cuesta cuatro veces menos.
    small = cv2.resize(
        image,
        None,
        fx=COARSE_FACTOR,
        fy=COARSE_FACTOR,
        interpolation=cv2.INTER_AREA
    )

    def coarse_match(scale):
        # Encoger el template es mucho más barato
        # que agrandar toda la pantalla.
        result = cv2.matchTemplate(
            small,
            scaled_image(template, COARSE_FACTOR / scale),
            cv2.TM_CCOEFF_NORMED
        )

        _, score, _, loc = cv2.minMaxLoc(result)

        return score, loc

    coarse = [s / 100 for s in range(50, 205, 5)]
    matches = {scale: coarse_match(scale) for scale in coarse}
    best = max(coarse, key=lambda scale: matches[scale][0])

    # La búsqueda fina agranda solo la zona donde apareció el
    # ancla, no toda la pantalla.
    x, y = (round(v / COARSE_FACTOR) for v in matches[best][1])
    margin = round(max(w, h) / best)

    window = image[
        max(y - margin, 0):y + 2 * margin,
        max(x - margin, 0):x + 2 * margin
    ]

    def fine_score(scale):

        scaled = scaled_image(window, scale)

        if scaled.shape[0] < h or scaled.shape[1] < w:
            return -1

        return locate_anchor(
            scaled,
            template_path,
            threshold=-1
        )["confidence"]

    # Más ancha que el paso grueso: a la mitad de resolución la
    # búsqueda gruesa puede quedar a un paso de la escala real.
    fine = [best + d / 100 for d in range(-7, 8)]

    return max(fine, key=fine_score)


# Píxeles que se busca el ancla alrededor de su posición anterior.
HINT_MARGIN = 20


def locate_near_hint(image, template_path, hint):
    """
    Busca el ancla solo alrededor del área de juego anterior
    (hint), con su misma escala. Devuelve el área o None si
    el ancla ya no está ahí.
    """

    scale = hint["scale"]

    scaled = scaled_image(image, scale)

    anchor_x = hint["x"] - GAME_OFFSET_X
    anchor_y = hint["y"] - GAME_OFFSET_Y

    h, w = load_template(template_path).shape[:2]

    left = max(anchor_x - HINT_MARGIN, 0)
    top = max(anchor_y - HINT_MARGIN, 0)

    window = scaled[
        top:anchor_y + h + HINT_MARGIN,
        left:anchor_x + w + HINT_MARGIN
    ]

    if window.shape[0] < h or window.shape[1] < w:
        return None

    anchor = locate_anchor(window, template_path)

    if anchor is None:
        return None

    return {
        "x": left + anchor["x"] + GAME_OFFSET_X,
        "y": top + anchor["y"] + GAME_OFFSET_Y,
        "width": GAME_WIDTH,
        "height": GAME_HEIGHT,
        "confidence": anchor["confidence"],
        "scale": scale
    }


def locate_game_area(image, template_path, hint=None):
    """
    Devuelve el área del juego en coordenadas de la pantalla
    escalada por "scale"; crop_game aplica ese mismo escalado.

    hint: área encontrada antes. Si el juego no se movió, el
    ancla se busca solo alrededor de ella y con su escala: con
    el juego a otra escala (pantalla de 1366x768), find_scale
    tarda ~1 s y esto unos milisegundos.
    """

    if hint is not None:

        area = locate_near_hint(image, template_path, hint)

        if area is not None:
            return area

    scale = 1.0

    anchor = locate_anchor(
        image,
        template_path
    )

    if anchor is None:

        scale = find_scale(image, template_path)

        anchor = locate_anchor(
            scaled_image(image, scale),
            template_path
        )

    if anchor is None:
        return None

    game_x = anchor["x"] + GAME_OFFSET_X
    game_y = anchor["y"] + GAME_OFFSET_Y

    return {
        "x": game_x,
        "y": game_y,
        "width": GAME_WIDTH,
        "height": GAME_HEIGHT,
        "confidence": anchor["confidence"],
        "scale": scale
    }


def crop_game(image, game_area):

    image = scaled_image(
        image,
        game_area.get("scale", 1.0)
    )

    x = game_area["x"]
    y = game_area["y"]
    w = game_area["width"]
    h = game_area["height"]

    return image[
        y:y+h,
        x:x+w
    ]
