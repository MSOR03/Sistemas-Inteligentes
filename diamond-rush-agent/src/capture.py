import sys

import pyautogui
import numpy as np
import cv2


def capture_screen():
    """
    Captura toda la pantalla y la devuelve
    como imagen BGR para OpenCV.
    """
    screenshot = pyautogui.screenshot()

    image = np.array(screenshot)

    # PyAutoGUI entrega RGB, OpenCV trabaja normalmente en BGR
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    return image

_display = None

# Captura con mss: copia solo el rectángulo pedido. PIL.ImageGrab
# en Windows captura la pantalla entera y después recorta, así que
# tarda lo mismo que una captura completa (~33 ms contra ~17 ms con
# mss en una pantalla de 1920x1080). Las dos dan los mismos píxeles
# en las mismas coordenadas (pyautogui deja el proceso con DPI
# real). Si mss no está instalado o falla, se usa PIL.ImageGrab.
_mss = None
_mss_failed = False


def capture_region(x, y, width, height):
    """
    Captura un rectángulo de la pantalla como imagen BGR.

    Es rápida, así que sirve para vigilar el juego mientras
    se ejecuta un plan: se llama muchas veces por movimiento.
    En Linux va directo a X11; en Windows y macOS usa mss si
    está, y si no PIL.ImageGrab, la misma función que usa
    pyautogui.screenshot(), así las coordenadas coinciden con
    las de capture_screen().
    """

    global _mss_failed

    if sys.platform.startswith("linux"):
        return _capture_region_x11(x, y, width, height)

    if not _mss_failed:

        try:
            return _capture_region_mss(x, y, width, height)
        except Exception as error:
            _mss_failed = True
            print(
                f"AVISO: captura rápida (mss) no disponible ({error}); "
                f"uso PIL.ImageGrab, más lenta."
            )

    return _capture_region_imagegrab(x, y, width, height)


def _capture_region_mss(x, y, width, height):

    global _mss

    if _mss is None:

        import mss

        # mss 10 renombró la clase; las versiones anteriores
        # solo tienen mss.mss.
        factory = getattr(mss, "MSS", None) or mss.mss
        _mss = factory()

    screen = _mss.monitors[0]

    # La parte que quede fuera de la pantalla se deja en negro.
    left = max(x, screen["left"])
    top = max(y, screen["top"])
    right = min(x + width, screen["left"] + screen["width"])
    bottom = min(y + height, screen["top"] + screen["height"])

    image = np.zeros((height, width, 3), dtype=np.uint8)

    if right <= left or bottom <= top:
        return image

    shot = _mss.grab({
        "left": left,
        "top": top,
        "width": right - left,
        "height": bottom - top
    })

    # mss entrega BGRA: basta con quitar el canal alfa.
    image[
        top - y:bottom - y,
        left - x:right - x
    ] = np.asarray(shot)[:, :, :3]

    return image


def _capture_region_imagegrab(x, y, width, height):

    from PIL import ImageGrab

    shot = ImageGrab.grab(
        bbox=(x, y, x + width, y + height)
    )

    image = cv2.cvtColor(
        np.array(shot.convert("RGB")),
        cv2.COLOR_RGB2BGR
    )

    if image.shape[:2] == (height, width):
        return image

    # La parte que quede fuera de la pantalla se deja en negro.
    padded = np.zeros((height, width, 3), dtype=np.uint8)

    h = min(height, image.shape[0])
    w = min(width, image.shape[1])

    padded[:h, :w] = image[:h, :w]

    return padded


def _capture_region_x11(x, y, width, height):
    """
    Tarda ~20 ms, contra los ~300 ms de pyautogui.screenshot().
    """

    global _display

    from Xlib import X, display

    if _display is None:
        _display = display.Display()

    screen = _display.screen()

    # La parte que quede fuera de la pantalla se deja en negro.
    left = max(x, 0)
    top = max(y, 0)
    right = min(x + width, screen.width_in_pixels)
    bottom = min(y + height, screen.height_in_pixels)

    image = np.zeros((height, width, 3), dtype=np.uint8)

    if right <= left or bottom <= top:
        return image

    raw = screen.root.get_image(
        left,
        top,
        right - left,
        bottom - top,
        X.ZPixmap,
        0xffffffff
    )

    pixels = np.frombuffer(
        raw.data,
        dtype=np.uint8
    ).reshape(bottom - top, right - left, 4)

    image[
        top - y:bottom - y,
        left - x:right - x
    ] = pixels[..., :3]

    return image
