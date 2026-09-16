# -*- coding: utf-8 -*-
"""
===============================================================================
 AGENTE PARA LA COMPETENCIA DE PICAS Y FIJAS  (interfaz `compute`)
 Ambiente: Ambientes/Ambiente_Definitivo.ipynb  (ultima celda, juez central)
===============================================================================

Parte de `Picas_Y_Fijas_Agent.py` (que se conserva para el ambiente viejo y
para `generar_arbol.py`). Aqui cambian la forma de hablar con el ambiente
(`compute`) y la busqueda en linea, que ahora puntua las jugadas por turnos
esperados en vez de por candidatos restantes.

Reglas que cumple este archivo
------------------------------
 * La clase del agente expone UN SOLO metodo de interfaz: `compute(dato)`.
   Recibe un dato y devuelve un dato. No hay `start`, `try_attempt` ni
   `feedBack`: el ambiente crea una instancia nueva por ronda y el primer
   turno se reconoce porque la retroalimentacion llega como [-1, -1].
 * `compute` NO tiene ciclos (`while`) dentro: el ciclo de turnos y el de
   rondas los controla el ambiente. Cada llamada es un turno y nada mas.
 * Todo lo demas (limpieza del dato, filtrado de candidatos, eleccion de la
   jugada) vive FUERA de la clase, en funciones del modulo.

Contrato exacto con el ambiente
-------------------------------
    intento = agente.compute([picas, fijas])
 * Entrada : lista [picas, fijas] con la respuesta del juez al intento del
             turno anterior; [-1, -1] en el primer turno de la ronda.
 * Salida  : lista de 4 enteros distintos entre 0 y 9 (el juez acepta el 0
             inicial, igual que cuando genera el secreto con random.sample).

Como es el juego en este ambiente
---------------------------------
 * En cada ronda el JUEZ genera un unico secreto (random.sample(range(10), 4):
   uniforme sobre las 5040 combinaciones).
 * Los dos agentes intentan adivinar ESE MISMO secreto, cada uno por su lado.
   Nadie evalua al rival ni ve sus intentos: gana quien lo resuelve en menos
   turnos (mismo turno = empate). Por eso la unica forma de ganar mas rondas
   es resolver en menos turnos.

Estrategia
----------
 1. Apertura fija 0123. Todas las aperturas son equivalentes: renombrar los
    digitos convierte cualquiera en cualquier otra.
 2. Arbol de decision precalculado (ARBOL), si lo hay. Hoy ARBOL_TEXTO esta
    VACIO y el agente juega solo con la busqueda en linea del punto 4; la
    maquinaria del arbol se queda para poder pegar un bloque cuando se quiera.
 3. Con 1 o 2 candidatos, jugar un candidato: se gana ya o en el turno
    siguiente, y ninguna otra jugada mejora eso.
 4. Busqueda en linea sobre las 5040 jugadas: se elige la que MENOS TURNOS
    costara, sumando |clase| * T(|clase|) sobre las clases de respuesta, con
    T(m) = turnos que faltan en promedio con m candidatos (ver _tabla_coste).
    Antes se minimizaba el numero esperado de CANDIDATOS restantes (la suma de
    cuadrados); puntuar por turnos baja el promedio de 5.2688 a 5.2397 sobre
    los 5040 secretos.
 5. Candidatos como bitsets de 5040 bits: filtrar por una respuesta son unas
    pocas operaciones & | sobre enteros. Para PUNTUAR jugadas, en cambio, se
    comprime el universo a los candidatos vivos (ver _barrido): asi el barrido
    tarda la mitad.

Rendimiento medido (los 5040 secretos, exhaustivo, no una muestra)
------------------------------------------------------------------
    promedio 5.2397 turnos | peor caso 8 | todos resueltos
    distribucion {1:1, 2:7, 3:74, 4:611, 5:2457, 6:1789, 7:100, 8:1}
    66 ms por ronda | 12.6 ms por jugada de media, 49.5 ms la peor

El bloque ARBOL de abajo lo genera `generar_arbol.py`, que escribe sobre
`Picas_Y_Fijas_Agent.py`. Las marcas aqui son las mismas, asi que el bloque
generado alli se puede pegar tal cual entre las marcas de este archivo.
"""

from __future__ import annotations

import itertools
import math
import random

# =============================================================================
#  Reglas del juego
# =============================================================================

LARGO = 4          # digitos por numero
BASE = 10          # digitos disponibles (0..9)

# Dato que envia el ambiente en el primer turno de cada ronda.
SIN_RETROALIMENTACION = [-1, -1]

