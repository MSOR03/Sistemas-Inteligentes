# -*- coding: utf-8 -*-
"""
===============================================================================
 AGENTE PARA LA COMPETENCIA DE PICAS Y FIJAS
 Ambiente: Ambientes/Ambiente_Definitivo.ipynb  (juez central)
 Regla del curso: el agente no tiene ciclos indefinidos. Recibe un dato
 (feedBack), lo procesa (_refinar / _elegir_jugada) y devuelve un dato
 (try_attempt); el ciclo de turnos lo controla el ambiente.
===============================================================================

Como es el juego en este ambiente
---------------------------------
 * En cada ronda el JUEZ genera un unico secreto (random.sample(range(10), 4):
   uniforme sobre las 5040 combinaciones, el 0 inicial es valido).
 * Los dos agentes intentan adivinar ESE MISMO secreto, cada uno por su lado.
   Nadie evalua al rival ni ve sus intentos: gana quien lo resuelve en menos
   turnos (mismo turno = empate).
 * Por eso la unica forma de ganar mas rondas es resolver en menos turnos.

Contrato con el ambiente (interfazAgente)
-----------------------------------------
 * start()                 -> resetea el estado al comenzar la ronda.
 * try_attempt()           -> LISTA de 4 enteros unicos entre 0 y 9.
 * feedBack([picas,fijas]) -> incorpora la respuesta del juez.
 (receive_feedback(picas, fijas), `try` y discover() son alias/compatibilidad.)

Estrategia
----------
 1. Arbol de decision precalculado (ARBOL). Para cada historial de respuestas
    guarda la jugada que minimiza el numero TOTAL de turnos sobre todos los
    secretos todavia posibles. Se obtuvo fuera de linea con `generar_arbol.py`
    con busqueda en profundidad y poda; promedio exacto sobre los 5040
    secretos indicado en ARBOL_PROMEDIO. Jugar desde el arbol cuesta
    microsegundos por turno.
 2. Busqueda en linea de respaldo, solo si la partida se sale del arbol (por
    ejemplo si la retroalimentacion fuera inconsistente): elige, entre las
    5040 jugadas, la que minimiza el numero esperado de candidatos restantes.
 3. Candidatos como bitsets de 5040 bits: filtrar por una respuesta son unas
    pocas operaciones & | sobre enteros.
"""

from __future__ import annotations

import itertools
import os
import random
import sys
from abc import ABCMeta

# =============================================================================
#  Reglas del juego
# =============================================================================

LARGO = 4          # digitos por numero
BASE = 10          # digitos disponibles (0..9)

# El reglamento permite el 0 inicial ("4 digitos enteros unicos entre 0 y 9") y
# el juez lo usa. En este ambiente el secreto propio no se usa (lo genera el
# juez); se conserva `self.secret` valido por si un ambiente lo pidiera.
SECRETO_PERMITE_CERO_INICIAL = True

# =============================================================================
#  Universo de codigos y mascaras de bits precalculadas (una sola vez)
# =============================================================================

CODIGOS = list(itertools.permutations(range(BASE), LARGO))
N_CODIGOS = len(CODIGOS)                       # 5040
INDICE = {c: i for i, c in enumerate(CODIGOS)}
MASCARA_TOTAL = (1 << N_CODIGOS) - 1
_N_BYTES = (N_CODIGOS + 7) // 8


def _construir_mascaras():
    """POS[p][d]: bitset de codigos con el digito d en la posicion p.
    TIENE[d]:    bitset de codigos que contienen el digito d."""
    pos = [[bytearray(_N_BYTES) for _ in range(BASE)] for _ in range(LARGO)]
    tiene = [bytearray(_N_BYTES) for _ in range(BASE)]
    for i, codigo in enumerate(CODIGOS):
        byte, bit = i >> 3, 1 << (i & 7)
        for p in range(LARGO):
            d = codigo[p]
            pos[p][d][byte] |= bit
            tiene[d][byte] |= bit
    return (
        [[int.from_bytes(pos[p][d], "little") for d in range(BASE)] for p in range(LARGO)],
        [int.from_bytes(tiene[d], "little") for d in range(BASE)],
    )


