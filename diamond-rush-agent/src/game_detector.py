import cv2


GAME_OFFSET_X = -28
GAME_OFFSET_Y = -39

GAME_WIDTH = 452
GAME_HEIGHT = 638


def locate_anchor(
    image,
    template_path,
    threshold=0.80
):
    template = cv2.imread(template_path)

    if template is None:
        raise FileNotFoundError(
            f"No se encontró el template: {template_path}"
        )

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


def find_scale(image, template_path):
    """
    Busca el factor por el que hay que escalar la pantalla
    para que el juego quede en su tamaño nativo (por ejemplo
    1.5 si el navegador está con zoom al 67%).
    """

    template = cv2.imread(template_path)

    if template is None:
        raise FileNotFoundError(
            f"No se encontró el template: {template_path}"
        )

    def coarse_score(scale):
        # Encoger el template es mucho más barato
        # que agrandar toda la pantalla.
        result = cv2.matchTemplate(
            image,
            scaled_image(template, 1 / scale),
            cv2.TM_CCOEFF_NORMED
        )

        return cv2.minMaxLoc(result)[1]

    def fine_score(scale):

        anchor = locate_anchor(
            scaled_image(image, scale),
            template_path,
            threshold=-1
        )

        return anchor["confidence"]

    coarse = [s / 100 for s in range(50, 205, 5)]
    best = max(coarse, key=coarse_score)

    fine = [best + d / 100 for d in range(-4, 5, 2)]

    return max(fine, key=fine_score)


def locate_game_area(image, template_path):
    """
    Devuelve el área del juego en coordenadas de la pantalla
    escalada por "scale"; crop_game aplica ese mismo escalado.
    """

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
