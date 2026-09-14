# -*- coding: utf-8 -*-
"""
Genera el arbol de decision que usa Picas_Y_Fijas_Agent.py (bloque ARBOL).

En el ambiente nuevo los dos agentes adivinan el MISMO secreto por separado y
gana quien necesita menos turnos. El juez elige el secreto con random.sample,
asi que los 5040 secretos son igual de probables: el arbol minimiza la SUMA de
un costo sobre los 5040.

El costo de terminar el secreto s en el turno t es W[s][t] (menor = mejor):
    W[s][t] = peso_rivales * rivales(s, t) + peso_carrera * carrera(t) + t
  * rivales(s, t): suma sobre los rivales de referencia de
        +R si ese rival resuelve s ANTES del turno t   (derrota)
         0 si lo resuelve en el turno t                (empate)
        -R si lo resuelve DESPUES                      (victoria)
    Los rivales son programas deterministas: generar_arbol juega con cada uno
    los 5040 secretos para saber en que turno termina. Asi el arbol intenta
    terminar antes justo en los secretos donde habria empate o derrota.
  * carrera(t): lo mismo pero con la DISTRIBUCION de turnos de los rivales,
    sin mirar el secreto concreto (protege frente a rivales desconocidos).
  * t: desempate; con los otros pesos en 0 el arbol minimiza el promedio.

Costo de un conjunto S de candidatos cuando el proximo intento es el turno t:
    costo({s}, t)    = W[s][t]
    costo({a, b}, t) = min(W[a][t] + W[b][t+1], W[b][t] + W[a][t+1])
    costo(S, t)      = min sobre jugadas g de
                       [g en S] * W[g][t] + suma costo(S_c, t+1)
                       (S_c = clases de respuesta de g sobre S, sin [0,4])

No se pueden probar las 5040 jugadas en cada nodo, asi que en cada nodo solo se
evaluan EXACTAMENTE las mejores segun heuristicas baratas:
  * las K(n) mejores por suma de cuadrados (candidatos esperados restantes),
  * las K(n)//2 mejores por peor caso (minimax),
  * los mejores candidatos (jugadas que pueden ganar ya),
con memoria por (bitset, turno) y poda por cota inferior (en una clase, como
mucho 1 secreto se resuelve en el turno t y 13 en el t+1; el resto despues).
Las jugadas del SEGUNDO turno se evaluan en procesos paralelos.

Uso:
    python3 generar_arbol.py                                     # por defecto
    python3 generar_arbol.py --peso-rivales 0 --peso-carrera 0   # solo promedio
    python3 generar_arbol.py --rivales AgenteJuan,AgenteEntropico
    python3 generar_arbol.py --no-escribir                       # solo informa
"""

import argparse
import json
import multiprocessing as mp
import os
import re
import sys
import time
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import Picas_Y_Fijas_Agent as A  # noqa: E402

pc = A._popcount
MAX_TURNO = 16
ESCALA = 1000                         # peso de una victoria/derrota frente a 1 turno
RIVALES_POR_DEFECTO = "AgenteLexicografico,AgenteJuan,AgenteCrucetero,AgenteEntropico"
KS = [[500, 3], [150, 5], [40, 8], [0, 12]]      # (tamano minimo, jugadas a probar)

W = None          # W[s][t]
MASCARAS = None   # MASCARAS[t] = [(valor, bitset de secretos con W[s][t] == valor)]
G1 = None         # G1[t] = max_s W[s][t+1] - W[s][t]
G2 = None         # G2[t] = max_s W[s][t+2] - W[s][t]
_memo = {}


# --------------------------------------------------------------------------- #
#  Turnos de los rivales
# --------------------------------------------------------------------------- #
def _jugar_rival(nombre):
    import rivales_nuevo_ambiente as R
    clase = getattr(R, nombre)
    turnos = []
    for secreto in A.CODIGOS:
        agente = clase()
        agente.start()
        for t in range(1, 60):
            intento = agente.try_attempt()
            picas, fijas = A._evaluar(intento, secreto)
            if fijas == 4:
                break
            agente.feedBack([picas, fijas])
        turnos.append(t)
    return nombre, turnos


