# -*- coding: utf-8 -*-
"""
===============================================================================
 AGENTE PARA LA COMPETENCIA DE PICAS Y FIJAS
===============================================================================

Cumplimiento estricto del reglamento del ambiente
-------------------------------------------------
 * start()                -> genera un secreto de 4 digitos ENTEROS UNICOS 0..9
                             y lo deja en `self.secret` como lista de enteros,
                             tal como lo exige `es_intento_valido`.
 * try / try_attempt()    -> devuelve una LISTA de 4 enteros unicos entre 0 y 9.
 * discover(numeroLista)  -> devuelve una LISTA [picas, fijas] de 2 enteros,
                             con picas + fijas <= 4, evaluada HONESTAMENTE
                             contra el secreto generado en start().
 * feedBack(retroLista)   -> incorpora [picas, fijas] del propio intento.

 No se miente en `discover`: la respuesta siempre es la evaluacion real del
 secreto declarado. Toda la fuerza del agente esta en el lado de la busqueda.

Motor de busqueda
-----------------
 El espacio de juego son las 5040 permutaciones de 4 digitos distintos.
 Cada turno el agente:
   1. Filtra el conjunto de candidatos consistentes con TODA la historia.
   2. Evalua las 5040 jugadas posibles (no solo las candidatas) y elige la que
      minimiza el numero esperado de candidatos restantes, desempatando por
      peor caso y por preferir una jugada que ademas pueda ganar de inmediato.
   3. Mientras haya candidatos que no empiecen en 0 busca solo entre ellos
      (muchos rivales generan "numeros de 4 cifras" sin cero inicial); si la
      evidencia los descarta, vuelve a las 5040 combinaciones.

 Para que esa busqueda exhaustiva sea viable en Python puro, los conjuntos de
 candidatos se representan como enteros-bitset de 5040 bits y las particiones
 se calculan con operaciones de bits sobre mascaras precalculadas por
 (posicion, digito) y por (digito presente). Un turno completo cuesta
 milisegundos, sin dependencias externas (no requiere numpy).

Defensas
--------
 * Modo adversarial: si el rival responde de forma sistematicamente "maligna"
   (siempre la clase de respuesta mas grande, tipico de un agente que no fija
   secreto y responde para maximizar la incertidumbre), el criterio cambia a
   minimax puro, que es la respuesta optima contra ese comportamiento.
 * Recuperacion ante contradicciones: si el rival responde de forma
   inconsistente y el conjunto de candidatos queda vacio, se descartan las
   restricciones mas antiguas hasta recuperar un conjunto viable.
 * Ningun metodo publico puede lanzar excepcion: todos tienen respaldo seguro.
 * El secreto se genera con un RNG propio sembrado desde os.urandom, de modo
   que no es predecible aunque otro agente manipule `random.seed()`.
"""

from __future__ import annotations

import itertools
import os
import random
import sys
from abc import ABCMeta

__all__ = [
    "AgentePicasFijas",
    "Agente",
    "AgenteClase1",
    "AgenteClase2",
    "TuAgente",
]

# =============================================================================
#  Reglas del juego
# =============================================================================

LARGO = 4          # digitos por numero
BASE = 10          # digitos disponibles (0..9)

# El reglamento PERMITE el 0 inicial: exige "4 digitos enteros unicos entre 0 y
# 9" y `es_intento_valido` acepta [0, 1, 2, 3]. Ambos valores son legales; es
# una decision estrategica, no de cumplimiento:
#   * True : 5040 secretos posibles. rival_real.py (busca en range(1023, 9876))
#            revienta con IndexError en ~7% de las rondas; en Ambiente.ipynb la
#            excepcion no se captura y detiene el torneo sin ganador.
#   * False: 4536 secretos. Ningun rival revienta. Contra rivales normales la
#            diferencia medida esta dentro del ruido (400 rondas por rival).
# El agente siempre ADIVINA sobre las 5040 combinaciones, sea cual sea el valor.
SECRETO_PERMITE_CERO_INICIAL = False

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
SIN_CERO_INICIAL = MASCARA_TOTAL & ~POS[0][0]   # 4536 codigos que no empiezan en 0

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
    return _celdas(
        conjunto,
        (POS[0][codigo[0]], POS[1][codigo[1]], POS[2][codigo[2]], POS[3][codigo[3]]),
    )