POS, TIENE = _construir_mascaras()

try:                                    # Python >= 3.10
    (0).bit_count()
    _popcount = int.bit_count
except AttributeError:                  # respaldo para interpretes antiguos
    def _popcount(x):
        return bin(x).count("1")


def _celdas(conjunto, mascaras):
    """Reparte `conjunto` en 5 celdas disjuntas segun a cuantas de las 4
    `mascaras` pertenece cada codigo. celdas[k] = codigos que cumplen k de 4."""
    celdas = [conjunto, 0, 0, 0, 0]
    for nivel, m_i in enumerate(mascaras):
        for k in range(nivel, -1, -1):
            actual = celdas[k]
            if actual:
                dentro = actual & m_i
                if dentro:
                    celdas[k + 1] |= dentro
                    celdas[k] = actual ^ dentro
    return celdas


def _celdas_fijas(codigo, conjunto):
    """celdas[f] = codigos de `conjunto` con exactamente f fijas frente a `codigo`."""
    return _celdas(
        conjunto,
        (POS[0][codigo[0]], POS[1][codigo[1]], POS[2][codigo[2]], POS[3][codigo[3]]),
    )


def _celdas_comunes(codigo, conjunto):
    """celdas[m] = codigos de `conjunto` que comparten m digitos con `codigo`."""
    return _celdas(
        conjunto,
        (TIENE[codigo[0]], TIENE[codigo[1]], TIENE[codigo[2]], TIENE[codigo[3]]),
    )


def _particion(indice_jugada, conjunto):
    """Lista de ((picas, fijas), subconjunto) no vacios que produce la jugada
    sobre `conjunto`, sin la clase ganadora [0, 4]."""
    codigo = CODIGOS[indice_jugada]
    fijas = _celdas_fijas(codigo, conjunto)
    comunes = _celdas_comunes(codigo, conjunto)
    salida = []
    for m in range(LARGO + 1):
        grupo_m = comunes[m]
        if not grupo_m:
            continue
        for f in range(min(m, LARGO - 1) + 1):   # f == 4 es la clase ganadora
            interseccion = fijas[f] & grupo_m
            if interseccion:
                salida.append(((m - f, f), interseccion))
    return salida


def _estadisticas(indice_jugada, conjunto):
    """(suma de cuadrados, peor caso) de los tamanos de las clases de respuesta.
    suma_cuadrados / n = numero esperado de candidatos que sobreviven."""
    suma_cuadrados = 0
    peor = 0
    for _, grupo in _particion(indice_jugada, conjunto):
        cuenta = _popcount(grupo)
        suma_cuadrados += cuenta * cuenta
        if cuenta > peor:
            peor = cuenta
    return suma_cuadrados, peor


def _refinar(conjunto, indice_jugada, picas, fijas):
    """Subconjunto de `conjunto` compatible con la respuesta [picas, fijas]."""
    if not (0 <= fijas <= LARGO and 0 <= picas <= LARGO and picas + fijas <= LARGO):
        return conjunto                     # respuesta imposible: no se filtra
    codigo = CODIGOS[indice_jugada]
    return _celdas_fijas(codigo, conjunto)[fijas] & _celdas_comunes(codigo, conjunto)[picas + fijas]


def _evaluar(intento, secreto):
    """Picas y fijas de `intento` contra `secreto` (listas de enteros)."""
    fijas = sum(1 for a, b in zip(intento, secreto) if a == b)
    comunes = len(set(intento) & set(secreto))
    picas = max(0, min(comunes - fijas, LARGO - fijas))
    return picas, fijas


def _indices(mascara):
    """Lista de indices activos en un bitset, de menor a mayor. Se lee la
    representacion binaria al reves (bit 0 primero)."""
    return [i for i, bit in enumerate(bin(mascara)[:1:-1]) if bit == "1"]


