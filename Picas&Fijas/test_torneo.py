# -*- coding: utf-8 -*-
"""
Banco de pruebas: replica EXACTAMENTE el ambiente oficial (Ambiente.ipynb) y
enfrenta el agente contra los rivales de la carpeta `examples`.

Uso:  python3 test_torneo.py [rondas_por_emparejamiento]
"""

import itertools
import math
import random
import sys
from collections import defaultdict

from Picas_Y_Fijas_Agent import AgentePicasFijas


# =============================================================================
#  Ambiente oficial (copiado del notebook, sin cambios de logica)
# =============================================================================

def es_intento_valido(lista):
    if not isinstance(lista, list) or len(lista) != 4:
        return False
    if not all(isinstance(x, int) and 0 <= x <= 9 for x in lista):
        return False
    if len(set(lista)) != 4:
        return False
    return True


def es_respuesta_valida(resp):
    if not isinstance(resp, list) or len(resp) != 2:
        return False
    if not all(isinstance(x, int) for x in resp):
        return False
    return resp[0] + resp[1] <= 4 and resp[0] >= 0 and resp[1] >= 0


def invocar_try(agente):
    if hasattr(agente, "try"):
        return getattr(agente, "try")()
    elif hasattr(agente, "try_attempt"):
        return agente.try_attempt()
    raise AttributeError("El agente no implementa ni 'try' ni 'try_attempt'.")


def jugar_ronda(agente1, agente2, verboso=False):
    """Devuelve (resultado, turnos, incidencias). resultado: 1, 2 o 0 (empate)."""
    incidencias = []
    agente1.start()
    agente2.start()

    for agente, etiqueta in ((agente1, "A1"), (agente2, "A2")):
        secreto = getattr(agente, "secret", None)
        if not es_intento_valido(secreto):
            incidencias.append("secreto invalido de %s: %r" % (etiqueta, secreto))

    for turno in range(1, 101):
        intento1 = invocar_try(agente1)
        intento2 = invocar_try(agente2)

        if not es_intento_valido(intento1):
            incidencias.append("intento invalido A1 turno %d: %r" % (turno, intento1))
        if not es_intento_valido(intento2):
            incidencias.append("intento invalido A2 turno %d: %r" % (turno, intento2))

        eval_para_1 = agente2.discover(intento1)
        eval_para_2 = agente1.discover(intento2)

        if not es_respuesta_valida(eval_para_1):
            incidencias.append("respuesta invalida A2 turno %d: %r" % (turno, eval_para_1))
        if not es_respuesta_valida(eval_para_2):
            incidencias.append("respuesta invalida A1 turno %d: %r" % (turno, eval_para_2))

        agente1.feedBack(eval_para_1)
        agente2.feedBack(eval_para_2)

        gana1 = isinstance(eval_para_1, list) and len(eval_para_1) == 2 and eval_para_1[1] == 4
        gana2 = isinstance(eval_para_2, list) and len(eval_para_2) == 2 and eval_para_2[1] == 4

        if verboso:
            print("  T%-3d %s -> %s | %s -> %s"
                  % (turno, intento1, eval_para_1, intento2, eval_para_2))

        if gana1 and gana2:
            return 0, turno, incidencias
        if gana1:
            return 1, turno, incidencias
        if gana2:
            return 2, turno, incidencias

    return 0, 100, incidencias


# =============================================================================
#  Rivales: los ejemplos de la carpeta, adaptados a la interfaz oficial
# =============================================================================

def _pf(intento, secreto):
    fijas = sum(a == b for a, b in zip(intento, secreto))
    comunes = sum(1 for d in set(intento) if d in set(secreto))
    return [comunes - fijas, fijas]


class RivalAleatorio:
    """Adivina al azar entre combinaciones validas."""
    nombre = "Aleatorio"

    def __init__(self):
        self.todos = list(itertools.permutations(range(10), 4))
        self.start()

    def start(self):
        self.secret = list(random.choice(self.todos))

    def try_attempt(self):
        return list(random.choice(self.todos))

    def discover(self, intento):
        return _pf(intento, self.secret)

    def feedBack(self, r):
        pass


class RivalConsistente:
    """Estilo `Cruceta`/`AgentA`: se queda con el primer candidato consistente."""
    nombre = "Consistente"

    def __init__(self):
        self.todos = list(itertools.permutations(range(10), 4))
        self.start()

    def start(self):
        self.secret = list(random.choice(self.todos))
        self.espacio = self.todos[:]
        self.ultimo = None

    def try_attempt(self):
        if self.ultimo is None:
            self.ultimo = self.espacio[0]
        return list(self.ultimo)

    def discover(self, intento):
        return _pf(intento, self.secret)

    def feedBack(self, r):
        if self.ultimo is None or not isinstance(r, list):
            return
        self.espacio = [c for c in self.espacio if _pf(list(c), list(self.ultimo)) == list(r)]
        self.ultimo = self.espacio[0] if self.espacio else random.choice(self.todos)