# Apertura y uso del arbol. Son parametros del modulo (y no atributos de clase)
# para que la clase del agente se quede con un solo metodo de interfaz.
# Todas las aperturas son equivalentes (renombrar digitos convierte una en
# otra); el arbol esta calculado para esta.
PRIMER_INTENTO = (0, 1, 2, 3)
USAR_ARBOL = True                       # False = jugar solo con busqueda en linea

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


# Coste en turnos de quedarse con m candidatos --------------------------------
#
# T(m) = turnos que faltan, en promedio, cuando quedan m candidatos. Se midio
# jugando 500 rondas y anotando cuantos turnos costo terminar desde cada
# tamano; el ajuste dio T(m) ~ A + B*ln(m), con T(1) = 1 y T(2) = 1.5 exactos.
#
# Puntuar una jugada por SUM |clase| * T(|clase|) es puntuarla por los turnos
# que costara, que es lo que se quiere ganar. La suma de cuadrados que se usaba
# antes puntuaba por CANDIDATOS restantes: trataba una clase de 40 como cuatro
# veces peor que una de 20, cuando en turnos solo es ~0.3 peor.
A_TURNOS = 1.1078
B_TURNOS = 0.6200


def _tabla_coste():
    """COSTE[m] = m * T(m).

    T se fuerza NO DECRECIENTE. Si T bajase al crecer m, partir una clase
    podria parecer peor que no partirla y el agente se quedaria dando vueltas
    sin resolver: con T(3) < T(2) llega a gastar 20 turnos con 3 candidatos
    sobre la mesa sin probar ninguno."""
    tabla = [0.0] * (N_CODIGOS + 1)
    previo = 0.0
    for m in range(1, N_CODIGOS + 1):
        t = 1.0 if m == 1 else (1.5 if m == 2 else A_TURNOS + B_TURNOS * math.log(m))
        if t < previo:
            t = previo
        previo = t
        tabla[m] = m * t
    return tabla


COSTE = _tabla_coste()


def _barrido(indices):
    """Para las 5040 jugadas: (coste en turnos, suma de cuadrados, peor caso,
    numero de clases) de las clases de respuesta sobre los candidatos `indices`.

    El candidato numero i es el bit i, asi que cada mascara ocupa len(indices)
    bits en vez de los 5040 del bitset general: ese ocupa 629 bytes SIEMPRE,
    queden 4 candidatos o 5000, y por eso el barrido no se abarataba al
    profundizar. Mismas cifras, aproximadamente el doble de rapido."""
    pos = [[0] * BASE for _ in range(LARGO)]
    tiene = [0] * BASE
    for i, indice in enumerate(indices):
        codigo = CODIGOS[indice]
        bit = 1 << i
        for p in range(LARGO):
            d = codigo[p]
            pos[p][d] |= bit
            tiene[d] |= bit

    lleno = (1 << len(indices)) - 1
    salida = []
    for codigo in CODIGOS:
        # celdas por fijas; la clase ganadora (4 fijas) se descarta sola al no
        # guardar f4, igual que hacia _particion topando f en LARGO - 1.
        f0, f1, f2, f3 = lleno, 0, 0, 0
        for p in range(LARGO):
            m = pos[p][codigo[p]]
            f3, f2, f1, f0 = ((f3 & ~m) | (f2 & m), (f2 & ~m) | (f1 & m),
                              (f1 & ~m) | (f0 & m), f0 & ~m)
        # celdas por digitos en comun
        c0, c1, c2, c3, c4 = lleno, 0, 0, 0, 0
        for p in range(LARGO):
            m = tiene[codigo[p]]
            c4, c3, c2, c1, c0 = (c4 | (c3 & m), (c3 & ~m) | (c2 & m),
                                  (c2 & ~m) | (c1 & m), (c1 & ~m) | (c0 & m), c0 & ~m)
        coste = 0.0
        suma_cuadrados = 0
        peor = 0
        clases = 0
        for comunes in (c0, c1, c2, c3, c4):
            if comunes:
                for fijas in (f0, f1, f2, f3):
                    grupo = fijas & comunes
                    if grupo:
                        cuenta = _popcount(grupo)
                        coste += COSTE[cuenta]
                        suma_cuadrados += cuenta * cuenta
                        clases += 1
                        if cuenta > peor:
                            peor = cuenta
        salida.append((coste, suma_cuadrados, peor, clases))
    return salida


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


def _normalizar_respuesta(valor):
    """Convierte la retroalimentacion a (picas, fijas) o None si no es una
    respuesta util (formato raro, [-1, -1] del primer turno, valores
    imposibles)."""
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        try:
            picas, fijas = int(valor[0]), int(valor[1])
        except (TypeError, ValueError):
            return None
        if 0 <= picas <= LARGO and 0 <= fijas <= LARGO and picas + fijas <= LARGO:
            return picas, fijas
    return None


