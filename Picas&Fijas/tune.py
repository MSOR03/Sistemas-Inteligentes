# -*- coding: utf-8 -*-
"""
Ajuste empirico de la politica del agente.

Fase 1: distribucion de turnos de cada criterio jugando en solitario.
        Con esas distribuciones se calcula el marcador de CARRERA esperado
        (ganar - perder) de cada criterio frente a los demas, que es la
        metrica que realmente decide el torneo.

Fase 2: enfrentamiento directo para medir el valor del modo carrera
        (arriesgar jugando solo candidatos cuando el rival esta por resolver).
"""

import multiprocessing as mp
import random
import sys
from collections import Counter

import Picas_Y_Fijas_Agent as M


MAX_TURNOS = 12


# ---------------------------------------------------------------- fase 1 ----

def _partida_solitaria(args):
    criterio, semilla = args
    rng = random.Random(semilla)
    agente = M.AgentePicasFijas()
    agente.CRITERIO = criterio
    agente.CARRERA = False
    agente.start()
    secreto = rng.sample(range(10), 4)
    for turno in range(1, MAX_TURNOS + 1):
        intento = agente.try_attempt()
        picas, fijas = M._evaluar(intento, secreto)
        agente.feedBack([picas, fijas])
        if fijas == 4:
            return turno
    return MAX_TURNOS


def distribucion(criterio, partidas, pool):
    tareas = [(criterio, 10_000 + i) for i in range(partidas)]
    turnos = pool.map(_partida_solitaria, tareas, chunksize=8)
    cuenta = Counter(turnos)
    return {t: cuenta[t] / partidas for t in sorted(cuenta)}


def marcador_carrera(p, q):
    """Ganar - perder cuando una distribucion de turnos p corre contra q."""
    total = 0.0
    for turno_p, prob_p in p.items():
        gano = sum(pr for t, pr in q.items() if t > turno_p)
        perdi = sum(pr for t, pr in q.items() if t < turno_p)
        total += prob_p * (gano - perdi)
    return total


# ---------------------------------------------------------------- fase 2 ----

def _configurar(agente, config):
    for clave, valor in config.items():
        setattr(agente, clave, valor)
    agente.start()
    return agente


def _duelo(args):
    config_a, config_b, semilla = args
    random.seed(semilla)
    a = _configurar(M.AgentePicasFijas(), config_a)
    b = _configurar(M.AgentePicasFijas(), config_b)

    for _ in range(1, 101):
        intento_a = a.try_attempt()
        intento_b = b.try_attempt()
        eval_a = b.discover(intento_a)
        eval_b = a.discover(intento_b)
        a.feedBack(eval_a)
        b.feedBack(eval_b)
        gana_a, gana_b = eval_a[1] == 4, eval_b[1] == 4
        if gana_a and gana_b:
            return 0
        if gana_a:
            return 1
        if gana_b:
            return -1
    return 0


def duelo(config_a, config_b, rondas, pool):
    tareas = [(config_a, config_b, 500_000 + i) for i in range(rondas)]
    resultados = pool.map(_duelo, tareas, chunksize=4)
    gano = resultados.count(1)
    perdio = resultados.count(-1)
    empate = resultados.count(0)
    return gano, empate, perdio


# ------------------------------------------------------------------ main ----

def main():
    partidas = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    rondas = int(sys.argv[2]) if len(sys.argv) > 2 else 300

    with mp.Pool(processes=4) as pool:
        print("=" * 78)
        print(" FASE 1 - distribucion de turnos (%d partidas por criterio)" % partidas)
        print("=" * 78)
        distribuciones = {}
        for criterio in ("cuadrados", "cubos", "minimax"):
            dist = distribucion(criterio, partidas, pool)
            distribuciones[criterio] = dist
            promedio = sum(t * p for t, p in dist.items())
            hasta5 = sum(p for t, p in dist.items() if t <= 5)
            peor = max(dist)
            print("%-10s  promedio %.3f   P(<=5) %.3f   peor %d   %s"
                  % (criterio, promedio, hasta5, peor,
                     {t: round(p, 3) for t, p in dist.items()}))

        print("\nMarcador de carrera (fila contra columna, ganar - perder):")
        nombres = list(distribuciones)
        print("%-12s%s" % ("", "".join("%12s" % n for n in nombres)))
        for a in nombres:
            fila = "".join("%12.4f" % marcador_carrera(distribuciones[a], distribuciones[b])
                           for b in nombres)
            print("%-12s%s" % (a, fila))

        mejor = max(nombres, key=lambda a: min(
            marcador_carrera(distribuciones[a], distribuciones[b]) for b in nombres))
        print("\nMejor criterio en el peor caso: %s" % mejor)

        print("\n" + "=" * 78)
        print(" FASE 2 - valor del modo carrera (%d rondas por duelo)" % rondas)
        print("=" * 78)
        base = {"CRITERIO": mejor, "CARRERA": False}
        for umbral in (6, 12, 25):
            reta = {"CRITERIO": mejor, "CARRERA": True, "UMBRAL_RIESGO": umbral}
            g, e, p = duelo(reta, base, rondas, pool)
            print("carrera(umbral=%2d) vs sin carrera:  %3d-%3d-%3d   neto %+d"
                  % (umbral, g, e, p, g - p))


if __name__ == "__main__":
    main()