def _celdas_comunes(codigo, conjunto):
    return _celdas(
        conjunto,
        (TIENE[codigo[0]], TIENE[codigo[1]], TIENE[codigo[2]], TIENE[codigo[3]]),
    )


def _estadisticas(indice_jugada, conjunto):
    """Para la jugada dada devuelve (suma_cuadrados, suma_cubos, peor_caso)
    sobre las clases de respuesta, excluyendo la clase ganadora [0,4] porque
    ahi el juego termina y no quedan candidatos por resolver.

      * suma_cuadrados / n  = numero esperado de candidatos que sobreviven.
      * suma_cubos          = igual pero castigando mas las clases grandes,
                              lo que recorta la cola de partidas largas.
      * peor_caso           = criterio minimax (optimo contra un rival que
                              responde de forma adversarial)."""
    codigo = CODIGOS[indice_jugada]
    fijas = _celdas_fijas(codigo, conjunto)
    comunes = _celdas_comunes(codigo, conjunto)
    suma_cuadrados = 0
    suma_cubos = 0
    peor = 0
    for m in range(5):
        grupo_m = comunes[m]
        if not grupo_m:
            continue
        for f in range(min(m, 3) + 1):      # f == 4 es la clase ganadora
            grupo_f = fijas[f]
            if not grupo_f:
                continue
            interseccion = grupo_f & grupo_m
            if interseccion:
                cuenta = _popcount(interseccion)
                cuadrado = cuenta * cuenta
                suma_cuadrados += cuadrado
                suma_cubos += cuadrado * cuenta
                if cuenta > peor:
                    peor = cuenta
    return suma_cuadrados, suma_cubos, peor


def _refinar(conjunto, indice_jugada, picas, fijas):
    """Subconjunto de `conjunto` compatible con la respuesta [picas, fijas]."""
    if not (0 <= fijas <= LARGO and 0 <= picas <= LARGO and picas + fijas <= LARGO):
        return conjunto                     # respuesta imposible: no se filtra
    codigo = CODIGOS[indice_jugada]
    return _celdas_fijas(codigo, conjunto)[fijas] & _celdas_comunes(codigo, conjunto)[picas + fijas]


def _evaluar(intento, secreto):
    """Picas y fijas honestas de `intento` contra `secreto` (listas de enteros)."""
    fijas = 0
    for a, b in zip(intento, secreto):
        if a == b:
            fijas += 1
    conjunto_secreto = set(secreto)
    comunes = sum(1 for d in set(intento) if d in conjunto_secreto)
    picas = comunes - fijas
    if picas < 0:
        picas = 0
    if picas + fijas > LARGO:
        picas = LARGO - fijas
    return picas, fijas


def _normalizar_numero(valor):
    """Convierte list/tuple/str/int a lista de 4 enteros, o None si no se puede."""
    if valor is None:
        return None
    if isinstance(valor, str):
        texto = valor.strip()
        if len(texto) != LARGO or not texto.isdigit():
            return None
        return [int(c) for c in texto]
    if isinstance(valor, int) and not isinstance(valor, bool):
        texto = str(valor).zfill(LARGO)
        if len(texto) != LARGO:
            return None
        return [int(c) for c in texto]
    if isinstance(valor, (list, tuple)):
        if len(valor) != LARGO:
            return None
        salida = []
        for x in valor:
            if isinstance(x, bool):
                return None
            if isinstance(x, int):
                salida.append(int(x))
            elif isinstance(x, str) and x.strip().isdigit() and len(x.strip()) == 1:
                salida.append(int(x))
            else:
                try:
                    entero = int(x)
                except (TypeError, ValueError):
                    return None
                salida.append(entero)
        if any(d < 0 or d > 9 for d in salida):
            return None
        return salida
    return None