def turnos_rivales(nombres, procesos):
    with mp.Pool(min(procesos, len(nombres))) as pool:
        return dict(pool.map(_jugar_rival, nombres))


# --------------------------------------------------------------------------- #
#  Pesos
# --------------------------------------------------------------------------- #
def _signo(x):
    return (x > 0) - (x < 0)


def construir_pesos(rivales, peso_rivales, peso_carrera):
    n_turnos = MAX_TURNO + 3
    carrera = [0.0] * n_turnos
    for turnos in rivales.values():
        cuenta = Counter(turnos)
        for t in range(n_turnos):
            carrera[t] += sum(c * _signo(t - r) for r, c in cuenta.items()) / len(turnos)
    pesos = []
    for s in range(A.N_CODIGOS):
        fila = []
        for t in range(n_turnos):
            por_rival = sum(_signo(t - turnos[s]) for turnos in rivales.values())
            fila.append(round(ESCALA * (peso_rivales * por_rival + peso_carrera * carrera[t])) + t)
        pesos.append(fila)
    return pesos


def _configurar(ks, pesos):
    global KS, W, MASCARAS, G1, G2
    KS, W = ks, pesos
    n_turnos = len(pesos[0])
    MASCARAS = []
    for t in range(n_turnos):
        grupos = {}
        for s in range(A.N_CODIGOS):
            grupos[pesos[s][t]] = grupos.get(pesos[s][t], 0) | (1 << s)
        MASCARAS.append(list(grupos.items()))
    G1 = [max(pesos[s][t + 1] - pesos[s][t] for s in range(A.N_CODIGOS)) for t in range(n_turnos - 1)]
    G2 = [max(pesos[s][t + 2] - pesos[s][t] for s in range(A.N_CODIGOS)) for t in range(n_turnos - 2)]
    _memo.clear()


def _suma(conjunto, t):
    return sum(valor * pc(conjunto & mascara) for valor, mascara in MASCARAS[t])


def _cota(conjunto, t):
    """Cota inferior de costo(conjunto, t): los pesos no bajan con t, como
    mucho 1 secreto termina en t y 13 en t+1, el resto en t+2 o despues."""
    if t + 2 >= len(MASCARAS):
        return _suma(conjunto, min(t, len(MASCARAS) - 1))
    return max(_suma(conjunto, t),
               _suma(conjunto, t + 1) - G1[t],
               _suma(conjunto, t + 2) - G2[t] - 13 * G1[t + 1])


# --------------------------------------------------------------------------- #
#  Busqueda
# --------------------------------------------------------------------------- #
def _k(n):
    for limite, k in KS:
        if n > limite:
            return k
    return KS[-1][1]


