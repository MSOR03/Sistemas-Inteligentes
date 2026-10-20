import argparse
import time
from pathlib import Path

import cv2

from agent import DiamondRushAgent
from game_detector import (
    GAME_HEIGHT,
    GAME_WIDTH,
    crop_game,
    locate_anchor,
    locate_game_area
)
from level_reader import (
    PLAYER,
    UNKNOWN,
    cell_image,
    find_cells,
    format_grid
)
from solver import format_plan, keys_in_hand_after


PROJECT_ROOT = Path(__file__).resolve().parent.parent

ANCHOR_TEMPLATE = (
    PROJECT_ROOT
    / "assets"
    / "templates"
    / "game_anchor.png"
)

UNKNOWN_DIR = (
    PROJECT_ROOT
    / "dataset"
    / "unknown"
)


DEBUG_SCREEN = (
    PROJECT_ROOT
    / "screenshots"
    / "debug_no_game.png"
)


LAST_GAME = (
    PROJECT_ROOT
    / "screenshots"
    / "last_game.png"
)


# Segundos que tarda una reja en abrirse o cerrarse.
GATE_ANIMATION = 0.4


def capture_game():
    """
    Captura la pantalla y recorta el área del juego.

    Devuelve (imagen, grab), donde grab() vuelve a capturar
    solo esa área, rápido, para seguir la partida; o None
    si el juego no está en pantalla.
    """

    # Import diferido: el modo --image no necesita pantalla.
    from capture import capture_region, capture_screen

    screen = capture_screen()

    game_area = locate_game_area(
        screen,
        str(ANCHOR_TEMPLATE)
    )

    if game_area is None:

        # Guardar lo que realmente se capturó para diagnosticar.
        best = locate_anchor(
            screen,
            str(ANCHOR_TEMPLATE),
            threshold=-1
        )

        DEBUG_SCREEN.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        cv2.imwrite(str(DEBUG_SCREEN), screen)

        print(
            f"Pantalla capturada: {screen.shape[1]}x{screen.shape[0]}. "
            f"Mejor coincidencia del ancla: {best['confidence']:.2f} "
            f"en ({best['x']}, {best['y']}), se necesita 0.80."
        )
        print(f"Captura guardada en {DEBUG_SCREEN}")

        return None

    game = crop_game(screen, game_area)

    # Última área de juego leída, para revisar el tablero.
    LAST_GAME.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    cv2.imwrite(str(LAST_GAME), game)

    # El área está en coordenadas de la pantalla escalada.
    scale = game_area["scale"]

    region = (
        round(game_area["x"] / scale),
        round(game_area["y"] / scale),
        round(GAME_WIDTH / scale),
        round(GAME_HEIGHT / scale)
    )

    def grab():

        return cv2.resize(
            capture_region(*region),
            (GAME_WIDTH, GAME_HEIGHT),
            interpolation=cv2.INTER_LINEAR
        )

    return game, grab


def save_unknown_cells(game, grid):
    """
    Guarda las celdas no reconocidas para poder
    convertirlas en templates.
    """

    cells = find_cells(grid, UNKNOWN)

    if not cells:
        return

    UNKNOWN_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    stamp = time.strftime("%Y%m%d_%H%M%S")

    for row, col in cells:

        cv2.imwrite(
            str(
                UNKNOWN_DIR
                / f"{stamp}_r{row:02d}_c{col:02d}.png"
            ),
            cell_image(game, row, col)
        )

    print(
        f"AVISO: {len(cells)} celdas no reconocidas "
        f"(se tratan como obstáculo): {cells}"
    )
    print(
        f"Recortes guardados en {UNKNOWN_DIR}"
    )


def print_learned(agent):

    for gate, plate in agent.learned:
        print(
            f"Aprendido: la reja {gate} no se abre "
            f"con la placa {plate}."
        )


