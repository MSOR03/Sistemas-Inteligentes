from collections import deque

from level_reader import (
    DIAMOND,
    EXIT,
    FLOOR,
    PLAYER,
    ROCK,
    UNSEEN,
    WALL,
    find_cells
)
from solver import (
    MOVES,
    format_plan,
    keys_in_hand_after,
    manhattan,
    solve
)
from stitcher import MapOverflow


# Al explorar solo se pisa lo que no cambia el nivel: piso y
# diamantes (recogerlos antes no estorba al plan). Nada de
# rocas, llaves, placas, púas ni la salida.
WALKABLE = (FLOOR, DIAMOND, PLAYER)

# Movimientos máximos de cada paseo de exploración.
MAX_EXPLORE_MOVES = 400

# Si caminando no se llega a ver más, se busca con el
# planificador (empujando rocas, abriendo puertas...) cómo
# acercarse a las fronteras más cercanas: cuántas se prueban
# por ronda, y cuántas rondas como mucho.
PUSH_ATTEMPTS = 3
MAX_PUSH_ROUNDS = 20

# Expansiones máximas del planificador en cada una de esas
# consultas: una frontera inalcanzable no debe costar minutos.
PUSH_BUDGET = 20_000


def cell_after(start, moves):
    """
    Casilla a la que llevan los movimientos desde start.
    """

    deltas = {name: (dr, dc) for name, dr, dc in MOVES}

    row, col = start

    for move in moves:
        dr, dc = deltas[move]
        row, col = row + dr, col + dc

    return row, col


def frontier(grid):
    """
    Casillas sin ver junto a una casilla vista que no es
    muro: por ahí el nivel puede seguir fuera de la pantalla.

    Las rocas no cuentan: en la fila a medio ver del borde
    inferior, un muro de ladrillo a veces se lee como roca.
    """

    cells = set()

    for r, row in enumerate(grid):

        for c, value in enumerate(row):

            if value in (UNSEEN, WALL, ROCK):
                continue

            for _, dr, dc in MOVES:

                rr, cc = r + dr, c + dc

                if (
                    0 <= rr < len(grid)
                    and 0 <= cc < len(grid[rr])
                    and grid[rr][cc] == UNSEEN
                ):
                    cells.add((rr, cc))

    return cells


def player_grid(level_map, templates, pos):
    """
    Tablero del mapa con el jugador donde se sabe que está
    (pos, en coordenadas del mapa).
    """

    grid = level_map.read(templates)

    here = level_map.to_grid(pos)

    for row, col in find_cells(grid, PLAYER):
        grid[row][col] = FLOOR

    grid[here[0]][here[1]] = PLAYER

    return grid


def walkable_from(grid, start, avoid=()):
    """
    Casillas a las que se llega caminando desde start, con
    el movimiento que lleva a cada una: {casilla: (anterior, movimiento)}.
    """

    parents = {start: None}
    queue = deque([start])

    while queue:

        cell = queue.popleft()

        for name, dr, dc in MOVES:

            nxt = (cell[0] + dr, cell[1] + dc)

            if (
                nxt in parents
                or nxt in avoid
                or not 0 <= nxt[0] < len(grid)
                or not 0 <= nxt[1] < len(grid[nxt[0]])
                or grid[nxt[0]][nxt[1]] not in WALKABLE
            ):
                continue

            parents[nxt] = (cell, name)
            queue.append(nxt)

    return parents


def path_to(parents, goal):

    moves = []

    while parents[goal] is not None:
        goal, name = parents[goal]
        moves.append(name)

    return moves[::-1]


def route(grid, start, targets, avoid=()):
    """
    Camino (solo por casillas WALKABLE) a la casilla más
    cercana a alguno de los objetivos; a igual cercanía, la
    de camino más corto.

    Devuelve (movimientos, objetivo) o None.
    """

    parents = walkable_from(grid, start, avoid)

    distance = {
        cell: len(path_to(parents, cell))
        for cell in parents
    }

    _, _, goal, target = min(
        (manhattan(cell, target), distance[cell], cell, target)
        for cell in parents
        for target in targets
    )

    return path_to(parents, goal), target


