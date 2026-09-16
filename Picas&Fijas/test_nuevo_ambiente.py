# -*- coding: utf-8 -*-
"""
Verificacion con el codigo REAL de Ambientes/Ambiente_Definitivo.ipynb.

El ambiente no se reescribe: se leen del notebook la celda `interfazAgente` y
la celda del torneo (`TorneoPicasFijasUI`) y se ejecutan tal cual. Solo se
sustituyen por objetos vacios las librerias graficas que no existen fuera de
Colab (ipywidgets, IPython.display, matplotlib), y se "pulsan" los controles
desde codigo: desplegables, semilla, numero de rondas y boton "Torneo Masivo".

Para imitar la carpeta de Drive, los agentes se copian a una carpeta temporal
y el ambiente la escanea con su propio `escanear_directorio`.

  1. Carga: el ambiente encuentra el agente, hereda de `interfazAgente`, no
     aparece duplicado en el desplegable.
  2. Torneos: el agente contra cada rival, N rondas con semilla fija por ronda
     (los mismos secretos para todos los rivales). Se cuentan victorias,
     empates, intentos invalidos, ms por turno y caidas del rival.

Uso:  python3 test_nuevo_ambiente.py [rondas_por_rival]
"""

import contextlib
import io
import json
import multiprocessing as mp
import os
import shutil
import sys
import tempfile
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
NOTEBOOK = os.path.join(AQUI, "Ambientes", "Ambiente_Definitivo.ipynb")

# Archivos que se ponen en la "carpeta de Drive" simulada.
ARCHIVOS = [
    "Picas_Y_Fijas_Agent_Compute.py",
    "Rival_Lexicografico.py",
    "Rival_Minimax.py",
    "Rival_Entropico.py",
    "Rival_Crucetero.py",
    "Rival_Juan.py",
]
AGENTE_PY = "Picas_Y_Fijas_Agent_Compute.py"
# El nombre de la clase lo pone el propio .py (NOMBRE_AGENTE), asi que la
# entrada del desplegable se busca por ARCHIVO y no se escribe a mano: asi
# renombrar el agente no rompe esta prueba.
MI_AGENTE = None


def _clave_de_mi_agente(ui):
    claves = [k for k in ui.agentes_disponibles if k.endswith("(%s)" % AGENTE_PY)]
    return claves[0] if len(claves) == 1 else None
# El ambiente definitivo solo registra clases con `compute`. Los rivales de
# `rival_real.py` y `rivales_nuevo_ambiente.py` usan la interfaz vieja
# (start/try_attempt/feedBack) y por eso NO aparecen en su desplegable; los
# `Rival_*.py` son esos mismos agentes portados a `compute`.
RIVALES = [
    "AgenteEstrategico",                                  # incluido en el notebook
    "AgenteAleatorio",                                    # incluido en el notebook
    "RivalLexicografico (Rival_Lexicografico.py)",        # suelo: primer candidato
    "RivalJuan (Rival_Juan.py)",                          # apertura 3579 + tabla
    "RivalCrucetero (Rival_Crucetero.py)",                # minimax con corte
    "RivalMinimax (Rival_Minimax.py)",                    # minimax de Knuth
    "RivalEntropico (Rival_Entropico.py)",                # maxima entropia
]


# --------------------------------------------------------------------------- #
#  Sustitutos de las librerias graficas
# --------------------------------------------------------------------------- #
class _Widget:
    def __init__(self, *args, **kwargs):
        self.__dict__.update(kwargs)
        self.value = kwargs.get("value")
        self.index = 0

    def on_click(self, funcion):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, nombre):
        return lambda *a, **k: _Widget()


def _instalar_sustitutos():
    widgets = types.ModuleType("ipywidgets")
    for nombre in ("Dropdown", "Text", "BoundedIntText", "Button", "Checkbox", "Output",
                   "VBox", "HBox", "HTML", "Label", "IntProgress", "Layout"):
        setattr(widgets, nombre, _Widget)
    ipython = types.ModuleType("IPython")
    display = types.ModuleType("IPython.display")
    display.display = lambda *a, **k: None
    display.clear_output = lambda *a, **k: None
    ipython.display = display
    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    pyplot.subplots = lambda *a, **k: (_Widget(), (_Widget(), _Widget(), _Widget()))
    pyplot.tight_layout = pyplot.show = lambda *a, **k: None
    matplotlib.pyplot = pyplot
    sys.modules.update({
        "ipywidgets": widgets, "IPython": ipython, "IPython.display": display,
        "matplotlib": matplotlib, "matplotlib.pyplot": pyplot,
    })


def _celda(marcador):
    """Fuente de la ULTIMA celda de codigo que contiene `marcador`.

    Tiene que ser la ultima: el notebook trae dos celdas con
    `class TorneoPicasFijasUI`, la del ambiente viejo (start/try_attempt/
    feedBack) y la definitiva (compute). Quedarse con la primera hacia que
    esta prueba midiera un ambiente que ya no es el del torneo."""
    with open(NOTEBOOK, encoding="utf-8") as f:
        nb = json.load(f)
    fuentes = ["".join(c["source"]) for c in nb["cells"]
               if c["cell_type"] == "code" and marcador in "".join(c["source"])]
    if not fuentes:
        raise RuntimeError("No se encontro la celda con %r" % marcador)
    return fuentes[-1]


