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


def capture_region(x, y, width, height):
    """
    Captura un rectángulo de la pantalla como imagen BGR.

    Va directo a X11: tarda ~20 ms, contra los ~300 ms de
    pyautogui.screenshot(), así que sirve para vigilar el
    juego mientras se ejecuta un plan.
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
