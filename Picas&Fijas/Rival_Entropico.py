# -*- coding: utf-8 -*-
"""
RIVAL DE PRUEBA - Maxima entropia  (interfaz `compute`)

Elige la jugada cuyo reparto de respuestas tiene mas entropia, o sea la que
mas informacion espera sacar del turno. Mientras quedan mas de 100 candidatos
mira las 5040 jugadas; por debajo se limita a los candidatos.

Misma logica que CrucetaEntropica de `examples/`.

NO es el agente que se entrega. Esta aqui solo para montar torneos locales.
"""

import math

import itertools

# --------------------------------------------------------------------------- #
#  Nucleo comun (identico en todos los rivales; cada archivo es autonomo para
#  poder copiarlo suelto a la carpeta del ambiente)
# --------------------------------------------------------------------------- #

CODIGOS = list(itertools.permutations(range(10), 4))
N = len(CODIGOS)                                  # 5040
IDX = {c: i for i, c in enumerate(CODIGOS)}
TOTAL = (1 << N) - 1


def _mascaras():
    pos = [[0] * 10 for _ in range(4)]
    tiene = [0] * 10
    for i, codigo in enumerate(CODIGOS):
        bit = 1 << i
        for p, d in enumerate(codigo):
            pos[p][d] |= bit
            tiene[d] |= bit
    return pos, tiene


POS, TIENE = _mascaras()


def _celdas(conjunto, mascaras):
    """celdas[k] = codigos de `conjunto` que cumplen exactamente k de las 4."""
    celdas = [conjunto, 0, 0, 0, 0]
    for nivel, m in enumerate(mascaras):
        for k in range(nivel, -1, -1):
            dentro = celdas[k] & m
            if dentro:
                celdas[k + 1] |= dentro
                celdas[k] ^= dentro
    return celdas


def _celdas_de(codigo, conjunto):
    fijas = _celdas(conjunto, (POS[0][codigo[0]], POS[1][codigo[1]],
                               POS[2][codigo[2]], POS[3][codigo[3]]))
    comunes = _celdas(conjunto, (TIENE[codigo[0]], TIENE[codigo[1]],
                                 TIENE[codigo[2]], TIENE[codigo[3]]))
    return fijas, comunes


def conteos(codigo, conjunto):
    """Tamanos de los grupos de respuesta que produce `codigo` sobre `conjunto`."""
    fijas, comunes = _celdas_de(codigo, conjunto)
    salida = []
    for com in range(5):
        if comunes[com]:
            for fij in range(com + 1):
                x = fijas[fij] & comunes[com]
                if x:
                    salida.append(x.bit_count())
    return salida


def refinar(conjunto, codigo, picas, fij):
    """Codigos de `conjunto` compatibles con la respuesta [picas, fij]."""
    if not (0 <= picas <= 4 and 0 <= fij <= 4 and picas + fij <= 4):
        return conjunto
    fijas, comunes = _celdas_de(codigo, conjunto)
    return fijas[fij] & comunes[picas + fij]


def candidatos(conjunto):
    """Codigos todavia posibles, en orden lexicografico."""
    salida = []
    c = conjunto
    while c:
        bajo = c & -c
        salida.append(CODIGOS[bajo.bit_length() - 1])
        c ^= bajo
    return salida


def _es_inicio(retroalimentacion):
    """El ambiente marca el primer turno de la ronda con [-1, -1]."""
    if retroalimentacion is None:
        return True
    try:
        return int(retroalimentacion[0]) < 0 or int(retroalimentacion[1]) < 0
    except (TypeError, ValueError, IndexError):
        return True


class _Base:
    """Interfaz `compute` + filtrado de candidatos. Cada rival solo cambia
    `_decidir`. Se borra el nombre al final del modulo para que el ambiente no
    la liste como un agente mas en el desplegable."""

    PRIMERO = (0, 1, 2, 3)

    def __init__(self):
        self._reiniciar()

    def _reiniciar(self):
        self.conjunto = TOTAL
        self.historial = ()
        self.ultimo = None

    def compute(self, retroalimentacion):
        try:
            if _es_inicio(retroalimentacion):
                self._reiniciar()
            elif self.ultimo is not None:
                picas = int(retroalimentacion[0])
                fij = int(retroalimentacion[1])
                self.historial += ((picas, fij),)
                nuevo = refinar(self.conjunto, self.ultimo, picas, fij)
                self.conjunto = nuevo if nuevo else TOTAL
            jugada = self._decidir()
            if jugada is None:
                raise ValueError("sin jugada")
        except Exception:
            vivos = candidatos(getattr(self, "conjunto", TOTAL))
            jugada = vivos[0] if vivos else CODIGOS[0]
        self.ultimo = tuple(jugada)
        return [int(d) for d in jugada]

    def _decidir(self):
        raise NotImplementedError

    def _primer_candidato(self):
        vivos = candidatos(self.conjunto)
        return vivos[0] if vivos else CODIGOS[0]


class RivalEntropico(_Base):
    """Primer intento 0123 y despues maxima entropia."""

    LIMITE_BUSQUEDA_AMPLIA = 100

    def _decidir(self):
        if not self.historial:
            return self.PRIMERO
        conjunto = self.conjunto
        vivos = candidatos(conjunto)
        total = len(vivos)
        if total <= 1:
            return vivos[0] if vivos else CODIGOS[0]
        pool = vivos if total <= self.LIMITE_BUSQUEDA_AMPLIA else CODIGOS
        mejor, mejor_h = vivos[0], -1.0
        for codigo in pool:
            h = 0.0
            for n in conteos(codigo, conjunto):
                p = n / total
                h -= p * math.log2(p)
            if h > mejor_h:
                mejor_h, mejor = h, codigo
        return mejor


del _Base