def _normalizar_respuesta(valor):
    """Convierte la retroalimentacion a (picas, fijas) o None."""
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        try:
            picas, fijas = int(valor[0]), int(valor[1])
        except (TypeError, ValueError):
            return None
        if 0 <= picas <= LARGO and 0 <= fijas <= LARGO and picas + fijas <= LARGO:
            return picas, fijas
    return None


# =============================================================================
#  Agente
# =============================================================================

class AgentePicasFijas:
    """Agente competitivo y reglamentario para Picas y Fijas."""

    # Turnos consecutivos cayendo en la clase mas grande antes de asumir que el
    # rival responde de forma adversarial en lugar de honesta.
    UMBRAL_ADVERSARIAL = 3

    # Criterio de seleccion de jugada: "cuadrados" (minimiza el numero esperado
    # de candidatos restantes), "cubos" (idem, castigando mas las clases
    # grandes) o "minimax" (minimiza el peor caso).
    #
    # Se eligio "cubos" midiendo 400 partidas por criterio (ver tune.py). Lo que
    # decide el torneo no es el promedio de turnos sino ganar la carrera, y ahi
    # llegar en 5 en vez de 6 vale mucho mas que llegar en 3 en vez de 4: el
    # rival casi nunca resuelve en 3. "cubos" recorta justo esa zona y resulta
    # mejor que "cuadrados" en las tres metricas a la vez (promedio 5.260 contra
    # 5.298, P(<=5 turnos) 0.617 contra 0.593, y marcador de carrera +0.031).
    CRITERIO = "cubos"

    # Modo carrera: si el rival ya casi resuelve mi secreto, dejo de recolectar
    # informacion y juego solo candidatos, que son los unicos que pueden ganar
    # en el turno actual. Un empate vale mas que una derrota.
    #
    # Umbral deliberadamente bajo: solo se activa en el final de partida, donde
    # explorar es claramente peor que disparar. En espejo contra si mismo la
    # ganancia medida queda por debajo del ruido (+3 en 300 rondas), porque el
    # desempate normal ya prefiere candidatos; se conserva porque el caso que
    # cubre -- un rival que va por delante -- si es real y el costo es nulo.
    CARRERA = True
    UMBRAL_RIESGO = 6           # candidatos que le quedan al rival
    EVIDENCIA_RIVAL = 2         # veces que el rival demostro usar su informacion

    # Prior sobre el secreto del rival: muchos agentes generan "numeros de 4
    # cifras" sin cero inicial. Mientras exista algun candidato que no empiece
    # en 0 se busca solo entre esos; si la evidencia los descarta todos, se
    # vuelve automaticamente a las 5040. Medido en 1200 partidas: -0.12 turnos
    # contra secretos sin cero inicial, +0.04 contra secretos uniformes, y
    # W-L +128 vs +70 contra rival_real.py.
    PRIORIZAR_SIN_CERO_INICIAL = True

    def __init__(self, nombre="AgentePicasFijas"):
        self.nombre = nombre
        self._rng = random.Random(int.from_bytes(os.urandom(16), "big"))
        self.secret = []
        self._reiniciar_estado()
        self.start()
        _registrar_en_interfaz(type(self))

    # ------------------------------------------------------------------ #
    #  Estado interno
    # ------------------------------------------------------------------ #
    def _reiniciar_estado(self):
        self._mascara = MASCARA_TOTAL          # candidatos al secreto del rival
        self._candidatos = list(range(N_CODIGOS))
        self._historia = []                    # [(indice_jugada, (picas, fijas))]
        self._ultima_jugada = None             # indice de la jugada sin responder
        self._jugadas_hechas = set()
        self._turno = 0
        self._racha_adversarial = 0
        self._particion_previa = None          # (peor_caso, total_clases)
        self.resuelto = False
        # Modelo del rival: codigos compatibles con TODAS mis respuestas, es
        # decir, exactamente la incertidumbre que le queda sobre mi secreto.
        self._rival_mascara = MASCARA_TOTAL
        self._rival_usa_info = 0

    # ------------------------------------------------------------------ #
    #  1) Inicializacion de ronda: genera el secreto
    # ------------------------------------------------------------------ #
    def start(self):
        """Genera el numero secreto: 4 digitos enteros unicos entre 0 y 9."""
        try:
            # Muestreo por rechazo: uniforme sobre los secretos permitidos
            # (intercambiar el 0 de posicion sesgaria hacia codigos con 0).
            digitos = self._rng.sample(range(BASE), LARGO)
            while not SECRETO_PERMITE_CERO_INICIAL and digitos[0] == 0:
                digitos = self._rng.sample(range(BASE), LARGO)
            self.secret = [int(d) for d in digitos]
        except Exception:
            self.secret = [1, 2, 3, 4]
        self._secreto_set = set(self.secret)
        self._reiniciar_estado()
        return self.secret

    # ------------------------------------------------------------------ #
    #  2) Intento del turno
    # ------------------------------------------------------------------ #
    def try_attempt(self):
        """Devuelve el intento del turno como lista de 4 enteros unicos."""
        try:
            indice = self._elegir_jugada()
        except Exception:
            indice = self._rng.randrange(N_CODIGOS)
        self._ultima_jugada = indice
        self._jugadas_hechas.add(indice)
        self._turno += 1
        return [int(d) for d in CODIGOS[indice]]

    # ------------------------------------------------------------------ #
    #  3) Evaluacion honesta del intento del rival
    # ------------------------------------------------------------------ #
    def discover(self, numeroLista):
        """Devuelve [picas, fijas] del intento del rival contra mi secreto."""
        try:
            intento = _normalizar_numero(numeroLista)
            if intento is None:
                return [0, 0]
            picas, fijas = _evaluar(intento, self.secret)
            try:
                self._actualizar_modelo_rival(intento, picas, fijas)
            except Exception:
                pass
            return [int(picas), int(fijas)]
        except Exception:
            return [0, 0]

    def _actualizar_modelo_rival(self, intento, picas, fijas):
        """Cada respuesta honesta que doy es informacion que el rival recibe.
        Replicando ese filtrado se sabe cuanta incertidumbre le queda."""
        if len(set(intento)) != LARGO:
            return
        indice = INDICE.get(tuple(intento))
        if indice is None:
            return
        restantes = _popcount(self._rival_mascara)
        # Que el rival juegue dentro de su propio conjunto de candidatos, ya
        # siendo este pequeno, es evidencia de que si esta usando su
        # informacion (un agente que adivina al azar casi nunca acierta ahi).
        if restantes <= 300 and (self._rival_mascara >> indice) & 1:
            self._rival_usa_info += 1
        nueva = _refinar(self._rival_mascara, indice, picas, fijas)
        if nueva:
            self._rival_mascara = nueva

    # ------------------------------------------------------------------ #
    #  4) Retroalimentacion del propio intento
    # ------------------------------------------------------------------ #
    def feedBack(self, retroalimentacionLista):
        """Incorpora [picas, fijas] del propio intento al modelo del rival."""
        try:
            respuesta = _normalizar_respuesta(retroalimentacionLista)
            if respuesta is None or self._ultima_jugada is None:
                return
            picas, fijas = respuesta
            indice = self._ultima_jugada
            self._ultima_jugada = None

            if fijas == LARGO:
                self.resuelto = True
                self._mascara = 1 << indice
                self._candidatos = [indice]
                return

            self._actualizar_sospecha_adversarial(indice, picas, fijas)
            self._historia.append((indice, (picas, fijas)))

            nueva = _refinar(self._mascara, indice, picas, fijas)
            if not nueva:
                nueva = self._recuperar()
            self._mascara = nueva
            # Se recalcula desde la mascara: tras _recuperar() el conjunto puede
            # crecer y filtrar la lista anterior dejaria candidatos fuera.
            self._candidatos = _indices(nueva)
        except Exception:
            self._ultima_jugada = None

    # ------------------------------------------------------------------ #
    #  Nucleo de decision
    # ------------------------------------------------------------------ #
    def _elegir_jugada(self):
        conjunto = self._mascara
        candidatos = self._candidatos
        total = len(candidatos)

        if total == 0:                                  # nunca deberia pasar
            self._mascara = conjunto = MASCARA_TOTAL
            self._candidatos = candidatos = list(range(N_CODIGOS))
            total = N_CODIGOS

        adversarial = self._racha_adversarial >= self.UMBRAL_ADVERSARIAL

        # Contra un rival que miente el prior es contraproducente: se refugia
        # en los codigos con cero inicial que el agente no esta partiendo.
        if self.PRIORIZAR_SIN_CERO_INICIAL and not adversarial:
            preferidos = conjunto & SIN_CERO_INICIAL
            if preferidos and preferidos != conjunto:
                conjunto = preferidos
                candidatos = [i for i in candidatos if (preferidos >> i) & 1]
                total = len(candidatos)

        # Con 1 o 2 candidatos ninguna jugada informativa supera a arriesgar
        # directamente un candidato: se gana ya o en el turno siguiente.
        if total <= 2:
            for i in candidatos:
                if i not in self._jugadas_hechas:
                    return i
            return candidatos[0]

        # Primer intento: por simetria de renombrado de digitos todas las
        # aperturas son equivalentes, asi que se elige al azar (impredecible).
        if self._turno == 0:
            return self._rng.randrange(N_CODIGOS)

        hechas = self._jugadas_hechas

        # Contra un rival adversarial el minimax es el criterio optimo; si no,
        # se usa el criterio configurado.
        criterio = "minimax" if adversarial else self.CRITERIO

        # En modo carrera, cuando el rival esta a punto de resolver, solo las
        # jugadas candidatas pueden ganar el turno: se deja de explorar.
        if self._debe_arriesgar(total):
            reserva = [i for i in candidatos if i not in hechas]
            reserva = reserva or candidatos
        else:
            reserva = range(N_CODIGOS)

        mejor_indice = candidatos[0]
        mejor_clave = None
        mejor_peor = total
        for indice in reserva:
            if indice in hechas:
                continue
            suma_cuadrados, suma_cubos, peor = _estadisticas(indice, conjunto)
            es_candidato = 0 if (conjunto >> indice) & 1 else 1
            if criterio == "minimax":
                clave = (peor, suma_cuadrados, es_candidato)
            elif criterio == "cubos":
                clave = (suma_cubos, peor, es_candidato)
            else:
                clave = (suma_cuadrados, peor, es_candidato)
            if mejor_clave is None or clave < mejor_clave:
                mejor_clave = clave
                mejor_indice = indice
                mejor_peor = peor

        # Tamano de la clase mas grande de la jugada elegida: sirve para
        # detectar despues si el rival siempre nos manda justo a esa clase.
        # Se mide sobre el conjunto COMPLETO aunque se haya jugado con el prior:
        # un rival que miente elige la clase mas grande de todo su espacio.
        if conjunto != self._mascara:
            mejor_peor = _estadisticas(mejor_indice, self._mascara)[2]
            total = len(self._candidatos)
        self._particion_previa = (mejor_peor, total)
        return mejor_indice

    def _debe_arriesgar(self, total):
        """Cierto cuando conviene jugar solo candidatos: el rival ya tiene mi
        secreto casi acorralado y no esta peor posicionado que yo. Explorar
        entonces regala el turno; jugar un candidato al menos puede empatar."""
        if not self.CARRERA or self._rival_usa_info < self.EVIDENCIA_RIVAL:
            return False
        restantes_rival = _popcount(self._rival_mascara)
        return restantes_rival <= self.UMBRAL_RIESGO and restantes_rival <= total

    def _actualizar_sospecha_adversarial(self, indice, picas, fijas):
        """Un rival honesto con secreto fijo cae en la clase mas grande solo a
        veces; uno que responde para maximizar la incertidumbre lo hace siempre."""
        datos = self._particion_previa
        self._particion_previa = None
        if not datos:
            return
        peor, total = datos
        if total < 8 or peor >= total or peor * 2 >= total:
            return                          # sin evidencia utilizable
        resultante = _refinar(self._mascara, indice, picas, fijas)
        cuenta = _popcount(resultante) if resultante else 0
        if cuenta == peor:
            self._racha_adversarial += 1
        else:
            self._racha_adversarial = 0

    def _recuperar(self):
        """El rival respondio de forma inconsistente: se descartan las
        restricciones mas antiguas hasta volver a tener candidatos."""
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

    # ------------------------------------------------------------------ #
    #  Alias de compatibilidad con otras variantes de ambiente
    # ------------------------------------------------------------------ #
    def compute(self, percept=None):
        """Ambientes antiguos: reciben el percept y esperan una cadena."""
        if percept is not None:
            self.feedBack(list(percept) if isinstance(percept, (list, tuple)) else percept)
        return "".join(str(d) for d in self.try_attempt())

    def respond(self, guess):
        """Alias de `discover` devolviendo tupla, como en los ambientes previos."""
        picas, fijas = self.discover(guess)
        return (picas, fijas)

    def guess(self):
        return self.try_attempt()

    def feedback(self, retroalimentacionLista):
        return self.feedBack(retroalimentacionLista)

    def reset(self):
        return self.start()

    def initRound(self):
        return self.start()

    def __repr__(self):
        return "<%s turno=%d candidatos=%d>" % (
            self.nombre, self._turno, len(self._candidatos),
        )


