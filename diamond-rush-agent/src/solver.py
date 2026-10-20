import heapq
from collections import deque
from itertools import permutations

from level_reader import (
    WALL,
    DIAMOND,
    PLAYER,
    EXIT,
    LAVA,
    SPIKE,
    KEY,
    DOOR,
    ROCK,
    HOLE,
    PLATE,
    GATE,
    RAISED,
    FLOOR,
    UNKNOWN,
    find_cells
)


# ----------------------------------------------------
# Reglas del juego asumidas por el planificador
# ----------------------------------------------------

# La salida solo se abre con todos los diamantes.
REQUIRE_ALL_DIAMONDS = True

# Las púas se activan al salir de la casilla:
# cada trampa se puede pisar una sola vez.
SPIKES_SINGLE_USE = True

# El jugador carga una sola llave: si pasa sobre otra
# con la mano ocupada, la llave se queda en el piso.
MAX_KEYS_IN_HAND = 1

# Las rocas se empujan una casilla si detrás hay piso libre.
# Una roca empujada a un hueco lo rellena y deja piso;
# un hueco sin rellenar no se puede pisar.
ROCK_LANDING = (FLOOR, PLAYER, ROCK, HOLE, PLATE)

# Una reja solo se puede cruzar mientras haya una roca sobre
# su placa de presión: el jugador puede pisar la placa, pero
# al bajarse la reja vuelve a cerrarse.
# El juego no muestra qué placa abre qué reja. Se prueban los
# emparejamientos posibles, del más cercano al más lejano, y
# se usa el primero con el que el nivel tiene solución: un
# nivel siempre se puede resolver, así que un emparejamiento
# sin solución no puede ser el real. Los pares que el juego
# desmiente (ver agent.py) se descartan.
# Antes de apostar por un emparejamiento se busca un plan que
# valga para todos los que siguen siendo posibles: no cruza
# una reja hasta tener roca en todas las placas que podrían
# ser la suya. Equivocarse de placa suele dejar las rocas
# donde ya no sirven, y eso no tiene arreglo sin reiniciar.
MAX_LINK_OPTIONS = 60

# Debajo de una roca puede haber púas que no se ven hasta
# moverla. Por cautela se planifica como si cada casilla que
# empieza con una roca fuera una trampa de un solo uso.
CAUTIOUS_EXPANSIONS = 100_000

# Límite de expansiones (regiones, ver explore) antes de rendirse.
MAX_EXPANSIONS = 400_000

# Primero se busca el plan más corto; si el nivel es demasiado
# grande para eso, se repite con A* ponderado, que encuentra
# un plan válido (no necesariamente el más corto) mucho antes.
OPTIMAL_EXPANSIONS = 10_000
FALLBACK_WEIGHT = 2

# En esa segunda búsqueda, costo extra por diamante sin recoger.
FALLBACK_MISSING_PENALTY = 5


MOVES = (
    ("up", -1, 0),
    ("down", 1, 0),
    ("left", 0, -1),
    ("right", 0, 1)
)

BLOCKED = (WALL, LAVA, RAISED, UNKNOWN)


def manhattan(a, b):

    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def link_options(gates, plates, excluded=()):
    """
    Emparejamientos {reja: placa} posibles, del de menor
    distancia total al de mayor. Las rejas que queden sin
    placa no se abren nunca.

    excluded: pares (reja, placa) que ya se sabe que no van.
    """

    if len(gates) <= len(plates):
        options = [
            dict(zip(gates, chosen))
            for chosen in permutations(plates, len(gates))
        ]
    else:
        options = [
            dict(zip(chosen, plates))
            for chosen in permutations(gates, len(plates))
        ]

    options = [
        option
        for option in options
        if not any(pair in excluded for pair in option.items())
    ]

    options.sort(
        key=lambda option: sum(
            manhattan(gate, plate)
            for gate, plate in option.items()
        )
    )

    return options or [{}]