class RivalMinimax:
    """Estilo `Crucetero`: Knuth minimax sobre todo el espacio."""
    nombre = "Minimax"

    def __init__(self):
        self.todos = list(itertools.permutations(range(10), 4))
        self.start()

    def start(self):
        self.secret = list(random.choice(self.todos))
        self.candidatos = self.todos[:]
        self.ultimo = None

    @staticmethod
    def _s(g, c):
        fijas = sum(a == b for a, b in zip(g, c))
        comunes = sum(1 for d in set(g) if d in set(c))
        return (comunes - fijas, fijas)

    def try_attempt(self):
        if self.ultimo is None:
            self.ultimo = (0, 1, 2, 3)
            return list(self.ultimo)
        if len(self.candidatos) <= 2:
            self.ultimo = self.candidatos[0]
            return list(self.ultimo)
        # Busqueda restringida para que el banco de pruebas no tarde una eternidad
        pool = self.candidatos if len(self.candidatos) <= 400 else random.sample(self.candidatos, 400)
        mejor, mejor_peor = pool[0], float("inf")
        for g in pool:
            grupos = defaultdict(int)
            for c in self.candidatos:
                grupos[self._s(g, c)] += 1
            peor = max(grupos.values())
            if peor < mejor_peor:
                mejor_peor, mejor = peor, g
        self.ultimo = mejor
        return list(mejor)

    def discover(self, intento):
        return _pf(intento, self.secret)

    def feedBack(self, r):
        if self.ultimo is None or not isinstance(r, list) or len(r) != 2:
            return
        objetivo = (r[0], r[1])
        self.candidatos = [c for c in self.candidatos if self._s(self.ultimo, c) == objetivo]
        if not self.candidatos:
            self.candidatos = self.todos[:]


class RivalEntropico:
    """Estilo `CrucetaEntropica`: maximiza entropia de la particion."""
    nombre = "Entropico"

    def __init__(self):
        self.todos = list(itertools.permutations(range(10), 4))
        self.start()

    def start(self):
        self.secret = list(random.choice(self.todos))
        self.candidatos = self.todos[:]
        self.ultimo = None

    _s = staticmethod(RivalMinimax._s)

    def try_attempt(self):
        if self.ultimo is None:
            self.ultimo = (0, 1, 2, 3)
            return list(self.ultimo)
        if len(self.candidatos) <= 2:
            self.ultimo = self.candidatos[0]
            return list(self.ultimo)
        pool = self.candidatos if len(self.candidatos) <= 400 else random.sample(self.candidatos, 400)
        mejor, mejor_h = pool[0], -1.0
        total = len(self.candidatos)
        for g in pool:
            grupos = defaultdict(int)
            for c in self.candidatos:
                grupos[self._s(g, c)] += 1
            h = -sum((n / total) * math.log2(n / total) for n in grupos.values())
            if h > mejor_h:
                mejor_h, mejor = h, g
        self.ultimo = mejor
        return list(mejor)

    def discover(self, intento):
        return _pf(intento, self.secret)

    def feedBack(self, r):
        RivalMinimax.feedBack(self, r)


class RivalTramposo:
    """Estilo `AgentJuan`: NO fija secreto; responde siempre la clase mas grande
    para maximizar los turnos del contrario. Sirve para probar la deteccion
    adversarial y la recuperacion ante contradicciones."""
    nombre = "Tramposo"

    def __init__(self):
        self.todos = list(itertools.permutations(range(10), 4))
        self.start()

    def start(self):
        self.secret = list(random.choice(self.todos))   # declarado pero ignorado
        self.mios = self.todos[:]
        self.candidatos = self.todos[:]
        self.ultimo = None

    _s = staticmethod(RivalMinimax._s)

    def try_attempt(self):
        if self.ultimo is None:
            self.ultimo = (3, 5, 7, 9)
        elif self.candidatos:
            self.ultimo = self.candidatos[0]
        return list(self.ultimo)

    def discover(self, intento):
        grupos = defaultdict(list)
        for c in self.mios:
            grupos[self._s(tuple(intento), c)].append(c)
        elegido = max(grupos.items(), key=lambda kv: len(kv[1]))
        self.mios = elegido[1]
        return [elegido[0][0], elegido[0][1]]

    def feedBack(self, r):
        RivalMinimax.feedBack(self, r)


# =============================================================================
#  Torneo
# =============================================================================

def enfrentar(fabrica_rival, rondas):
    mio = AgentePicasFijas()
    rival = fabrica_rival()
    victorias = derrotas = empates = 0
    turnos_ganados = []
    todas_incidencias = []

    for i in range(rondas):
        # Se alterna la posicion para descartar cualquier sesgo del ambiente.
        if i % 2 == 0:
            res, turnos, inc = jugar_ronda(mio, rival)
            gane, perdi = res == 1, res == 2
        else:
            res, turnos, inc = jugar_ronda(rival, mio)
            gane, perdi = res == 2, res == 1
        todas_incidencias.extend(inc)
        if gane:
            victorias += 1
            turnos_ganados.append(turnos)
        elif perdi:
            derrotas += 1
        else:
            empates += 1

    return victorias, empates, derrotas, turnos_ganados, todas_incidencias


def main():
    rondas = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    random.seed(2024)

    rivales = [RivalAleatorio, RivalConsistente, RivalEntropico, RivalMinimax, RivalTramposo]

    print("=" * 74)
    print(" BANCO DE PRUEBAS - %d rondas por rival (ambiente oficial)" % rondas)
    print("=" * 74)
    print("%-14s %8s %8s %8s %10s   %s" % ("RIVAL", "GANO", "EMPATE", "PERDIO", "%PUNTOS", "INCIDENCIAS"))

    incidencias_totales = 0
    for fabrica in rivales:
        v, e, d, turnos, inc = enfrentar(fabrica, rondas)
        incidencias_totales += len(inc)
        puntos = 100.0 * (v + 0.5 * e) / max(1, v + e + d)
        print("%-14s %8d %8d %8d %9.1f%%   %d"
              % (fabrica.nombre, v, e, d, puntos, len(inc)))
        if inc:
            for linea in inc[:3]:
                print("      ! %s" % linea)

    print("-" * 74)
    print("Incidencias reglamentarias propias: %d (deben ser 0 para el agente)"
          % incidencias_totales)


if __name__ == "__main__":
    main()