def _indices(mascara):
    """Lista de indices activos en un bitset."""
    salida = []
    i = 0
    while mascara:
        bajo = mascara & -mascara
        i = bajo.bit_length() - 1
        salida.append(i)
        mascara ^= bajo
    return salida


def _alias_try(self):
    """Expone el metodo literal `try` exigido por el reglamento. No puede
    declararse con `def try(...)` porque es palabra reservada de Python."""
    return self.try_attempt()


setattr(AgentePicasFijas, "try", _alias_try)


def _buscar_interfaz():
    """`interfazAgente` tal como la definio el ambiente (celda del notebook,
    que vive en __main__, o un modulo aparte), o None si no existe."""
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
    """Si el notebook ya definio `interfazAgente` al importar este archivo, la
    clase publica HEREDA de verdad de ella (aparece en __mro__), que es lo que
    exige `Ambiente.setup`. Si la interfaz pidiera un metodo abstracto que el
    agente no tiene, no se arriesga un TypeError al instanciar: se usa la
    clase normal registrada como subclase virtual."""
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


AgentePicasFijas = _heredar_de_interfaz(AgentePicasFijas)

# Alias de clase para que cualquier forma de importacion del ambiente funcione.
Agente = AgentePicasFijas
AgenteClase1 = AgentePicasFijas
AgenteClase2 = AgentePicasFijas
AgentePicasYFijas = AgentePicasFijas
TuAgente = AgentePicasFijas
Agent = AgentePicasFijas