def solve(grid, keys_in_hand=0, plates=(), excluded=()):
    """
    Busca la secuencia de movimientos que recoge todos
    los diamantes y llega a la salida.

    keys_in_hand: llaves que el jugador ya trae consigo
    (al replanificar a mitad de un nivel).
    plates: placas que el tablero no muestra porque
    tienen una roca encima.
    excluded: pares (reja, placa) descartados.

    Devuelve (plan, enlaces): la lista de "up" / "down" /
    "left" / "right" y, para cada reja, las placas que el
    plan mantiene con roca al cruzarla; (None, {}) si no
    hay solución.
    """

    options = link_options(
        find_cells(grid, GATE),
        sorted(set(find_cells(grid, PLATE)) | set(plates)),
        excluded
    )

    # {reja: placas que deben tener roca para cruzarla}
    candidates = [
        {
            gate: frozenset(
                option[gate]
                for option in options
                if gate in option
            )
            for gate in options[0]
        }
    ]

    for option in options[:MAX_LINK_OPTIONS]:

        links = {
            gate: frozenset([plate])
            for gate, plate in option.items()
        }

        if links not in candidates:
            candidates.append(links)

    # Debajo de una roca puede haber púas (HIDDEN_SPIKES):
    # con cada emparejamiento se intenta primero un plan que
    # no dependa de que no las haya.
    attempts = [
        (links, hidden_spikes)
        for links in candidates
        for hidden_spikes in (True, False)
    ]

    for links, hidden_spikes in attempts:

        last = (links, hidden_spikes) == attempts[-1]

        plan, exhausted = search(
            grid,
            1,
            OPTIMAL_EXPANSIONS,
            keys_in_hand,
            hidden_spikes=hidden_spikes,
            links=links
        )

        if plan is None and not exhausted:

            plan, _ = search(
                grid,
                FALLBACK_WEIGHT,
                MAX_EXPANSIONS if last else CAUTIOUS_EXPANSIONS,
                keys_in_hand,
                FALLBACK_MISSING_PENALTY,
                hidden_spikes,
                links
            )

        if plan is not None:
            return plan, links

    return None, {}


