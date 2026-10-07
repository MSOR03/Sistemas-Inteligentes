import cv2
import os


def extract_cells(
    image,
    x0,
    y0,
    cell_width,
    cell_height,
    output_dir
):
    os.makedirs(
        output_dir,
        exist_ok=True
    )

    height, width = image.shape[:2]

    row = 0
    y = y0

    while y + cell_height <= height:

        col = 0
        x = x0

        while x + cell_width <= width:

            cell = image[
                y:y + cell_height,
                x:x + cell_width
            ]

            filename = (
                f"r{row:02d}_c{col:02d}.png"
            )

            cv2.imwrite(
                os.path.join(
                    output_dir,
                    filename
                ),
                cell
            )

            col += 1
            x += cell_width

        row += 1
        y += cell_height