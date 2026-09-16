# -*- coding: utf-8 -*-
"""
RIVAL DE PRUEBA - Juan  (interfaz `compute`)

Abre con 3579, tiene tabulado el segundo intento para cada respuesta posible y
a partir del tercero hace minimax DENTRO de los candidatos (nunca juega un
codigo descartado). Misma logica que AgentJuan de `examples/`.

Abrir con 3579 es equivalente a abrir con 0123: renombrar digitos convierte una
apertura en la otra. Lo que lo distingue es la tabla del segundo turno.

NO es el agente que se entrega. Esta aqui solo para montar torneos locales.
"""

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


class RivalJuan(_Base):
    """Apertura 3579 + tabla de segundo intento + minimax entre candidatos."""

    PRIMERO = (3, 5, 7, 9)

    # (fijas, picas) -> segundo intento, igual que la TABLA_G2 del original
    TABLA_G2 = {
        (0, 0): "0124", (0, 1): "0123", (0, 2): "0135", (0, 3): "0795", (0, 4): "5397",
        (1, 0): "0129", (1, 1): "0139", (1, 2): "0359", (1, 3): "3795",
        (2, 0): "0179", (2, 1): "0379", (2, 2): "3597", (3, 0): "0579", (4, 0): "3579",
    }

    def _decidir(self):
        if not self.historial:
            return self.PRIMERO
        if len(self.historial) == 1:
            picas, fij = self.historial[0]
            texto = self.TABLA_G2.get((fij, picas))
            if texto:
                return tuple(int(c) for c in texto)
            return self._primer_candidato()
        conjunto = self.conjunto
        vivos = candidatos(conjunto)
        if not vivos:
            return CODIGOS[0]
        mejor, mejor_peor = vivos[0], float("inf")
        for codigo in vivos:                      # minimax solo entre candidatos
            peor = max(conteos(codigo, conjunto))
            if peor < mejor_peor:
                mejor, mejor_peor = codigo, peor
        return mejor


del _Base
