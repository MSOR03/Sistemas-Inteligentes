# -*- coding: utf-8 -*-
"""
Verificacion contra el agente real del companero (rival_real.PicasFijasAgent),
usando el bucle del ambiente oficial.

Mide, ademas del marcador, dos cosas que deciden el torneo:
  * cuantas veces el rival REVIENTA (IndexError) porque su espacio de busqueda
    excluye los numeros que empiezan por 0, y
  * si conviene renunciar al cero inicial en el propio secreto para no
    provocar esa caida.

Uso:  python3 test_rival_real.py [rondas]
"""

import multiprocessing as mp
import random
import sys
from collections import Counter

import Picas_Y_Fijas_Agent as M
from rival_real import PicasFijasAgent


def es_intento_valido(lista):
    if not isinstance(lista, list) or len(lista) != 4:
        return False
    if not all(isinstance(x, int) and 0 <= x <= 9 for x in lista):
        return False
    return len(set(lista)) == 4


def es_respuesta_valida(r):
    return (isinstance(r, list) and len(r) == 2
            and all(isinstance(x, int) for x in r)
            and r[0] >= 0 and r[1] >= 0 and r[0] + r[1] <= 4)


def _invocar_try(agente):
    if hasattr(agente, "try"):
        return getattr(agente, "try")()
    return agente.try_attempt()


def _ronda(args):
    """Una ronda completa. Devuelve un dict con todo lo observado."""
    indice, cero_inicial = args
    random.seed(400_000 + indice)
    M.SECRETO_PERMITE_CERO_INICIAL = cero_inicial

    mio = M.AgentePicasFijas()
    rival = PicasFijasAgent()
    mio.start()
    rival.start()

    reporte = {
        "resultado": 0, "turnos": 0, "caida_rival": False,
        "infracciones_mias": 0, "infracciones_rival": 0,
        "cero_inicial": mio.secret[0] == 0,
    }

    for turno in range(1, 101):
        reporte["turnos"] = turno
        try:
            intento_mio = _invocar_try(mio)
            intento_rival = _invocar_try(rival)
            if not es_intento_valido(intento_mio):
                reporte["infracciones_mias"] += 1
            if not es_intento_valido(intento_rival):
                reporte["infracciones_rival"] += 1

            eval_mio = rival.discover(intento_mio)
            eval_rival = mio.discover(intento_rival)
            if not es_respuesta_valida(eval_rival):
                reporte["infracciones_mias"] += 1
            if not es_respuesta_valida(eval_mio):
                reporte["infracciones_rival"] += 1

            mio.feedBack(eval_mio)
            rival.feedBack(eval_rival)
        except Exception:
            # En el ambiente oficial esto NO esta protegido: la excepcion sube
            # y aborta el torneo entero.
            reporte["caida_rival"] = True
            return reporte

        gano_yo = eval_mio[1] == 4
        gano_rival = eval_rival[1] == 4
        if gano_yo and gano_rival:
            reporte["resultado"] = 0
            return reporte
        if gano_yo:
            reporte["resultado"] = 1
            return reporte
        if gano_rival:
            reporte["resultado"] = -1
            return reporte
    return reporte


def _solo_rival(semilla):
    """Turnos que tarda el rival en resolver un secreto SIN cero inicial."""
    random.seed(semilla)
    rival = PicasFijasAgent()
    rival.start()
    secreto = random.choice(rival.candidate_set)
    for turno in range(1, 21):
        g = rival.try_attempt()
        resp = rival.check_option(g, secreto)
        if resp == [0, 4]:
            return turno
        try:
            rival.feedBack(resp)
        except Exception:
            return 20
    return 20


def informe(datos, titulo):
    total = len(datos)
    caidas = sum(1 for d in datos if d["caida_rival"])
    validas = [d for d in datos if not d["caida_rival"]]
    gano = sum(1 for d in validas if d["resultado"] == 1)
    empate = sum(1 for d in validas if d["resultado"] == 0)
    perdio = sum(1 for d in validas if d["resultado"] == -1)
    mias = sum(d["infracciones_mias"] for d in datos)
    suyas = sum(d["infracciones_rival"] for d in datos)
    turnos = [d["turnos"] for d in validas if d["resultado"] == 1]

    print("  %s" % titulo)
    print("    rondas jugadas            : %d" % total)
    print("    CAIDAS del rival          : %d  (%.1f%% de las rondas)"
          % (caidas, 100.0 * caidas / total))
    if validas:
        print("    marcador (rondas limpias) : %d ganadas / %d empates / %d perdidas   -> %.1f%% de puntos"
              % (gano, empate, perdio,
                 100.0 * (gano + 0.5 * empate) / len(validas)))
    print("    turno medio al ganar      : %.2f" % (sum(turnos) / len(turnos) if turnos else 0))
    print("    infracciones mias         : %d" % mias)
    print("    infracciones del rival    : %d" % suyas)
    print()
    return caidas, gano, empate, perdio


def main():
    rondas = int(sys.argv[1]) if len(sys.argv) > 1 else 400

    with mp.Pool(processes=4) as pool:
        print("=" * 78)
        print(" FUERZA DEL RIVAL EN SOLITARIO")
        print("=" * 78)
        turnos = pool.map(_solo_rival, range(1000, 1000 + rondas), chunksize=8)
        cuenta = Counter(turnos)
        print("  promedio %.3f turnos   peor %d   distribucion %s"
              % (sum(turnos) / len(turnos), max(turnos),
                 {t: cuenta[t] for t in sorted(cuenta)}))
        print("  (mi agente: 5.20 turnos de promedio, peor caso 7)")
        print()

        print("=" * 78)
        print(" ENFRENTAMIENTO EN EL AMBIENTE OFICIAL (%d rondas por configuracion)" % rondas)
        print("=" * 78)
        con_cero = pool.map(_ronda, [(i, True) for i in range(rondas)], chunksize=4)
        informe(con_cero, "A) Mi secreto uniforme sobre las 5040 (permite cero inicial)")

        sin_cero = pool.map(_ronda, [(i, False) for i in range(rondas)], chunksize=4)
        informe(sin_cero, "B) Mi secreto sin cero inicial (4536 opciones)")


if __name__ == "__main__":
    main()
