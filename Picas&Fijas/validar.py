# -*- coding: utf-8 -*-
"""
Validacion final del agente con la configuracion de competencia.

  1. Conformidad con el reglamento en cada llamada del ambiente.
  2. Distribucion de turnos resolviendo en solitario.
  3. Torneo contra los rivales derivados de la carpeta examples/.

Uso:  python3 validar.py [partidas] [rondas_por_rival]
"""

import multiprocessing as mp
import random
import sys
from collections import Counter

import Picas_Y_Fijas_Agent as M
from test_torneo import (
    RivalAleatorio, RivalConsistente, RivalEntropico, RivalMinimax, RivalTramposo,
    es_intento_valido, es_respuesta_valida, jugar_ronda,
)

RIVALES = {
    "Aleatorio": RivalAleatorio,
    "Consistente": RivalConsistente,
    "Entropico": RivalEntropico,
    "Minimax": RivalMinimax,
    "Tramposo": RivalTramposo,
}


def _solitaria(semilla):
    rng = random.Random(semilla)
    agente = M.AgentePicasFijas()
    agente.start()
    secreto = rng.sample(range(10), 4)
    for turno in range(1, 13):
        intento = agente.try_attempt()
        if not es_intento_valido(intento):
            return -1
        picas, fijas = M._evaluar(intento, secreto)
        if not es_respuesta_valida([picas, fijas]):
            return -1
        agente.feedBack([picas, fijas])
        if fijas == 4:
            return turno
    return 12


def _ronda(args):
    nombre, indice = args
    random.seed(900_000 + indice)
    mio = M.AgentePicasFijas()
    rival = RIVALES[nombre]()
    if indice % 2 == 0:                       # se alterna la posicion
        res, turnos, inc = jugar_ronda(mio, rival)
        propio = 1
    else:
        res, turnos, inc = jugar_ronda(rival, mio)
        propio = 2
    # Solo interesan las infracciones del agente propio.
    etiqueta = "A1" if propio == 1 else "A2"
    mias = [x for x in inc if etiqueta in x]
    if res == 0:
        marcador = 0
    else:
        marcador = 1 if res == propio else -1
    return marcador, turnos, mias


def main():
    partidas = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    rondas = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    with mp.Pool(processes=4) as pool:
        print("=" * 78)
        print(" 1. DISTRIBUCION DE TURNOS  (%d partidas, configuracion final)" % partidas)
        print("=" * 78)
        turnos = pool.map(_solitaria, range(70_000, 70_000 + partidas), chunksize=8)
        assert -1 not in turnos, "se produjo una jugada o respuesta invalida"
        cuenta = Counter(turnos)
        promedio = sum(turnos) / len(turnos)
        hasta5 = sum(c for t, c in cuenta.items() if t <= 5) / partidas
        print("  promedio %.3f turnos   peor caso %d   P(<=5 turnos) %.3f"
              % (promedio, max(turnos), hasta5))
        print("  distribucion: %s"
              % {t: "%.1f%%" % (100.0 * cuenta[t] / partidas) for t in sorted(cuenta)})

        print()
        print("=" * 78)
        print(" 2. TORNEO EN EL AMBIENTE OFICIAL  (%d rondas por rival)" % rondas)
        print("=" * 78)
        print("  %-13s %6s %7s %7s %9s %8s   %s"
              % ("RIVAL", "GANO", "EMPATE", "PERDIO", "%PUNTOS", "TURNOS", "INFRACCIONES"))
        infracciones = 0
        for nombre in RIVALES:
            datos = pool.map(_ronda, [(nombre, i) for i in range(rondas)], chunksize=2)
            gano = sum(1 for m, _, _ in datos if m == 1)
            empate = sum(1 for m, _, _ in datos if m == 0)
            perdio = sum(1 for m, _, _ in datos if m == -1)
            propias = sum(len(x) for _, _, x in datos)
            infracciones += propias
            medias = sum(t for _, t, _ in datos) / len(datos)
            print("  %-13s %6d %7d %7d %8.1f%% %8.2f   %d"
                  % (nombre, gano, empate, perdio,
                     100.0 * (gano + 0.5 * empate) / rondas, medias, propias))

        print()
        print("=" * 78)
        print(" 3. VEREDICTO")
        print("=" * 78)
        print("  Infracciones reglamentarias del agente: %d" % infracciones)
        print("  %s" % ("CONFORME: el agente nunca incumplio una regla."
                        if infracciones == 0 else
                        "ATENCION: revisar las infracciones reportadas."))


if __name__ == "__main__":
    main()