def _normalizar_numero(valor):
    """Convierte list/tuple/str/int a lista de 4 enteros 0..9, o None."""
    if isinstance(valor, str):
        valor = valor.strip()
        if len(valor) != LARGO or not valor.isdigit():
            return None
        return [int(c) for c in valor]
    if isinstance(valor, int) and not isinstance(valor, bool):
        texto = str(valor).zfill(LARGO)
        return [int(c) for c in texto] if len(texto) == LARGO else None
    if isinstance(valor, (list, tuple)) and len(valor) == LARGO:
        try:
            salida = [int(x) for x in valor]
        except (TypeError, ValueError):
            return None
        return salida if all(0 <= d <= 9 for d in salida) else None
    return None


def _normalizar_respuesta(valor):
    """Convierte la retroalimentacion a (picas, fijas) o None si es imposible."""
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        try:
            picas, fijas = int(valor[0]), int(valor[1])
        except (TypeError, ValueError):
            return None
        if 0 <= picas <= LARGO and 0 <= fijas <= LARGO and picas + fijas <= LARGO:
            return picas, fijas
    return None


# =============================================================================
#  Arbol de decision precalculado
# =============================================================================
#
# Cada respuesta [picas, fijas] se escribe con UNA letra:
#     letra = LETRAS[5 * picas + fijas]     ([0,0]='a', [0,1]='b', [1,0]='f', [2,1]='l', ...)
# La RUTA de un momento de la partida es la cadena de letras de las respuestas
# recibidas hasta entonces ("" antes del primer intento).
#
# ARBOL[ruta] = jugada (4 digitos) que se hace en ese momento. Solo se guardan
# los momentos con 3 o mas candidatos: con 1 o 2 lo optimo es jugar un
# candidato, y eso lo hace la busqueda en linea.
#
# El bloque entre las marcas lo escribe `generar_arbol.py`; no editar a mano.

LETRAS = "abcdefghijklmnopqrstu"

# >>> ARBOL (generado por generar_arbol.py)
ARBOL_PROMEDIO = None
ARBOL_TEXTO = ""
# <<< ARBOL


def _letra(picas, fijas):
    return LETRAS[5 * picas + fijas]


def _cargar_arbol(texto):
    """'ruta:dddd ruta:dddd ...' -> {ruta: indice de la jugada}. Ignora
    cualquier entrada mal formada en lugar de fallar al importar."""
    arbol = {}
    for token in texto.split():
        ruta, _, jugada = token.partition(":")
        if len(jugada) == LARGO and jugada.isdigit():
            indice = INDICE.get(tuple(int(c) for c in jugada))
            if indice is not None and all(ch in LETRAS for ch in ruta):
                arbol[ruta] = indice
    return arbol


ARBOL = _cargar_arbol(ARBOL_TEXTO)


# =============================================================================
#  Agente
# =============================================================================

# Nombre con el que aparece el agente en el desplegable del ambiente. El
# ambiente usa la clave del modulo, y "&" no es valido en un identificador de
# Python, asi que la clase se publica al final con globals()[NOMBRE_AGENTE].
NOMBRE_AGENTE = "AgenteJJ&S"


