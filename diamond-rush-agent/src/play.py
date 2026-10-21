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
    DOOR,
    EXIT,
    PLAYER,
    UNKNOWN,
    cell_image,
    find_cells,
    format_grid
)
from explorer import MAX_EXPLORE_MOVES, cell_after, frontier
from solver import format_plan, keys_in_hand_after
from stitcher import LevelMap


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


# Pantalla completa de la última lectura, para comprobar que
# el recorte del juego no deja parte del tablero afuera.
LAST_SCREEN = (
    PROJECT_ROOT
    / "screenshots"
    / "last_screen.png"
)


# Mapa armado al explorar un nivel más grande que la pantalla.
LAST_MAP = (
    PROJECT_ROOT
    / "screenshots"
    / "last_map.png"
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
    cv2.imwrite(str(LAST_SCREEN), screen)

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


def explore_level(agent, game, grab, args):
    """
    Si el nivel sigue fuera de la pantalla, pasea al jugador
    para que la cámara lo muestre entero y arma su mapa.

    Devuelve (mapa, casilla del jugador en su tablero, llaves
    en la mano), o (None, None, 0) si el nivel cabe en pantalla.
    """

    from explorer import map_level

    level_map = LevelMap(game)

    grid = level_map.read(agent.templates)

    players = find_cells(grid, PLAYER)

    # Con la salida a la vista el nivel cabe en pantalla: una
    # fila abierta junto al HUD no es razón para pasear.
    if (
        not frontier(grid)
        or not players
        or find_cells(grid, EXIT)
    ):
        return None, None, 0

    print()
    print(format_grid(grid))
    print()

    if args.dry_run:
        print(
            "El nivel sigue fuera de la pantalla (~ = sin ver); "
            "sin enviar teclas no puedo explorarlo."
        )
        return None, None, 0

    print("El nivel sigue fuera de la pantalla: lo exploro...")

    pos, keys_in_hand = map_level(
        level_map,
        agent.templates,
        grab,
        level_map.to_map(players[0]),
        args.delay,
        args.explore_moves
    )

    level_map.freeze()
    level_map.save(LAST_MAP)

    print(f"Mapa del nivel guardado en {LAST_MAP}")

    return level_map, level_map.to_grid(pos), keys_in_hand


def plan_level(
    agent,
    percept,
    keys_in_hand=0,
    replanning=False,
    player=None
):
    """
    Percibe, planifica y muestra el resultado.

    percept: imagen del juego o mapa del nivel (LevelMap).
    player: casilla conocida del jugador al replanificar.
    """

    plan = agent.compute(percept, keys_in_hand, replanning, player)

    print()
    print(format_grid(agent.grid))
    print()

    if isinstance(percept, LevelMap):
        game = percept.image()
    else:
        game = percept

    save_unknown_cells(game, agent.grid)

    print_learned(agent)

    if not find_cells(agent.grid, PLAYER):
        print("No se encontró al jugador en el tablero.")
        return None

    # Sin salida el solver solo pide los diamantes visibles: con
    # ninguno a la vista, el plan vacío daría el nivel por ganado.
    if not find_cells(agent.grid, EXIT):
        print("No se ve la salida: falta ver parte del nivel.")
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

    from controller import execute_plan, wait_until_still

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

    # Casilla del jugador al replanificar: el controlador
    # comprobó cada paso en pantalla, así que se sabe dónde
    # está aunque su imagen no se reconozca.
    player = None

    # Mapa del nivel en curso si no cabe en pantalla: se conserva
    # al replanificar, porque una captura nueva solo ve una parte.
    level_map = None

    while solved < args.levels:

        if level_map is None:

            captured = capture_game()

            if captured is None:
                print("ERROR: no se encontró Diamond Rush en pantalla.")
                return

            game, grab = captured

        if not started:

            level_map, player, keys_in_hand = explore_level(
                agent,
                game,
                grab,
                args
            )

        elif level_map is not None:

            level_map.update(grab())

        plan = plan_level(
            agent,
            level_map if level_map is not None else game,
            keys_in_hand,
            replanning=started,
            player=player
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

            # Dar tiempo a que la reja termine de moverse: si se
            # mira a mitad de la animación, se aprende algo falso.
            time.sleep(GATE_ANIMATION)

            if level_map is None:
                wait_until_still(grab, agent.gates)
                return agent.look(grab(), pos)

            wait_until_still(grab, agent.gates, level_map.offset)
            level_map.update(grab())

            return agent.look(level_map, pos)

        started = True

        start = find_cells(agent.grid, PLAYER)[0]

        done, status = execute_plan(
            plan,
            start,
            grab,
            args.delay,
            watch_plates,
            camera=level_map
        )

        if status != "done":

            keys_in_hand = keys_in_hand_after(
                agent.grid,
                plan[:done],
                keys_in_hand
            )

            player = cell_after(start, plan[:done])

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

            row, col = cell_after(start, plan[:done + 1])

            if agent.grid[row][col] == DOOR and keys_in_hand > 0:

                # La puerta no se abrió: el jugador no tiene
                # llave, aunque la cuenta diga lo contrario (una
                # celda leída como llave no lo era).
                print(
                    "La puerta no se abrió: el jugador no tiene "
                    "llave. Corrijo la cuenta de llaves."
                )

                keys_in_hand = 0

            elif done == 0:
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
        player = None
        level_map = None

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
        "--explore-moves",
        type=int,
        default=MAX_EXPLORE_MOVES,
        help="Movimientos máximos para explorar un nivel que no cabe en pantalla"
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
