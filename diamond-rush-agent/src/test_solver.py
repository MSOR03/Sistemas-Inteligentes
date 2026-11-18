import sys
import time
from pathlib import Path

from agent import DiamondRushAgent
from image_io import read_image
from level_reader import format_grid
from solver import format_plan, solve


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
    6: """
# # # # # # # # # #
# . . . . P . . . #
# . R . D D . R K #
# H # . # # . # H #
# . . . . . . . . #
# . . . . . . . . #
# . . # # G # . . #
# . D # E D # . D #
# # G # # # # S # #
# H . D D D . . . #
# . # # # # # # S #
# S . D K D . . . #
""",
    7: """
# # # # # # # # # #
# # R . R . # # . #
# R P R . R . # . #
# . R # D # R # D #
# R . R . R # # R #
# # R . H . # K D #
# . D . # R # . R #
# R # # R . # . D #
# H R . . D . H # #
# . . # # G # # R #
# D . # . D . # . #
# . # # . E . # R #
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
""",
    17: """
# # # # # # # # # #
# . . D . S . # K #
# D # # # # . # B #
# . B K O B . O . #
# P # # D # # # D #
# . S . R . . . . #
# . S . R . # # # #
# . # # . # # # O #
# # # . . R . . . #
# D # S S # # . D #
# D G . . D # G # #
# # # # # # # . E #
"""
}


# Niveles sin captura guardada: solo se prueba el planificador.
# Nivel 20: la meta es la estatua (E), encerrada tras tres huecos;
# hay que rellenarlos con rocas. Nivel 13: llaves, puertas y reja.
SOLVER_ONLY = {
    13: """
# # # # # # # # # #
# D D . S . D . K #
# D # S # # G # # #
# # # . . D . . . #
# D # . # R # # S #
# . S K B O . . D #
# . # . # # . # # #
# D # S # S . # S #
# . # . # D . S E #
# G # S # # S # # #
# . . D P . . D . #
# # # # # # # # # #
""",
    20: """
# . . . R . . R . #
# # R # # . . P . #
# # . . . R . . . #
# . . R . H H # # #
# R . . R # R R # #
# # # # H # . R . #
# H H H R R H . . #
# E # # H R # # . #
# # # . . R # . . #
# . . . . H R R R #
# . H R R # . . . #
# R . . . # . R . #
"""
}


def main():

    agent = DiamondRushAgent()

    errors = 0

    for level, expected in EXPECTED.items():

        image = read_image(
            str(
                RAW_DIR
                / f"level_{level:03d}"
                / "game_area.png"
            )
        )

        if image is None:
            print(f"--- Nivel {level}: sin captura, se omite.")
            print()
            continue

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

        errors += board != expected.strip()
        errors += plan is None

    for level, board in SOLVER_ONLY.items():

        grid = [line.split() for line in board.strip().splitlines()]

        start = time.perf_counter()

        plan, _ = solve(grid)

        elapsed = time.perf_counter() - start

        print(f"--- Nivel {level}, solo planificador ({elapsed:.2f}s)")

        if plan is None:
            print("ERROR: sin solución.")
            errors += 1
        else:
            print(
                f"Plan ({len(plan)} movimientos): "
                f"{format_plan(plan)}"
            )

        print()

    print("Todo bien." if not errors else f"{errors} errores.")

    return errors


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