def _es_inicio_de_ronda(valor):
    """True si el dato recibido es el [-1, -1] (o equivalente) con el que el
    ambiente marca el primer turno de una ronda."""
    if valor is None:
        return True
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        try:
            return int(valor[0]) < 0 or int(valor[1]) < 0
        except (TypeError, ValueError):
            return False
    return False


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
#  Estado del agente (todo esto vive FUERA de la clase)
# =============================================================================

def _reiniciar(estado):
    """Deja el estado como al principio de una ronda. El ambiente crea una
    instancia por ronda, pero ademas se reinicia cada vez que llega [-1, -1],
    asi que reutilizar la misma instancia tampoco rompe nada."""
    estado.mascara = MASCARA_TOTAL      # codigos que aun pueden ser el secreto
    estado.ruta = ""                    # letras de las respuestas; None = fuera del arbol
    estado.historia = []                # [(indice_jugada, (picas, fijas))]
    estado.ultima_jugada = None         # jugada que espera respuesta
    estado.jugadas_hechas = set()


def _procesar_respuesta(estado, retroalimentacion):
    """Incorpora el dato que llega del ambiente: reinicia si es el comienzo de
    la ronda, y si no filtra los candidatos con [picas, fijas]."""
    if _es_inicio_de_ronda(retroalimentacion):
        _reiniciar(estado)
        return

    indice = estado.ultima_jugada
    estado.ultima_jugada = None
    if indice is None:                  # respuesta sin intento previo: se ignora
        return

    respuesta = _normalizar_respuesta(retroalimentacion)
    if respuesta is None:               # dato ilegible: el arbol ya no sirve
        estado.ruta = None
        return

    picas, fijas = respuesta
    if fijas == LARGO:                  # acertado: la ronda termina aqui
        estado.mascara = 1 << indice
        return

    estado.historia.append((indice, respuesta))
    nueva = _refinar(estado.mascara, indice, picas, fijas)
    if estado.ruta is not None:
        estado.ruta += _letra(picas, fijas)
    if not nueva:                       # respuestas contradictorias
        nueva = _recuperar(estado)
        estado.ruta = None              # el arbol ya no describe la partida
    estado.mascara = nueva


def _recuperar(estado):
    """Respuestas contradictorias: se descartan las restricciones mas antiguas
    hasta volver a tener candidatos."""
    historia = estado.historia
    for descarte in range(1, len(historia) + 1):
        mascara = MASCARA_TOTAL
        for indice, (picas, fijas) in historia[descarte:]:
            mascara = _refinar(mascara, indice, picas, fijas)
            if not mascara:
                break
        if mascara:
            estado.historia = historia[descarte:]
            return mascara
    estado.historia = []
    return MASCARA_TOTAL


# =============================================================================
#  Nucleo de decision
# =============================================================================

def _elegir_jugada(estado):
    """Indice de la jugada del turno: arbol si la partida sigue en el, y si no
    busqueda en linea sobre las 5040 jugadas."""
    conjunto = estado.mascara
    if not conjunto:
        estado.mascara = conjunto = MASCARA_TOTAL
        estado.ruta = None
    hechas = estado.jugadas_hechas

    # (a) Apertura fija.
    if not estado.historia and estado.ruta == "":
        indice = INDICE[tuple(PRIMER_INTENTO)]
        if indice not in hechas:
            return indice

    # (b) Arbol precalculado.
    if USAR_ARBOL and estado.ruta is not None:
        indice = ARBOL.get(estado.ruta)
        if indice is not None and indice not in hechas:
            return indice

    candidatos = _indices(conjunto)

    # (c) 1 o 2 candidatos: jugar uno (gana ya o en el turno siguiente).
    if len(candidatos) <= 2:
        for i in candidatos:
            if i not in hechas:
                return i
        # Los candidatos ya se jugaron: solo pasa con respuestas incoherentes.
        # Repetir gastaria el turno sin aprender nada.
        return _primera_sin_jugar(hechas, candidatos[0])

    # (d) Busqueda en linea: la jugada que menos turnos costara. Se descartan
    #     las jugadas que no reparten nada (una sola clase y no son candidatas):
    #     no aportan informacion, y como `mejor_indice` empieza siendo un
    #     candidato, el agente nunca se queda sin resolver.
    es_candidato = set(candidatos)
    mejor_indice, mejor_clave = candidatos[0], None
    for indice, (coste, suma_cuadrados, peor, clases) in enumerate(_barrido(candidatos)):
        candidata = indice in es_candidato
        if indice in hechas or (clases < 2 and not candidata):
            continue
        clave = (coste, suma_cuadrados, peor, 0 if candidata else 1)
        if mejor_clave is None or clave < mejor_clave:
            mejor_clave, mejor_indice = clave, indice
    return mejor_indice