def search(
    grid,
    weight,
    max_expansions,
    keys_in_hand=0,
    missing_penalty=0,
    hidden_spikes=False,
    links=None
):
    """
    A* (ponderado si weight > 1) sobre el estado del nivel.

    No avanza paso a paso sino por acciones: cada expansión
    agrupa todo lo que el jugador puede caminar sin alterar
    el nivel (ver explore) y solo ramifica en los pasos que
    sí lo alteran. Las reglas del juego viven en step().

    Estado: (fila, columna, diamantes recogidos,
             llaves disponibles en el piso, llaves en mano,
             puertas abiertas, púas usadas,
             posiciones de las rocas, huecos rellenados)

    Devuelve (plan, agotado): agotado indica que se exploró
    todo el espacio de estados, es decir, que no hay solución.
    """

    players = find_cells(grid, PLAYER)

    if not players:
        return None, True

    start = players[0]

    exits = find_cells(grid, EXIT)
    goal = exits[0] if exits else None

    rows = len(grid)
    cols = len(grid[0])

    # Cada objeto recibe un bit dentro de su máscara.
    diamonds = {
        cell: 1 << i
        for i, cell in enumerate(find_cells(grid, DIAMOND))
    }
    keys = {
        cell: 1 << i
        for i, cell in enumerate(find_cells(grid, KEY))
    }
    doors = {
        cell: 1 << i
        for i, cell in enumerate(find_cells(grid, DOOR))
    }
    spikes = {
        cell: 1 << i
        for i, cell in enumerate(find_cells(grid, SPIKE))
    }

    holes = {
        cell: 1 << i
        for i, cell in enumerate(find_cells(grid, HOLE))
    }

    start_rocks = frozenset(find_cells(grid, ROCK))

    if links is None:
        links = {
            gate: frozenset([plate])
            for gate, plate in link_options(
                find_cells(grid, GATE),
                find_cells(grid, PLATE)
            )[0].items()
        }

    def gate_open(gate, rocks):
        # Abierta si todas sus placas tienen una roca encima.
        needed = links.get(gate)

        return needed is not None and needed <= rocks

    if hidden_spikes:

        for cell in start_rocks:
            spikes[cell] = 1 << len(spikes)

    all_diamonds = (1 << len(diamonds)) - 1

    def heuristic(pos, collected):

        missing = [
            cell
            for cell, bit in diamonds.items()
            if not collected & bit
        ]

        if not missing:
            return manhattan(pos, goal) if goal else 0

        # Empuja la búsqueda hacia estados con más diamantes
        # recogidos (solo en la búsqueda no óptima).
        extra = missing_penalty * len(missing)

        if goal is None:
            return extra + max(
                manhattan(pos, cell)
                for cell in missing
            )

        # Hay que pasar por el diamante más costoso
        # y después llegar a la salida.
        return extra + max(
            manhattan(pos, cell) + manhattan(cell, goal)
            for cell in missing
        )

    def is_goal(pos, collected):

        if goal is None:
            return collected == all_diamonds

        return pos == goal

    def can_hold_rock(cell, collected, taken, opened, used, rocks):
        # Una casilla ya vaciada (llave recogida,
        # puerta abierta) se comporta como piso.
        symbol = grid[cell[0]][cell[1]]

        if cell in spikes:
            # Una roca puede quedar sobre púas aún sin activar.
            return not used & spikes[cell]

        if symbol in ROCK_LANDING:
            return True

        if symbol == DIAMOND:
            # Una roca puede pasar por encima de un diamante:
            # el diamante sigue ahí cuando la roca se aparta.
            return True

        if symbol == KEY:
            return bool(taken & keys[cell])

        if symbol == DOOR:
            return bool(opened & doors[cell])

        if symbol == GATE:
            # Por una reja abierta también pasa una roca. No
            # cuenta la roca que se está empujando: si era la
            # que pisaba la placa, la reja se cierra.
            return gate_open(cell, rocks)

        return False

    def step(state, dr, dc):
        """
        Aplica un movimiento del jugador.

        Devuelve el estado resultante, o None si el
        movimiento no es posible.
        """

        (
            pos, collected, taken, in_hand,
            opened, used, rocks, filled
        ) = state

        r = pos[0] + dr
        c = pos[1] + dc

        if not (0 <= r < rows and 0 <= c < cols):
            return None

        target = (r, c)
        symbol = grid[r][c]

        if symbol in BLOCKED:
            return None

        if target in spikes and used & spikes[target]:
            return None

        if target in rocks:

            # Empujar la roca una casilla más allá.
            br = r + dr
            bc = c + dc

            if not (0 <= br < rows and 0 <= bc < cols):
                return None

            beyond = (br, bc)

            if (
                beyond in rocks
                or not can_hold_rock(
                    beyond,
                    collected,
                    taken,
                    opened,
                    used,
                    rocks - {target}
                )
            ):
                return None

            rocks = rocks - {target}

            if (
                beyond in holes
                and not filled & holes[beyond]
            ):
                filled |= holes[beyond]
            else:
                rocks = rocks | {beyond}

        elif symbol == HOLE:

            if not filled & holes[target]:
                return None

        elif symbol == GATE:

            if not gate_open(target, rocks):
                return None

        if symbol == EXIT:

            if (
                REQUIRE_ALL_DIAMONDS
                and collected != all_diamonds
            ):
                return None

        elif symbol == DIAMOND:

            collected |= diamonds[target]

        elif symbol == KEY:

            if (
                not taken & keys[target]
                and in_hand < MAX_KEYS_IN_HAND
            ):
                taken |= keys[target]
                in_hand += 1

        elif symbol == DOOR:

            if not opened & doors[target]:

                if in_hand == 0:
                    return None

                in_hand -= 1
                opened |= doors[target]

        # Al salir de una trampa, las púas quedan arriba.
        if SPIKES_SINGLE_USE and pos in spikes:
            used |= spikes[pos]

        return (
            target, collected, taken, in_hand,
            opened, used, rocks, filled
        )

    def explore(state):
        """
        Recorre todas las casillas a las que el jugador llega
        caminando sin que cambie nada más en el nivel.

        Devuelve (región, acciones). Cada acción es
        (movimientos, estado): el camino hasta el borde de
        la región más el paso que sí cambia el nivel (empujar
        una roca, abrir una puerta, gastar una trampa...).

        Buscar sobre estas acciones, y no paso a paso, es lo
        que permite resolver niveles largos: dos posiciones
        dentro de la misma región son el mismo estado.
        """

        rest = state[1:]

        previous = {state[0]: None}
        queue = deque([state])

        actions = []

        def path_to(pos, last):

            path = [last]

            while previous[pos] is not None:
                pos, name = previous[pos]
                path.append(name)

            path.reverse()

            return path

        while queue:

            current = queue.popleft()

            for name, dr, dc in MOVES:

                following = step(current, dr, dc)

                if following is None:
                    continue

                changed = following[1:]

                if changed == rest and following[0] != goal:

                    if following[0] not in previous:
                        previous[following[0]] = (current[0], name)
                        queue.append(following)

                    continue

                action = (path_to(current[0], name), following)

                if (
                    missing_penalty
                    and changed[:3] != rest[:3]
                    and changed[3:] == rest[3:]
                ):
                    # Recoger un diamante o una llave al alcance
                    # nunca perjudica. En la búsqueda no óptima
                    # se hace siempre, sin considerar alternativas.
                    return None, [action]

                actions.append(action)

        return min(previous), actions

    def priority(state, new_cost):

        return new_cost + weight * heuristic(
            state[0],
            state[1]
        )

    start_state = (
        start, 0, 0, keys_in_hand, 0, 0, start_rocks, 0
    )

    parents = {start_state: None}
    cost = {start_state: 0}

    # Regiones ya expandidas (ver explore).
    closed = set()

    counter = 0
    frontier = [
        (priority(start_state, 0), counter, start_state)
    ]

    expansions = 0

    while frontier:

        _, _, state = heapq.heappop(frontier)

        if is_goal(state[0], state[1]):
            return rebuild_path(parents, state), False

        region, actions = explore(state)

        if region is not None:

            if missing_penalty:
                key = (region,) + state[1:]
            else:
                # La búsqueda óptima distingue en qué casilla
                # de la región quedó el jugador: de eso depende
                # cuánto cuesta el siguiente tramo.
                key = state

            if key in closed:
                continue

            closed.add(key)

        expansions += 1

        if expansions > max_expansions:
            return None, False

        for path, next_state in actions:

            new_cost = cost[state] + len(path)

            if new_cost >= cost.get(next_state, float("inf")):
                continue

            cost[next_state] = new_cost
            parents[next_state] = (state, path)

            counter += 1

            heapq.heappush(
                frontier,
                (
                    priority(next_state, new_cost),
                    counter,
                    next_state
                )
            )

    return None, True