class _AgenteJJyS:
    """Agente para Picas y Fijas: arbol optimizado + busqueda de respaldo."""

    # Apertura. Todas las aperturas son equivalentes (renombrar digitos
    # convierte una en otra); el arbol esta calculado para esta.
    PRIMER_INTENTO = (0, 1, 2, 3)

    # Poner en False para jugar solo con la busqueda en linea (comparaciones).
    USAR_ARBOL = True

    def __init__(self):
        self._rng = random.Random(int.from_bytes(os.urandom(16), "big"))
        self.secret = []
        self.start()
        _registrar_en_interfaz(type(self))

    # ------------------------------------------------------------------ #
    #  1) Inicio de ronda
    # ------------------------------------------------------------------ #
    def start(self):
        """Resetea todo lo aprendido. Tambien deja un secreto propio valido
        en `self.secret` (este ambiente no lo usa)."""
        iniciales = range(BASE) if SECRETO_PERMITE_CERO_INICIAL else range(1, BASE)
        primero = self._rng.choice(iniciales)
        resto = self._rng.sample([d for d in range(BASE) if d != primero], LARGO - 1)
        self.secret = [int(d) for d in [primero] + resto]

        self._mascara = MASCARA_TOTAL     # codigos que aun pueden ser el secreto
        self._ruta = ""                   # letras de las respuestas; None = fuera del arbol
        self._historia = []               # [(indice_jugada, (picas, fijas))]
        self._ultima_jugada = None        # jugada que espera respuesta
        self._jugadas_hechas = set()
        self.resuelto = False
        return self.secret

    # ------------------------------------------------------------------ #
    #  2) Intento del turno
    # ------------------------------------------------------------------ #
    def try_attempt(self):
        """Devuelve el intento del turno: lista de 4 enteros unicos 0..9."""
        try:
            indice = self._elegir_jugada()
        except Exception:
            libres = [i for i in _indices(self._mascara) if i not in self._jugadas_hechas]
            indice = libres[0] if libres else self._rng.randrange(N_CODIGOS)
        self._ultima_jugada = indice
        self._jugadas_hechas.add(indice)
        return [int(d) for d in CODIGOS[indice]]

    # ------------------------------------------------------------------ #
    #  3) Retroalimentacion del juez
    # ------------------------------------------------------------------ #
    def feedBack(self, retroalimentacionLista):
        """Filtra los candidatos con la respuesta [picas, fijas] del juez."""
        try:
            respuesta = _normalizar_respuesta(retroalimentacionLista)
            indice = self._ultima_jugada
            self._ultima_jugada = None
            if respuesta is None or indice is None:
                return
            picas, fijas = respuesta
            if fijas == LARGO:
                self.resuelto = True
                self._mascara = 1 << indice
                return

            self._historia.append((indice, respuesta))
            nueva = _refinar(self._mascara, indice, picas, fijas)
            if self._ruta is not None:
                self._ruta += _letra(picas, fijas)
            if not nueva:                  # respuestas contradictorias
                nueva = self._recuperar()
                self._ruta = None          # el arbol ya no describe la partida
            self._mascara = nueva
        except Exception:
            self._ruta = None

    def receive_feedback(self, picas, fijas):
        """Nombre que usa AdaptadorUniversal del ambiente nuevo."""
        return self.feedBack([picas, fijas])

    # ------------------------------------------------------------------ #
    #  Compatibilidad con el ambiente anterior (agentes que se evaluan)
    # ------------------------------------------------------------------ #
    def discover(self, numeroLista):
        """[picas, fijas] honestas del intento del rival contra `self.secret`."""
        try:
            intento = _normalizar_numero(numeroLista)
            if intento is None:
                return [0, 0]
            picas, fijas = _evaluar(intento, self.secret)
            return [int(picas), int(fijas)]
        except Exception:
            return [0, 0]

    # ------------------------------------------------------------------ #
    #  Nucleo de decision
    # ------------------------------------------------------------------ #
    def _elegir_jugada(self):
        conjunto = self._mascara
        if not conjunto:
            self._mascara = conjunto = MASCARA_TOTAL
            self._ruta = None
        hechas = self._jugadas_hechas

        # (a) Apertura fija.
        if not self._historia and self._ruta == "":
            indice = INDICE[tuple(self.PRIMER_INTENTO)]
            if indice not in hechas:
                return indice

        # (b) Arbol precalculado.
        if self.USAR_ARBOL and self._ruta is not None:
            indice = ARBOL.get(self._ruta)
            if indice is not None and indice not in hechas:
                return indice

        candidatos = _indices(conjunto)

        # (c) 1 o 2 candidatos: jugar uno (gana ya o en el turno siguiente).
        if len(candidatos) <= 2:
            for i in candidatos:
                if i not in hechas:
                    return i
            return candidatos[0]

        # (d) Busqueda en linea: minimiza el numero esperado de candidatos
        #     restantes; desempata por peor caso y por jugada candidata.
        mejor_indice, mejor_clave = candidatos[0], None
        for indice in range(N_CODIGOS):
            if indice in hechas:
                continue
            suma_cuadrados, peor = _estadisticas(indice, conjunto)
            clave = (suma_cuadrados, peor, 0 if (conjunto >> indice) & 1 else 1)
            if mejor_clave is None or clave < mejor_clave:
                mejor_clave, mejor_indice = clave, indice
        return mejor_indice

    def _recuperar(self):
        """Respuestas contradictorias: se descartan las restricciones mas
        antiguas hasta volver a tener candidatos."""
        historia = self._historia
        for descarte in range(1, len(historia) + 1):
            mascara = MASCARA_TOTAL
            for indice, (picas, fijas) in historia[descarte:]:
                mascara = _refinar(mascara, indice, picas, fijas)
                if not mascara:
                    break
            if mascara:
                self._historia = historia[descarte:]
                return mascara
        self._historia = []
        return MASCARA_TOTAL

    def __repr__(self):
        return "<AgenteJJ&S candidatos=%d ruta=%r>" % (_popcount(self._mascara), self._ruta)


