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


def locate_game_area(image, template_path):

    anchor = locate_anchor(
        image,
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
        "confidence": anchor["confidence"]
    }


def crop_game(image, game_area):

    x = game_area["x"]
    y = game_area["y"]
    w = game_area["width"]
    h = game_area["height"]

    return image[
        y:y+h,
        x:x+w
    ]