def _primera_sin_jugar(hechas, respaldo):
    """Primer codigo que no se haya jugado todavia. Solo se repite una jugada
    si de verdad no queda ninguno libre, cosa imposible en una partida normal:
    son 5040 codigos y las rondas duran unos pocos turnos."""
    for indice in range(N_CODIGOS):
        if indice not in hechas:
            return indice
    return respaldo


def _jugada_de_emergencia(estado):
    """Si algo inesperado falla, igual hay que devolver un numero valido.
    Se prefiere un candidato sin jugar; si no hay candidatos (mascara vacia
    por respuestas incoherentes), cualquier codigo sin jugar."""
    hechas = estado.jugadas_hechas
    for indice in _indices(estado.mascara):
        if indice not in hechas:
            return indice
    return _primera_sin_jugar(hechas, 0)


def _turno(estado, retroalimentacion):
    """Un turno completo: leer el dato, decidir y devolver el intento. Sin
    ciclos: el ambiente es quien repite esto turno tras turno."""
    try:
        _procesar_respuesta(estado, retroalimentacion)
        indice = _elegir_jugada(estado)
    except Exception:
        indice = _jugada_de_emergencia(estado)
    estado.ultima_jugada = indice
    estado.jugadas_hechas.add(indice)
    return [int(d) for d in CODIGOS[indice]]


# =============================================================================
#  Agente
# =============================================================================

# Nombre con el que aparece el agente en el desplegable del ambiente. El
# ambiente usa la clave del modulo, y "&" no es valido en un identificador de
# Python, asi que la clase se publica al final con globals()[NOMBRE_AGENTE].
NOMBRE_AGENTE = "AgenteDJS"


class _AgenteJJyS:
    """Agente para Picas y Fijas: busqueda que minimiza los turnos esperados
    (mas un arbol precalculado opcional, hoy vacio).

    Unico metodo de interfaz: `compute([picas, fijas]) -> [d, d, d, d]`."""

    def __init__(self):
        _reiniciar(self)

    def compute(self, retroalimentacion):
        """Recibe [picas, fijas] del turno anterior ([-1, -1] en el primero) y
        devuelve el intento de este turno: 4 enteros distintos entre 0 y 9."""
        return _turno(self, retroalimentacion)


_AgenteJJyS.__name__ = _AgenteJJyS.__qualname__ = NOMBRE_AGENTE
globals()[NOMBRE_AGENTE] = _AgenteJJyS

# Nota: no se exportan alias de la clase (por eso se borra _AgenteJJyS). El
# ambiente lista en su desplegable CADA clase del modulo, y los alias
# apareceria repetidos.
del _AgenteJJyS


# =============================================================================
#  Autoprueba: los 5040 secretos posibles, hablando solo por `compute`
# =============================================================================

if __name__ == "__main__":
    import sys
    import time
    from collections import Counter

    Agente = globals()[NOMBRE_AGENTE]
    muestra = CODIGOS
    if len(sys.argv) > 1 and sys.argv[1].isdigit():      # python3 archivo.py 200
        muestra = random.Random(0).sample(CODIGOS, int(sys.argv[1]))

    inicio = time.time()
    turnos = []
    decisiones = []                                      # ms de cada compute()
    for secreto in muestra:
        agente = Agente()
        retro = list(SIN_RETROALIMENTACION)              # primer turno: [-1, -1]
        for turno in range(1, 30):
            marca = time.perf_counter()
            intento = agente.compute(retro)
            decisiones.append(1000.0 * (time.perf_counter() - marca))
            assert isinstance(intento, list) and len(intento) == 4, intento
            assert len(set(intento)) == 4 and all(0 <= d <= 9 for d in intento), intento
            picas, fijas = _evaluar(intento, secreto)
            retro = [picas, fijas]
            if fijas == LARGO:
                turnos.append(turno)
                break
        else:                                            # nunca deberia pasar
            raise SystemExit("SIN RESOLVER: %s" % (secreto,))
    duracion = time.time() - inicio
    cuenta = Counter(turnos)
    print("Secretos probados : %d  (todos resueltos)" % len(turnos))
    print("Turnos promedio   : %.4f" % (sum(turnos) / len(turnos)))
    print("Peor caso         : %d" % max(turnos))
    print("Distribucion      : %s" % dict(sorted(cuenta.items())))
    print("Tiempo por ronda  : %.2f ms" % (1000.0 * duracion / len(turnos)))
    print("Tiempo por jugada : %.2f ms de media, %.2f ms la peor"
          % (sum(decisiones) / len(decisiones), max(decisiones)))