def _alias_try(self):
    """Metodo literal `try` que menciona el reglamento. No puede declararse con
    `def try(...)` porque es palabra reservada de Python."""
    return self.try_attempt()


setattr(_AgenteJJyS, "try", _alias_try)


# =============================================================================
#  Herencia de la interfaz del ambiente
# =============================================================================

def _buscar_interfaz():
    """`interfazAgente` tal como la definio el notebook (sus celdas viven en
    __main__) o un modulo aparte; None si no existe."""
    for nombre_modulo in ("__main__", "builtins", "Ambiente", "interfaz", "interfazAgente"):
        base = getattr(sys.modules.get(nombre_modulo), "interfazAgente", None)
        if isinstance(base, ABCMeta):
            return base
    return None


def _registrar_en_interfaz(clase):
    """Respaldo si la interfaz se define DESPUES de importar este archivo:
    registra la clase como subclase virtual (issubclass/isinstance dan True)."""
    base = _buscar_interfaz()
    if base is not None and not issubclass(clase, base):
        try:
            base.register(clase)
        except Exception:
            pass


def _heredar_de_interfaz(clase):
    """Si `interfazAgente` ya existe al importar, la clase publica HEREDA de
    ella (aparece en __mro__). Si la interfaz exigiera un metodo que el agente
    no tiene, se usa la clase normal registrada como subclase virtual, para no
    provocar un TypeError al instanciar."""
    base = _buscar_interfaz()
    if base is None or base in clase.__mro__:
        return clase
    try:
        nueva = type(base)(clase.__name__, (clase, base), {
            "__module__": clase.__module__,
            "__qualname__": clase.__qualname__,
            "__doc__": clase.__doc__,
        })
        if not getattr(nueva, "__abstractmethods__", None):
            return nueva
    except Exception:
        pass
    _registrar_en_interfaz(clase)
    return clase


_AgenteJJyS.__name__ = _AgenteJJyS.__qualname__ = NOMBRE_AGENTE
globals()[NOMBRE_AGENTE] = _heredar_de_interfaz(_AgenteJJyS)

# Nota: no se exportan alias de la clase (por eso se borra _AgenteJJyS). El
# ambiente nuevo lista en su desplegable CADA clase del modulo, y los alias
# aparecerian repetidos.
del _AgenteJJyS


# =============================================================================
#  Autoprueba: los 5040 secretos posibles
# =============================================================================

if __name__ == "__main__":
    import time
    from collections import Counter

    Agente = globals()[NOMBRE_AGENTE]
    inicio = time.time()
    turnos = []
    for secreto in CODIGOS:
        agente = Agente()
        agente.start()
        for turno in range(1, 30):
            intento = agente.try_attempt()
            assert isinstance(intento, list) and len(set(intento)) == 4, intento
            picas, fijas = _evaluar(intento, secreto)
            agente.feedBack([picas, fijas])
            if fijas == 4:
                turnos.append(turno)
                break
    duracion = time.time() - inicio
    cuenta = Counter(turnos)
    print("Secretos probados : %d (todos)" % len(turnos))
    print("Turnos promedio   : %.4f" % (sum(turnos) / len(turnos)))
    print("Peor caso         : %d" % max(turnos))
    print("Distribucion      : %s" % dict(sorted(cuenta.items())))
    print("Tiempo por ronda  : %.2f ms" % (1000.0 * duracion / len(turnos)))
