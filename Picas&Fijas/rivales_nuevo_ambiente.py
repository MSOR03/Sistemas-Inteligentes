# -*- coding: utf-8 -*-
"""
Rivales de prueba para el NUEVO ambiente (Ambientes/Ambiente_Definitivo.ipynb).

Son los agentes de `examples/Ambiente.ipynb` adaptados a la interfaz nueva
(start / try_attempt / feedBack, sin `discover` porque ahora el juez central
evalua). La LOGICA de decision de cada uno se conserva:

  * AgenteLexicografico - la logica de AgenteEstrategico del notebook y de
                       Cruceta/AgentA: primer candidato en orden.
  * AgenteJuan       - primer intento 3579, tabla de segundo intento y minimax
                       dentro de los candidatos (AgentJuan).
  * AgenteCrucetero  - primer intento 0123 y minimax sobre las 5040 jugadas,
                       desempatando por candidato (Crucetero).
  * AgenteEntropico  - primer intento 0123 y maxima entropia; busca en las 5040
                       jugadas si hay mas de 100 candidatos (CrucetaEntropica).

Los originales tardan varios segundos por turno en Python puro. Para poder
jugar cientos de rondas, las CUENTAS de la particion se hacen con mascaras de
bits y las decisiones se memorizan por historial; el recorrido y los
desempates son los mismos que en el original, asi que eligen la misma jugada.

Si copias este archivo junto al agente en la carpeta del ambiente, sus clases
aparecen en los desplegables del torneo.
"""

import itertools
import math

_CODIGOS = list(itertools.permutations(range(10), 4))
_N = len(_CODIGOS)
_IDX = {c: i for i, c in enumerate(_CODIGOS)}


def _mascaras():
    pos = [[0] * 10 for _ in range(4)]
    tiene = [0] * 10
    for i, c in enumerate(_CODIGOS):
        b = 1 << i
        for p, d in enumerate(c):
            pos[p][d] |= b
            tiene[d] |= b
    return pos, tiene


_POS, _TIENE = _mascaras()


def _celdas(conjunto, mascaras):
    celdas = [conjunto, 0, 0, 0, 0]
    for nivel, m in enumerate(mascaras):
        for k in range(nivel, -1, -1):
            dentro = celdas[k] & m
            if dentro:
                celdas[k + 1] |= dentro
                celdas[k] ^= dentro
    return celdas


def _particion(codigo, conjunto):
    """{(picas, fijas): bitset} de `conjunto` frente a la jugada `codigo`."""
    f = _celdas(conjunto, [_POS[p][codigo[p]] for p in range(4)])
    m = _celdas(conjunto, [_TIENE[d] for d in codigo])
    salida = {}
    for comunes in range(5):
        if not m[comunes]:
            continue
        for fijas in range(comunes + 1):
            x = f[fijas] & m[comunes]
            if x:
                salida[(comunes - fijas, fijas)] = x
    return salida


def _conteos(codigo, conjunto):
    return [x.bit_count() for x in _particion(codigo, conjunto).values()]


class _BaseMemo:
    """Filtrado por bitset + memoria de decisiones por historial."""
    _memo = None
    PRIMERO = (0, 1, 2, 3)

    def start(self):
        self.conjunto = (1 << _N) - 1
        self.historial = ()
        self.ultimo = None

    def try_attempt(self):
        memo = type(self).__dict__.get("_memo")     # una memoria por clase
        if memo is None:
            memo = {}
            setattr(type(self), "_memo", memo)
        jugada = memo.get(self.historial)
        if jugada is None:
            jugada = self._decidir()
            memo[self.historial] = jugada
        self.ultimo = jugada
        return list(jugada)

    def feedBack(self, r):
        if self.ultimo is None:
            return
        clave = (int(r[0]), int(r[1]))
        self.historial += (clave,)
        nuevo = _particion(self.ultimo, self.conjunto).get(clave, 0)
        self.conjunto = nuevo if nuevo else (1 << _N) - 1

    def _decidir(self):
        """Por defecto: primer candidato en orden (estilo Cruceta/AgentA)."""
        return self.PRIMERO if not self.historial else self._candidatos()[0]

    def _candidatos(self):
        c, salida = self.conjunto, []
        while c:
            bajo = c & -c
            salida.append(_CODIGOS[bajo.bit_length() - 1])
            c ^= bajo
        return salida


class AgenteLexicografico(_BaseMemo):
    """Misma logica que AgenteEstrategico del notebook (y que Cruceta/AgentA de
    examples/): primer intento 0123 y siempre el primer candidato en orden."""


class AgenteJuan(_BaseMemo):
    PRIMERO = (3, 5, 7, 9)
    # clave (fijas, picas) -> segundo intento, igual que TABLA_G2 del original
    TABLA_G2 = {
        (0, 0): "0124", (0, 1): "0123", (0, 2): "0135", (0, 3): "0795", (0, 4): "5397",
        (1, 0): "0129", (1, 1): "0139", (1, 2): "0359", (1, 3): "3795",
        (2, 0): "0179", (2, 1): "0379", (2, 2): "3597", (3, 0): "0579", (4, 0): "3579",
    }

    def _decidir(self):
        if not self.historial:
            return self.PRIMERO
        if len(self.historial) == 1:
            picas, fijas = self.historial[0]
            texto = self.TABLA_G2.get((fijas, picas))
            if texto:
                return tuple(int(c) for c in texto)
            return self._candidatos()[0]
        candidatos = self._candidatos()
        mejor, mejor_peor = None, float("inf")
        for g in candidatos:                       # minimax dentro de candidatos
            peor = max(_conteos(g, self.conjunto))
            if peor < mejor_peor:
                mejor, mejor_peor = g, peor
        return mejor


class AgenteCrucetero(_BaseMemo):
    def _decidir(self):
        if not self.historial:
            return self.PRIMERO
        mejor, mejor_peor = None, float("inf")
        for g in _CODIGOS:                         # minimax sobre las 5040
            peor = max(_conteos(g, self.conjunto))
            if peor < mejor_peor:
                mejor_peor, mejor = peor, g
            if peor == mejor_peor and (self.conjunto >> _IDX[g]) & 1:
                mejor = g
                break
        return mejor


class AgenteEntropico(_BaseMemo):
    def _decidir(self):
        if not self.historial:
            return self.PRIMERO
        candidatos = self._candidatos()
        total = len(candidatos)
        pool = candidatos if total <= 100 else _CODIGOS
        mejor, mejor_h = None, -1
        for g in pool:
            h = 0.0
            for n in _conteos(g, self.conjunto):
                p = n / total
                h -= p * math.log2(p)
            if h > mejor_h:
                mejor_h, mejor = h, g
        return mejor