def cargar_ambiente():
    """Carpeta temporal con los agentes + celdas del notebook ejecutadas en
    __main__ (como en Colab). Devuelve la instancia de TorneoPicasFijasUI."""
    carpeta = tempfile.mkdtemp(prefix="drive_picas_")
    for archivo in ARCHIVOS:
        shutil.copy(os.path.join(AQUI, archivo), carpeta)
    os.chdir(carpeta)
    _instalar_sustitutos()
    principal = sys.modules["__main__"].__dict__
    exec(compile(_celda("class interfazAgente"), "notebook[interfaz]", "exec"), principal)
    codigo = _celda("class TorneoPicasFijasUI").replace("UI = TorneoPicasFijasUI()", "")
    exec(compile(codigo, "notebook[ambiente]", "exec"), principal)
    with contextlib.redirect_stdout(io.StringIO()):
        return principal["TorneoPicasFijasUI"]()


# --------------------------------------------------------------------------- #
#  1) Carga del agente
# --------------------------------------------------------------------------- #
def verificar_carga():
    """El ambiente definitivo solo pide `compute`: NO exige heredar de
    `interfazAgente` (su escaner ni lo mira). Por eso aqui se comprueba el
    contrato de verdad y no la herencia."""
    global MI_AGENTE
    ui = cargar_ambiente()
    print("=" * 78)
    print(" 1. CARGA EN EL AMBIENTE (escanear_directorio, interfaz `compute`)")
    print("=" * 78)
    claves_mias = [k for k in ui.agentes_disponibles if k.endswith("(%s)" % AGENTE_PY)]
    MI_AGENTE = _clave_de_mi_agente(ui)
    clase = ui.agentes_disponibles.get(MI_AGENTE) if MI_AGENTE else None
    primero = None
    if clase is not None:
        try:
            primero = clase().compute([-1, -1])
        except Exception as e:
            primero = "EXCEPCION: %s" % e
    valido = (isinstance(primero, list) and len(primero) == 4
              and len(set(primero)) == 4
              and all(isinstance(d, int) and 0 <= d <= 9 for d in primero))
    checks = {
        "el ambiente detecta el agente": clase is not None,
        "una sola entrada en el desplegable": len(claves_mias) == 1,
        "tiene compute": clase is not None and hasattr(clase, "compute"),
        "se instancia sin argumentos": clase is not None,
        "compute([-1,-1]) da 4 digitos unicos 0-9": valido,
    }
    print("  entradas del agente en el desplegable: %s" % claves_mias)
    print("  primer intento: %s" % (primero,))
    for texto, ok in checks.items():
        print("  %-42s %s" % (texto, "OK" if ok else "FALLA"))
    return all(checks.values())


# --------------------------------------------------------------------------- #
#  2) Torneos con el boton "Torneo Masivo"
# --------------------------------------------------------------------------- #
_UI = None


def _ronda(args):
    """Una ronda = un torneo masivo de 1 ronda con semilla propia, para poder
    registrar la caida de un rival sin perder el resto de la estadistica."""
    global _UI
    rival, i = args
    if _UI is None:
        _UI = cargar_ambiente()
    ui = _UI
    ui.dd_agenteA.value = MI_AGENTE or _clave_de_mi_agente(ui)
    ui.dd_agenteB.value = rival
    ui.input_rondas.value = 1
    ui.input_semilla.value = "ronda-%d" % i
    ui.chk_visual_masivo.value = False
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ui.on_masivo(None)
    except Exception as e:
        return {"caida": type(e).__name__, "secreto": ui.secreto_juez}
    s = ui.stats
    return {
        "caida": None, "secreto": ui.secreto_juez,
        "vA": s["vA"], "vB": s["vB"], "empate": s["empates"],
        "turnos": ui.turno_actual, "errA": s["erroresA"],
        "tA": s["tiempoA"], "movsA": s["movsA"], "tB": s["tiempoB"], "movsB": s["movsB"],
    }


def torneos(rondas):
    print()
    print("=" * 78)
    print(" 2. TORNEO MASIVO: %s vs cada rival (%d rondas, secretos identicos)" % (MI_AGENTE.split()[0], rondas))
    print("=" * 78)
    print("  %-17s %6s %6s %6s %8s %8s %9s %9s %7s" % (
        "RIVAL", "GANO", "EMPATE", "PERDIO", "%GANADAS", "INVALID", "ms/t mio", "ms/t riv", "CAIDAS"))
    total_invalidos = 0
    with mp.Pool(max(1, min(12, os.cpu_count() or 1))) as pool:
        for rival in RIVALES:
            datos = pool.map(_ronda, [(rival, i) for i in range(rondas)], chunksize=4)
            ok = [d for d in datos if not d["caida"]]
            caidas = len(datos) - len(ok)
            g = sum(d["vA"] for d in ok)
            p = sum(d["vB"] for d in ok)
            e = sum(d["empate"] for d in ok)
            inval = sum(d["errA"] for d in ok)
            total_invalidos += inval
            ms_mio = 1000 * sum(d["tA"] for d in ok) / max(1, sum(d["movsA"] for d in ok))
            ms_riv = 1000 * sum(d["tB"] for d in ok) / max(1, sum(d["movsB"] for d in ok))
            print("  %-17s %6d %6d %6d %7.1f%% %8d %9.2f %9.2f %7d" % (
                rival.split()[0], g, e, p, 100.0 * g / max(1, len(ok)), inval, ms_mio, ms_riv, caidas))
            if caidas:
                ejemplo = next(d for d in datos if d["caida"])
                print("      el rival lanzo %s (p.ej. con el secreto %s); en el notebook eso detiene el torneo"
                      % (ejemplo["caida"], ejemplo["secreto"]))
    return total_invalidos


def main():
    rondas = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    ok = verificar_carga()
    invalidos = torneos(rondas)
    print()
    print("VEREDICTO: %s" % ("CONFORME" if ok and invalidos == 0 else "REVISAR"))


if __name__ == "__main__":
    main()