def keys_in_hand_after(grid, plan, keys_in_hand=0):
    """
    Llaves que el jugador tiene en la mano tras ejecutar plan
    sobre grid, empezando con keys_in_hand.
    """

    pos = find_cells(grid, PLAYER)[0]

    deltas = {name: (dr, dc) for name, dr, dc in MOVES}

    taken = set()
    opened = set()

    for move in plan:

        dr, dc = deltas[move]
        pos = (pos[0] + dr, pos[1] + dc)

        symbol = grid[pos[0]][pos[1]]

        if symbol == KEY:

            if (
                pos not in taken
                and keys_in_hand < MAX_KEYS_IN_HAND
            ):
                taken.add(pos)
                keys_in_hand += 1

        elif symbol == DOOR and pos not in opened:

            opened.add(pos)
            keys_in_hand -= 1

    return keys_in_hand


def rebuild_path(parents, state):

    pieces = []

    while parents[state] is not None:
        state, path = parents[state]
        pieces.append(path)

    pieces.reverse()

    return [
        move
        for path in pieces
        for move in path
    ]


def format_plan(plan):
    """
    ["right", "right", "down"] -> "right x2, down x1"
    """

    groups = []

    for move in plan:

        if groups and groups[-1][0] == move:
            groups[-1][1] += 1
        else:
            groups.append([move, 1])

    return ", ".join(
        f"{move} x{count}"
        for move, count in groups
    )
