import time
from pathlib import Path

import cv2

from agent import DiamondRushAgent
from level_reader import format_grid
from solver import format_plan


PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "dataset" / "raw"


# Tableros etiquetados a mano a partir de las capturas.
EXPECTED = {
    1: """
# # # # # # # # # #
# . . # # # # # # #
# . . # # # # # # #
# . P D D D . . . #
# # # # # # # D . #
# # # # # # # D . #
# . D . D D . . . #
# . D . # # # # # #
# . D . # # # # # #
# # # . D D . . . #
# # # . . # . E . #
# . . . . # . . . #
""",
    2: """
# # # # # # # # # #
# . . D . . # L L #
# . D . D . # L L #
# S # # # . # # . #
# D L L # D . D . #
# D L L # D . D . #
# . # # # S # L L #
# . # . D S # L L #
# . # E # S # # # #
# . # # # . . . . #
# D D S S . . P . #
# D D # # . . . . #
""",
    3: """
# # # # # # # # # #
# . . . # . # . D #
# . P # # . G . E #
# . . S . . # . D #
# # S # G # # # # #
# . . # . . # D D #
# . D # . . G K D #
# # . # . . # D D #
# K . # D . # # # #
# . # # . . # . . #
# D S S . . G K D #
# . # # # K # . . #
""",
    4: """
# # # # # # # # # #
# . P . . . . . . #
# # # # # # R # # #
# . . D D . H . . #
# R # # # # # # # #
# H . . . R . D . #
# # # # # # D # # #
# . . . . . . . . #
# . R . . . . . . #
# # . . R # H # . #
# # # H D # E # . #
# # # # D # # # . #
""",
    5: """
# # # # # # # # # #
# E # # # # # D D #
# P S . . K # D D #
# S # # R # # # G #
# D # . . . # # H #
# D # . . . . . . #
# H # . . . . . . #
# . . . . . # . . #
# . . . . # # # . #
# L L L . # # # R #
# L L L . S S . . #
# # # # # D D # # #
""",
    8: """
# # D . D . D . # #
# # . # # # # D # #
# # D # . E # . # #
# # . D . D # . # #
# # # # # # # G # #
# # O . R P . D # #
# # # # # # # B # #
# # H R D S B . # #
# # K # S S # . # #
# # R # S S # S # #
# # H R . D O D # #
# # # # # # # # # #
""",
    10: """
# # # # # # # # # #
# . . S . . S . . #
# D # # . . # # D #
# D D # E . # D D #
# . D # # P # D . #
# # . # . . # . # #
# D H . S S . H D #
# # S # R R # S # #
# . . . . . . . . #
# . R . . . . R . #
# . # . R R . # . #
# . . . . . . . . #
""",
    11: """
# # # # # # # # # #
# K . . # # # O . #
# . P . E D B . . #
# S # # # # # H # #
# . . # D D # D . #
# . D . . . # D . #
# S # # # . . . # #
# . S . # H R . K #
# R # . # . . . # #
# . D D . R . . # #
# H # # # R # S # #
# . S D G . G D D #
""",
    12: """
# # # # # # # # # #
# . D P . S # D # #
# # # # # . S . S #
# # . G . S # # R #
# D . # . . . S D #
# # . # # # # # . #
# # B # L # L # . #
# D D . . # . . . #
# S # # R # . # D #
# S # . . # . R H #
# K D D . O . . E #
# # # # # # # # # #
""",
    14: """
# # # # # # # # # #
# . . D . . # D D #
# # B # E # # D D #
# . . . # . # B # #
# D . . D # . . . #
# . # B # . # H O #
# # . R O # D . . #
# . . . # D . . . #
# # G # . # # R # #
# O . . O . B . . #
# # . . R . # # K #
# # # # P # # # # #
""",
    16: """
# # # # # # # # # #
# L L L L L L L L #
# L L # L L # L L #
# L L L L L L L L #
# P . . # . . # D #
# . # . . . . R . #
# . # R # # R # . #
# . # . . D . # . #
# D . . . # . # . #
# . # # . . . D . #
# . # D . # # # # #
# . . . . H H H E #
"""
}


def main():

    agent = DiamondRushAgent()

    for level, expected in EXPECTED.items():

        image = cv2.imread(
            str(
                RAW_DIR
                / f"level_{level:03d}"
                / "game_area.png"
            )
        )

        start = time.perf_counter()

        plan = agent.compute(image)

        elapsed = time.perf_counter() - start

        board = format_grid(agent.grid)

        print(f"--- Nivel {level} ({elapsed:.2f}s)")
        print(board)

        if board != expected.strip():
            print("ERROR: el tablero no coincide con el esperado.")

        if plan is None:
            print("ERROR: sin solución.")
        else:
            print(
                f"Plan ({len(plan)} movimientos): "
                f"{format_plan(plan)}"
            )

        print()


if __name__ == "__main__":
    main()
