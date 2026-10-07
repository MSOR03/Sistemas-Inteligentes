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