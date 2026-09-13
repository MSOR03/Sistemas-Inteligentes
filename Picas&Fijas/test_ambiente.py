# -*- coding: utf-8 -*-
"""
Verificacion contra el codigo REAL de Ambiente.ipynb.

No reescribe el ambiente: extrae del notebook la celda que define
`jugar_ronda` / `ejecutar_torneo` y la ejecuta tal cual, cambiando solo la
linea de importacion para inyectar los agentes.

  1. Interfaz: ejecuta la celda `interfazAgente` del notebook en __main__
     (como Colab), importa el agente despues y verifica herencia real,
     isinstance/issubclass y que la celda del ambiente compile.
  2. Torneo oficial a 3 rondas: mi agente vs rival_real y vs si mismo.
  3. Estadistica: N torneos con `jugar_ronda` del notebook, alternando
     posiciones, contando infracciones y excepciones.

Uso:  python3 test_ambiente.py [torneos]
"""

import contextlib
import io
import json
import multiprocessing as mp
import os
import random
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)


def codigo_celda(marcador):
    """Codigo de la primera celda del notebook que contiene `marcador`."""
    with open(os.path.join(AQUI, "Ambiente.ipynb"), encoding="utf-8") as f:
        nb = json.load(f)
    for celda in nb["cells"]:
        fuente = "".join(celda["source"])
        if celda["cell_type"] == "code" and marcador in fuente:
            return fuente
    raise RuntimeError("No se encontro la celda con %s" % marcador)


# --------------------------------------------------------------------------- #
#  Interfaz: se ejecuta la celda REAL del notebook dentro de __main__, que es
#  donde Colab/Jupyter ejecuta las celdas y donde el agente la busca.
# --------------------------------------------------------------------------- #
AVISOS = []
_celda_interfaz = codigo_celda("class interfazAgente")
try:
    exec(compile(_celda_interfaz, "Ambiente.ipynb[interfaz]", "exec"), sys.modules["__main__"].__dict__)
except Exception as e:                      # p.ej. Python <= 3.13: `-> list(int)`
    AVISOS.append("la celda interfazAgente falla en este Python (%s: %s); se usa "
                  "la misma celda sin la anotacion `-> list(int)`" % (type(e).__name__, e))
    exec(_celda_interfaz.replace("-> list(int)", ""), sys.modules["__main__"].__dict__)
if "-> list(int)" in _celda_interfaz and not AVISOS:
    AVISOS.append("`-> list(int)` solo funciona en Python >= 3.14 (anotaciones diferidas); "
                  "en Colab (3.12) la celda lanza TypeError y la interfaz no queda definida")
interfazAgente = sys.modules["__main__"].interfazAgente

import Picas_Y_Fijas_Agent as M          # noqa: E402  (tras definir la interfaz)
from rival_real import PicasFijasAgent   # noqa: E402


def ambiente_del_notebook(clase1, clase2):
    """Ejecuta la celda del ambiente sin la importacion ni la llamada final."""
    lineas = []
    for linea in codigo_celda("def jugar_ronda").splitlines():
        texto = linea.strip()
        if texto.startswith("from "):
            continue                                   # importaciones de agentes
        if texto == "ejecutar_torneo()":
            continue
        lineas.append(linea)
    espacio = {"AgenteClase1": clase1, "AgenteClase2": clase2, "__name__": "ambiente"}
    exec(compile("\n".join(lineas), "Ambiente.ipynb", "exec"), espacio)
    return espacio


# --------------------------------------------------------------------------- #
#  1) Interfaz
# --------------------------------------------------------------------------- #
def verificar_interfaz():
    print("=" * 74)
    print(" 1. INTERFAZ (Ambiente.setup)")
    print("=" * 74)
    print("  Python local: %d.%d" % sys.version_info[:2])
    for aviso in AVISOS:
        print("  AVISO %s" % aviso)
    print("  interfaz del notebook, metodos abstractos: %s"
          % ", ".join(sorted(interfazAgente.__abstractmethods__)))
    try:
        compile(codigo_celda("def jugar_ronda"), "celda ambiente", "exec")
        print("  celda del ambiente: compila")
    except SyntaxError as e:
        print("  AVISO celda del ambiente NO compila, linea %s: %r  (corregir la importacion)"
              % (e.lineno, (e.text or "").strip()))
    agente = M.AgentePicasFijas()
    agente.start()
    ok = {
        "hereda de verdad (interfaz en __mro__)": interfazAgente in type(agente).__mro__,
        "sin metodos abstractos pendientes": not getattr(type(agente), "__abstractmethods__", None),
        "issubclass(clase, interfazAgente)": issubclass(M.AgentePicasFijas, interfazAgente),
        "isinstance(agente, interfazAgente)": isinstance(agente, interfazAgente),
        "hasattr(agente, 'try')": hasattr(agente, "try"),
        "hasattr(agente, 'try_attempt')": hasattr(agente, "try_attempt"),
        "secreto valido tras start()": len(set(agente.secret)) == 4
        and all(isinstance(d, int) and 0 <= d <= 9 for d in agente.secret),
    }
    for clave, valor in ok.items():
        print("  %-40s %s" % (clave, "OK" if valor else "FALLA"))
    return all(ok.values())


