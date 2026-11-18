import cv2
import os
from image_io import read_image


def load_templates(template_dir):
    """
    Carga todos los templates de celda.
    El nombre del archivo se usa como etiqueta.
    """

    templates = {}

    for filename in os.listdir(template_dir):

        if not filename.lower().endswith(
            (".png", ".jpg", ".jpeg")
        ):
            continue

        path = os.path.join(
            template_dir,
            filename
        )

        image = read_image(path)

        if image is None:
            continue

        label = os.path.splitext(
            filename
        )[0].upper()

        templates[label] = image

    return templates


def similarity(cell, template):
    """
    Compara una celda con un template.
    """

    # Garantizar mismo tamaño
    if (
        cell.shape[0] != template.shape[0]
        or cell.shape[1] != template.shape[1]
    ):
        template = cv2.resize(
            template,
            (
                cell.shape[1],
                cell.shape[0]
            )
        )

    cell_gray = cv2.cvtColor(
        cell,
        cv2.COLOR_BGR2GRAY
    )

    template_gray = cv2.cvtColor(
        template,
        cv2.COLOR_BGR2GRAY
    )

    result = cv2.matchTemplate(
        cell_gray,
        template_gray,
        cv2.TM_CCOEFF_NORMED
    )

    return float(result[0][0])


def classify_cell(
    cell,
    templates
):
    """
    Devuelve la clase con mayor similitud.
    """

    best_label = None
    best_score = -1

    scores = {}

    for label, template in templates.items():

        score = similarity(
            cell,
            template
        )

        scores[label] = score

        if score > best_score:
            best_score = score
            best_label = label

    return (
        best_label,
        best_score,
        scores
    )