import cv2

from cell_extractor import extract_cells


image = cv2.imread(
    "../screenshots/game_area.png"
)

extract_cells(
    image=image,
    x0=0,          # provisional
    y0=125,
    cell_width=42,
    cell_height=43,
    output_dir="../screenshots/cells"
)

print("Celdas extraídas.")