def plan_level(agent, game, keys_in_hand=0, replanning=False):
    """
    Percibe, planifica y muestra el resultado.
    """

    plan = agent.compute(game, keys_in_hand, replanning)

    print()
    print(format_grid(agent.grid))
    print()

    save_unknown_cells(game, agent.grid)

    print_learned(agent)

    if not find_cells(agent.grid, PLAYER):
        print("No se encontró al jugador en el tablero.")
        return None

    if plan is None:
        print("No se encontró solución para este tablero.")
        return None

    print(
        f"Plan ({len(plan)} movimientos): "
        f"{format_plan(plan)}"
    )

    return plan


def play(args):

    from controller import execute_plan

    agent = DiamondRushAgent()

    print(
        f"Haz clic sobre el juego. "
        f"Empiezo en {args.countdown} segundos..."
    )

    time.sleep(args.countdown)

    solved = 0
    replans = 0

    # El nivel ya está empezado (se replanifica sobre él).
    started = False

    # Llaves en la mano al replanificar a mitad de un nivel:
    # no se ven en el tablero, hay que llevar la cuenta.
    keys_in_hand = 0

    while solved < args.levels:

        captured = capture_game()

        if captured is None:
            print("ERROR: no se encontró Diamond Rush en pantalla.")
            return

        game, grab = captured

        plan = plan_level(
            agent,
            game,
            keys_in_hand,
            replanning=started
        )

        if plan is None:
            return

        if args.dry_run:
            return

        def watch_plates(pos, beyond):
            # Algo acaba de pisar una placa (el jugador, o una
            # roca empujada): es el momento de ver qué reja abre.
            if (
                pos not in agent.plates
                and beyond not in agent.plates
            ):
                return False

            # Dar tiempo a que la reja termine de moverse.
            time.sleep(GATE_ANIMATION)

            return agent.look(grab(), pos)

        started = True

        done, status = execute_plan(
            plan,
            find_cells(agent.grid, PLAYER)[0],
            grab,
            args.delay,
            watch_plates
        )

        if status != "done":

            keys_in_hand = keys_in_hand_after(
                agent.grid,
                plan[:done],
                keys_in_hand
            )

        if status == "interrupted":

            print_learned(agent)
            print("Vuelvo a planificar con lo aprendido...")

            # Que el jugador se baje de la placa no debe
            # confundirse con el estado estable del nivel.
            continue

        if status == "blocked":

            print(
                f"El movimiento {done + 1} de {len(plan)} "
                f"({plan[done]}) no tuvo efecto en el juego."
            )

            if done == 0:
                print(
                    "El juego no está recibiendo las teclas "
                    "o el tablero se leyó mal."
                )
                return

            replans += 1

            if replans > args.replans:
                return

            print("Vuelvo a leer el tablero y a planificar...")
            continue

        solved += 1
        replans = 0
        started = False
        keys_in_hand = 0

        if solved < args.levels:
            # Esperar la transición al siguiente nivel.
            time.sleep(args.level_wait)

    print("Listo.")


def main():

    parser = argparse.ArgumentParser(
        description="Agente que juega Diamond Rush."
    )

    parser.add_argument(
        "--image",
        help="Resolver una imagen del área del juego sin tocar el teclado"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Capturar y planificar, sin enviar teclas"
    )

    parser.add_argument(
        "--levels",
        type=int,
        default=1,
        help="Cantidad de niveles consecutivos a jugar"
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Pausa extra tras comprobar cada movimiento"
    )

    parser.add_argument(
        "--replans",
        type=int,
        default=6,
        help="Veces que se replanifica si un movimiento falla"
    )

    parser.add_argument(
        "--countdown",
        type=float,
        default=4,
        help="Segundos para dar foco a la ventana del juego"
    )

    parser.add_argument(
        "--level-wait",
        type=float,
        default=4,
        help="Segundos de espera entre un nivel y el siguiente"
    )

    args = parser.parse_args()

    if args.image:

        game = cv2.imread(args.image)

        if game is None:
            print(f"No se pudo leer la imagen: {args.image}")
            return

        plan_level(
            DiamondRushAgent(),
            game
        )

        return

    play(args)


if __name__ == "__main__":
    main()