def explore(
    level_map,
    templates,
    grab,
    start,
    step_delay=0.05,
    max_moves=MAX_EXPLORE_MOVES,
    exhausted=None
):
    """
    Pasea al jugador hacia los bordes sin ver del nivel para
    que la cámara los muestre, hasta que no quede frontera
    alcanzable (o se acaben los movimientos).

    start: casilla del jugador en coordenadas del mapa.
    exhausted: fronteras que ya no vale la pena intentar
    (coordenadas del mapa); se completa con las de este paseo.
    Devuelve la casilla final del jugador, también del mapa.
    """

    # Import diferido: leer el mapa no necesita el teclado.
    from controller import execute_plan

    pos = start
    moves = 0

    # Fronteras que no se revelaron al acercarse y casillas
    # que resultaron no ser transitables, en coordenadas del mapa.
    if exhausted is None:
        exhausted = set()

    blocked = set()

    while moves < max_moves:

        grid = player_grid(level_map, templates, pos)

        here = level_map.to_grid(pos)

        targets = {
            cell
            for cell in frontier(grid)
            if level_map.to_map(cell) not in exhausted
        }

        if not targets:
            break

        path, target = route(
            grid,
            here,
            targets,
            {level_map.to_grid(cell) for cell in blocked}
        )

        # Se intenta revelar cada frontera una sola vez.
        exhausted.add(level_map.to_map(target))

        if not path:
            continue

        path = path[:max_moves - moves]

        print(f"Exploro hacia {target}: {format_plan(path)}")

        try:
            done, status = execute_plan(
                path,
                here,
                grab,
                step_delay,
                camera=level_map,
                ends_in_exit=False
            )
        except MapOverflow as error:
            print(f"AVISO: {error}. Dejo de explorar.")
            break

        moves += done
        pos = level_map.to_map(cell_after(here, path[:done]))

        if status == "blocked":

            cell = cell_after(here, path[:done + 1])

            print(
                f"La casilla {cell} no se pudo pisar; "
                f"la evito al explorar."
            )

            blocked.add(level_map.to_map(cell))

    else:
        print(
            f"AVISO: exploré {moves} movimientos sin ver "
            f"todo el nivel; planifico con lo visto."
        )

    return pos


def reach_frontier(
    level_map,
    templates,
    grab,
    pos,
    keys_in_hand,
    tried,
    step_delay=0.05
):
    """
    Usa el planificador para llegar junto a una frontera a la
    que no se llega caminando: la casilla vista de al lado se
    trata como la salida, sin diamantes que recoger y con la
    salida real cerrada.

    tried: fronteras ya intentadas (coordenadas del mapa).
    Devuelve (casilla del jugador, llaves en la mano, si se movió).
    """

    from controller import execute_plan

    grid = player_grid(level_map, templates, pos)

    here = level_map.to_grid(pos)

    # Lo que se alcanza caminando ya lo probó explore().
    walkable = walkable_from(grid, here)

    targets = sorted(
        (
            cell
            for cell in frontier(grid)
            if level_map.to_map(cell) not in tried
        ),
        key=lambda cell: manhattan(cell, here)
    )

    for target in targets[:PUSH_ATTEMPTS]:

        tried.add(level_map.to_map(target))

        for _, dr, dc in MOVES:

            stand = (target[0] - dr, target[1] - dc)

            if (
                stand in walkable
                or not 0 <= stand[0] < len(grid)
                or not 0 <= stand[1] < len(grid[0])
                or grid[stand[0]][stand[1]] not in (FLOOR, DIAMOND)
            ):
                continue

            trial = [
                [
                    FLOOR if value == DIAMOND
                    else WALL if value == EXIT
                    else value
                    for value in row
                ]
                for row in grid
            ]

            trial[stand[0]][stand[1]] = EXIT

            plan, _ = solve(trial, keys_in_hand, budget=PUSH_BUDGET)

            if not plan:
                continue

            print(
                f"Para ver más allá de {target} voy a {stand}: "
                f"{format_plan(plan)}"
            )

            try:
                done, status = execute_plan(
                    plan,
                    here,
                    grab,
                    step_delay,
                    camera=level_map,
                    ends_in_exit=False
                )
            except MapOverflow as error:
                print(f"AVISO: {error}.")
                return pos, keys_in_hand, False

            keys_in_hand = keys_in_hand_after(
                grid,
                plan[:done],
                keys_in_hand
            )

            pos = level_map.to_map(cell_after(here, plan[:done]))

            return pos, keys_in_hand, done > 0

    return pos, keys_in_hand, False


def map_level(
    level_map,
    templates,
    grab,
    start,
    step_delay=0.05,
    max_moves=MAX_EXPLORE_MOVES
):
    """
    Explora el nivel hasta que no quede frontera, o hasta que
    lo visto ya alcance para terminarlo (hay salida y plan).

    Primero solo camina. Empujar rocas puede dejar el nivel
    sin solución, así que el planificador solo se usa cuando
    caminando ya no se ve más y lo visto no alcanza.

    start: casilla del jugador en coordenadas del mapa.
    Devuelve (casilla del jugador en el mapa, llaves en la mano).
    """

    exhausted = set()

    pos = explore(
        level_map,
        templates,
        grab,
        start,
        step_delay,
        max_moves,
        exhausted
    )

    keys_in_hand = 0
    tried = set()

    for _ in range(MAX_PUSH_ROUNDS):

        grid = player_grid(level_map, templates, pos)

        if not frontier(grid):
            print("Exploración terminada: no quedan bordes sin ver.")
            break

        # Sin salida a la vista el solver se conforma con los
        # diamantes visibles: no sirve para saber si basta.
        if (
            find_cells(grid, EXIT)
            and solve(grid, keys_in_hand)[0] is not None
        ):
            print("Con lo visto ya se puede terminar el nivel.")
            break

        pos, keys_in_hand, moved = reach_frontier(
            level_map,
            templates,
            grab,
            pos,
            keys_in_hand,
            tried,
            step_delay
        )

        if not moved:
            print(
                "AVISO: no encuentro cómo ver el resto del nivel; "
                "planifico con lo visto."
            )
            break

        pos = explore(
            level_map,
            templates,
            grab,
            pos,
            step_delay,
            max_moves,
            exhausted
        )

    return pos, keys_in_hand