# =============================================================================
#  Autoprueba rapida
# =============================================================================

if __name__ == "__main__":
    import time

    def es_intento_valido(lista):
        if not isinstance(lista, list) or len(lista) != 4:
            return False
        if not all(isinstance(x, int) and 0 <= x <= 9 for x in lista):
            return False
        return len(set(lista)) == 4

    rng = random.Random(7)
    turnos = []
    inicio = time.time()
    partidas = 200
    for _ in range(partidas):
        agente = AgentePicasFijas()
        secreto = rng.sample(range(10), 4)
        for turno in range(1, 21):
            intento = getattr(agente, "try")()
            assert es_intento_valido(intento), intento
            picas, fijas = _evaluar(intento, secreto)
            respuesta = [picas, fijas]
            assert isinstance(respuesta, list) and sum(respuesta) <= 4
            agente.feedBack(respuesta)
            if fijas == 4:
                turnos.append(turno)
                break
        else:
            turnos.append(99)

    duracion = time.time() - inicio
    print("Partidas          : %d" % partidas)
    print("Turnos promedio   : %.3f" % (sum(turnos) / len(turnos)))
    print("Peor caso         : %d" % max(turnos))
    print("Distribucion      : %s" % {t: turnos.count(t) for t in sorted(set(turnos))})
    print("Tiempo por partida: %.1f ms" % (1000.0 * duracion / partidas))
