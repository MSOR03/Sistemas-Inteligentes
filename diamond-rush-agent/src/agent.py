import json
from pathlib import Path

from cell_classifier import load_templates
from level_reader import (
    FLOOR,
    GATE,
    PLATE,
    PLAYER,
    ROCK,
    find_cells,
    format_grid,
    prepare_templates,
    read_level
)
from solver import solve


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CELL_TEMPLATES = (
    PROJECT_ROOT
    / "assets"
    / "templates"
    / "cells"
)

# Lo que el agente aprende jugando, por nivel.
KNOWLEDGE_FILE = PROJECT_ROOT / "knowledge.json"


class DiamondRushAgent:
    """
    Agente basado en objetivos para Diamond Rush.

    La percepción (imagen del juego) se recoge afuera;
    compute() la transforma en un tablero lógico y
    planifica la secuencia completa de movimientos.
    """

    def __init__(
        self,
        template_dir=CELL_TEMPLATES,
        knowledge_file=KNOWLEDGE_FILE
    ):

        self.templates = prepare_templates(
            load_templates(
                str(template_dir)
            )
        )

        # Último tablero percibido, útil para depurar.
        self.grid = None

        # Memoria del nivel en curso: su tablero inicial (lo
        # identifica), dónde están sus rejas y placas, y qué
        # placa se supuso que abre cada reja en el último plan.
        self.level = None
        self.gates = []
        self.plates = []
        self.links = {}

        # Pares (reja, placa) descartados en la última lectura.
        self.learned = []

        # Pares (reja, placa) que el juego desmintió, por nivel.
        self.knowledge_file = Path(knowledge_file)
        self.knowledge = {}

        if self.knowledge_file.exists():
            self.knowledge = json.loads(
                self.knowledge_file.read_text()
            )

    def excluded(self):

        return {
            (tuple(gate), tuple(plate))
            for gate, plate in self.knowledge.get(self.level, [])
        }

    def compute(self, percept, keys_in_hand=0, replanning=False):
        """
        percept: imagen BGR del área del juego.
        keys_in_hand: llaves que el jugador ya trae consigo.
        replanning: el nivel ya estaba empezado (se conserva
        la memoria del nivel en lugar de reiniciarla).

        Devuelve la lista de acciones
        ("up", "down", "left", "right") o None
        si no encuentra un plan.
        """

        grid = read_level(
            percept,
            self.templates
        )

        self.learned = []

        if replanning and self.level is not None:

            self.observe(grid)

            # Una reja abierta no se ve como reja, pero volverá
            # a cerrarse si su placa queda libre.
            for row, col in self.gates:

                if grid[row][col] not in (PLAYER, ROCK):
                    grid[row][col] = GATE

        else:

            self.level = format_grid(grid)
            self.gates = find_cells(grid, GATE)
            self.plates = find_cells(grid, PLATE)

        self.grid = grid

        plan, self.links = solve(
            grid,
            keys_in_hand,
            self.plates,
            self.excluded()
        )

        return plan

    def look(self, percept, player):
        """
        Mira el tablero en mitad de un plan, justo cuando algo
        acaba de pisar una placa, para ver qué reja reaccionó.

        player: casilla del jugador (su peso también cuenta
        mientras está sobre una placa).

        Devuelve True si aprendió algo nuevo: el plan en curso
        puede haber quedado obsoleto.
        """

        self.learned = []

        self.observe(
            read_level(percept, self.templates),
            player
        )

        return bool(self.learned)

    def observe(self, grid, player=None):
        """
        Aprende qué placa abre qué reja mirando el tablero a
        mitad del nivel: una reja que sigue cerrada no es de
        ninguna placa que tenga peso encima, y una que se ve
        abierta solo puede ser de alguna de esas.

        Lo aprendido se guarda por nivel, así que también
        sirve en la siguiente partida. Deja en self.learned
        los pares (reja, placa) recién descartados.
        """

        pressed = [
            plate
            for plate in self.plates
            if grid[plate[0]][plate[1]] in (ROCK, PLAYER)
            or plate == player
        ]

        if not pressed:
            return

        pairs = self.knowledge.setdefault(self.level, [])

        for gate in self.gates:

            symbol = grid[gate[0]][gate[1]]

            if symbol == GATE:
                wrong = pressed
            elif symbol == FLOOR:
                wrong = [
                    plate
                    for plate in self.plates
                    if plate not in pressed
                ]
            else:
                continue

            for plate in wrong:

                pair = [list(gate), list(plate)]

                if pair not in pairs:
                    pairs.append(pair)
                    self.learned.append((gate, plate))

        if self.learned:
            self.knowledge_file.write_text(
                json.dumps(self.knowledge, indent=2)
            )