def _pool(conjunto, k):
    """Jugadas a evaluar exactamente en este nodo."""
    puntuadas = []
    for g in range(A.N_CODIGOS):
        s2, peor = A._estadisticas(g, conjunto)
        no_cand = 0 if (conjunto >> g) & 1 else 1
        puntuadas.append((s2, peor, no_cand, g))
    por_cuadrados = sorted(puntuadas)
    por_peor = sorted(puntuadas, key=lambda x: (x[1], x[0], x[2]))
    candidatos = [x for x in por_cuadrados if x[2] == 0]
    pool = []
    for lista, cuantos in ((por_cuadrados, k), (por_peor, max(1, k // 2)), (candidatos, max(2, k // 3))):
        for x in lista[:cuantos]:
            if x[3] not in pool:
                pool.append(x[3])
    return pool


def _costo_jugada(conjunto, t, g, tope):
    """Costo de jugar g en el turno t; None si no mejora `tope` (poda)."""
    n = pc(conjunto)
    clases = sorted((x for _, x in A._particion(g, conjunto)), key=pc, reverse=True)
    acierta = (conjunto >> g) & 1
    if not acierta and len(clases) == 1 and pc(clases[0]) == n:
        return None                                   # no aporta informacion
    total = W[g][t] if acierta else 0
    cotas = [_cota(x, t + 1) for x in clases]
    resto = sum(cotas)
    if total + resto >= tope:
        return None
    for x, cota in zip(clases, cotas):
        resto -= cota
        total += costo(x, t + 1)[0]
        if total + resto >= tope:
            return None
    return total


def costo(conjunto, t):
    """(costo minimo, mejor jugada) del conjunto si el proximo turno es t."""
    clave = (conjunto, t)
    r = _memo.get(clave)
    if r is not None:
        return r
    n = pc(conjunto)
    if t + 2 >= len(W[0]):
        r = (10 ** 15, conjunto.bit_length() - 1)
    elif n == 1:
        s = conjunto.bit_length() - 1
        r = (W[s][t], s)
    elif n == 2:
        b = conjunto.bit_length() - 1
        a = (conjunto ^ (1 << b)).bit_length() - 1
        r = min((W[a][t] + W[b][t + 1], a), (W[b][t] + W[a][t + 1], b))
    else:
        mejor = (10 ** 15, None)
        for g in _pool(conjunto, _k(n)):
            c = _costo_jugada(conjunto, t, g, mejor[0])
            if c is not None and c < mejor[0]:
                mejor = (c, g)
        r = mejor
    _memo[clave] = r
    return r


def _politica(conjunto, t, ruta, salida):
    """Recorre el arbol elegido y guarda {ruta: jugada} de los nodos con 2 o
    mas candidatos (con 2, el orden importa cuando los pesos dependen del
    secreto)."""
    if pc(conjunto) <= 1:
        return
    _, g = costo(conjunto, t)
    salida[ruta] = g
    for (picas, fijas), x in A._particion(g, conjunto):
        _politica(x, t + 1, ruta + A._letra(picas, fijas), salida)


def _tarea(args):
    """Evalua una jugada concreta de segundo turno (hijo de la apertura)."""
    ruta, conjunto, g = args
    c = _costo_jugada(conjunto, 2, g, 10 ** 15)
    politica = {}
    if c is not None:
        politica[ruta] = g
        for (picas, fijas), x in A._particion(g, conjunto):
            _politica(x, 3, ruta + A._letra(picas, fijas), politica)
    return ruta, g, c, politica


def turnos_por_secreto(arbol):
    """Juega los 5040 secretos siguiendo el arbol y la regla del agente para
    los nodos fuera del arbol (primer candidato). Devuelve los turnos."""
    turnos = []
    for s in range(A.N_CODIGOS):
        conjunto, ruta, t = A.MASCARA_TOTAL, "", 1
        while True:
            g = arbol.get(ruta)
            if g is None:
                g = A._indices(conjunto)[0]
            if g == s:
                break
            picas, fijas = A._evaluar(A.CODIGOS[g], A.CODIGOS[s])
            conjunto = A._refinar(conjunto, g, picas, fijas)
            ruta += A._letra(picas, fijas)
            t += 1
        turnos.append(t)
    return turnos


def informe(turnos, rivales):
    cuenta = Counter(turnos)
    print("PROMEDIO EXACTO: %.4f turnos  peor %d  distribucion %s"
          % (sum(turnos) / len(turnos), max(turnos), dict(sorted(cuenta.items()))))
    for nombre, suyos in rivales.items():
        g = sum(1 for m, r in zip(turnos, suyos) if m < r)
        p = sum(1 for m, r in zip(turnos, suyos) if m > r)
        e = len(turnos) - g - p
        print("  vs %-20s gana %5.1f%%  empata %5.1f%%  pierde %5.1f%%  (5040 secretos)"
              % (nombre, 100 * g / 5040, 100 * e / 5040, 100 * p / 5040))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rivales", default=RIVALES_POR_DEFECTO,
                        help="clases de rivales_nuevo_ambiente.py separadas por comas")
    parser.add_argument("--evaluar", default=RIVALES_POR_DEFECTO,
                        help="rivales contra los que se informa el resultado")
    parser.add_argument("--peso-rivales", type=float, default=1.0)
    parser.add_argument("--peso-carrera", type=float, default=1.0)
    parser.add_argument("--ks", default=json.dumps(KS), help="K(n) para los nodos profundos")
    parser.add_argument("--k2", type=int, default=8, help="jugadas a probar en el segundo turno")
    parser.add_argument("--procesos", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--no-escribir", action="store_true")
    args = parser.parse_args()

    inicio = time.time()
    nombres = [x for x in args.rivales.split(",") if x]
    evaluar = [x for x in args.evaluar.split(",") if x]
    todos = turnos_rivales(sorted(set(nombres) | set(evaluar)), args.procesos)
    referencia = {n: todos[n] for n in nombres}
    ks = json.loads(args.ks)
    pesos = construir_pesos(referencia, args.peso_rivales, args.peso_carrera)
    _configurar(ks, pesos)

    apertura = A.INDICE[tuple(getattr(A, A.NOMBRE_AGENTE).PRIMER_INTENTO)]
    hijos = A._particion(apertura, A.MASCARA_TOTAL)
    tareas = []
    for (picas, fijas), x in hijos:
        n = pc(x)
        k2 = args.k2 if n > 150 else max(4, args.k2 // 2)
        for g in (_pool(x, k2) if n > 2 else [costo(x, 2)[1]]):
            tareas.append((A._letra(picas, fijas), x, g))
    tareas.sort(key=lambda tarea: -pc(tarea[1]))
    print("Rivales de referencia %s | pesos rivales=%g carrera=%g | K=%s k2=%d | %d tareas"
          % (nombres, args.peso_rivales, args.peso_carrera, ks, args.k2, len(tareas)))

    mejores = {}
    with mp.Pool(args.procesos, initializer=_configurar, initargs=(ks, pesos)) as pool:
        for ruta, g, c, politica in pool.imap_unordered(_tarea, tareas):
            if c is not None and (ruta not in mejores or c < mejores[ruta][0]):
                mejores[ruta] = (c, g, politica)

    arbol = {"": apertura}
    for (picas, fijas), x in hijos:
        ruta = A._letra(picas, fijas)
        if ruta in mejores:
            arbol.update(mejores[ruta][2])

    turnos = turnos_por_secreto(arbol)
    informe(turnos, {n: todos[n] for n in evaluar})
    print("nodos %d  tiempo %.0fs" % (len(arbol), time.time() - inicio))

    if args.no_escribir:
        return
    cuenta = Counter(turnos)
    tokens = ["%s:%s" % (ruta, "".join(map(str, A.CODIGOS[g]))) for ruta, g in sorted(arbol.items())]
    lineas, linea = [], ""
    for token in tokens:
        if len(linea) + len(token) + 1 > 96:
            lineas.append(linea)
            linea = ""
        linea = (linea + " " + token).strip()
    lineas.append(linea)
    bloque = ("# >>> ARBOL (generado por generar_arbol.py)\n"
              "ARBOL_CONFIGURACION = %r\n"
              "ARBOL_PROMEDIO = %.4f\n"
              "ARBOL_DISTRIBUCION = %r\n"
              "ARBOL_TEXTO = \"\"\"\n%s\n\"\"\"\n"
              "# <<< ARBOL" % (
                  "rivales=%s peso_rivales=%g peso_carrera=%g K=%s k2=%d"
                  % (",".join(nombres), args.peso_rivales, args.peso_carrera, ks, args.k2),
                  sum(turnos) / len(turnos), dict(sorted(cuenta.items())), "\n".join(lineas)))
    ruta_agente = os.path.join(AQUI, "Picas_Y_Fijas_Agent.py")
    with open(ruta_agente, encoding="utf-8") as f:
        fuente = f.read()
    fuente, cambios = re.subn(r"# >>> ARBOL.*?# <<< ARBOL", lambda _: bloque, fuente, flags=re.S)
    if cambios != 1:
        raise SystemExit("No se encontraron las marcas del bloque ARBOL")
    with open(ruta_agente, "w", encoding="utf-8") as f:
        f.write(fuente)
    print("Bloque ARBOL escrito en Picas_Y_Fijas_Agent.py (%d entradas)" % len(arbol))


if __name__ == "__main__":
    main()