# --------------------------------------------------------------------------- #
#  2) Torneo tal cual lo imprime el notebook
# --------------------------------------------------------------------------- #
def torneo_demo():
    print()
    print("=" * 74)
    print(" 2. ejecutar_torneo() DEL NOTEBOOK")
    print("=" * 74)
    for titulo, c1, c2 in (("Mi agente (A1) vs rival_real (A2)", M.AgentePicasFijas, PicasFijasAgent),
                           ("Mi agente (A1) vs mi agente (A2)", M.AgentePicasFijas, M.AgentePicasFijas)):
        print("  -- %s" % titulo)
        amb = ambiente_del_notebook(c1, c2)
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            amb["ejecutar_torneo"]()
        for linea in salida.getvalue().strip().splitlines():
            if linea.strip():
                print("     " + linea)


# --------------------------------------------------------------------------- #
#  3) Estadistica con jugar_ronda del notebook
# --------------------------------------------------------------------------- #
class _Espia:
    """Envuelve un agente para registrar infracciones sin alterar el juego."""

    def __init__(self, agente, registro):
        self.a, self.reg = agente, registro

    def start(self):
        r = self.a.start()
        s = getattr(self.a, "secret", None) or getattr(self.a, "my_number", None)
        if not (isinstance(s, list) and len(s) == 4 and len(set(s)) == 4
                and all(isinstance(d, int) and 0 <= d <= 9 for d in s)):
            self.reg["secreto"] += 1
        return r

    def try_attempt(self):
        t0 = time.perf_counter()
        x = self.a.try_attempt()
        self.reg["max_ms"] = max(self.reg["max_ms"], 1000 * (time.perf_counter() - t0))
        if not (isinstance(x, list) and len(x) == 4 and len(set(x)) == 4
                and all(isinstance(d, int) and 0 <= d <= 9 for d in x)):
            self.reg["intento"] += 1
        return x

    def discover(self, intento):
        r = self.a.discover(intento)
        if not (isinstance(r, list) and len(r) == 2 and all(isinstance(v, int) for v in r)
                and r[0] >= 0 and r[1] >= 0 and r[0] + r[1] <= 4):
            self.reg["respuesta"] += 1
        return r

    def feedBack(self, r):
        return self.a.feedBack(r)


def _torneo(args):
    semilla, rival = args
    random.seed(semilla)
    amb = ambiente_del_notebook(None, None)
    reg = {"secreto": 0, "intento": 0, "respuesta": 0, "max_ms": 0.0}
    mio = _Espia(M.AgentePicasFijas(), reg)
    otro = PicasFijasAgent() if rival == "real" else M.AgentePicasFijas()
    mis_v = sus_v = 0
    with contextlib.redirect_stdout(io.StringIO()):
        for ronda in range(1, 4):
            if (semilla + ronda) % 2:
                r = amb["jugar_ronda"](mio, otro, ronda)
                mis_v += r == 1
                sus_v += r == 2
            else:
                r = amb["jugar_ronda"](otro, mio, ronda)
                mis_v += r == 2
                sus_v += r == 1
    return mis_v, sus_v, reg


def estadistica(torneos):
    print()
    print("=" * 74)
    print(" 3. %d TORNEOS (3 rondas c/u) con jugar_ronda del notebook" % torneos)
    print("=" * 74)
    total_infr = 0
    with mp.Pool(max(1, min(12, os.cpu_count() or 1))) as pool:
        for rival in ("real", "espejo"):
            datos = pool.map(_torneo, [(10_000 + i, rival) for i in range(torneos)], chunksize=2)
            g = sum(1 for a, b, _ in datos if a > b)
            p = sum(1 for a, b, _ in datos if a < b)
            e = torneos - g - p
            rg = sum(a for a, _, _ in datos)
            rp = sum(b for _, b, _ in datos)
            infr = sum(r["secreto"] + r["intento"] + r["respuesta"] for _, _, r in datos)
            lento = max(r["max_ms"] for _, _, r in datos)
            total_infr += infr
            print("  vs %-8s torneos G/E/P %3d/%3d/%3d  (%.1f%% puntos) | rondas G/P %d/%d"
                  " | infracciones %d | turno mas lento %.0f ms"
                  % (rival, g, e, p, 100.0 * (g + 0.5 * e) / torneos, rg, rp, infr, lento))
    return total_infr


def main():
    torneos = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    ok = verificar_interfaz()
    torneo_demo()
    infr = estadistica(torneos)
    print()
    print("VEREDICTO: %s" % ("CONFORME" if ok and infr == 0 else "REVISAR"))


if __name__ == "__main__":
    main()
