import os
from pathlib import Path


# Ajustes de velocidad y tiempos del agente que se pueden cambiar
# sin tocar el código: en el archivo .env de la raíz del proyecto
# (ver .env.example) o como variables de entorno, que mandan
# sobre el archivo. Las opciones de play.py (--delay, ...)
# mandan sobre ambos.
#
# Un valor mal escrito no detiene al agente: se avisa y se usa
# el valor por defecto.


PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_FILE = PROJECT_ROOT / ".env"


def read_env_file(path=ENV_FILE):
    """
    Lee líneas NOMBRE=valor; ignora vacías y comentarios (#).
    """

    values = {}

    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values

    for number, line in enumerate(lines, 1):

        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            print(f"AVISO: {path}, línea {number}: falta '=', la ignoro.")
            continue

        name, value = line.split("=", 1)

        # Un comentario al final de la línea: DR_X=1  # nota
        value = value.split(" #", 1)[0].strip().strip("\"'")

        values[name.strip()] = value

    return values


_file_values = read_env_file()


def setting(name, default, kind=float, minimum=0):
    """
    Valor del ajuste name: variable de entorno, luego .env,
    luego default.
    """

    raw = os.environ.get(name, _file_values.get(name))

    if raw is None or raw == "":
        return default

    try:
        value = kind(raw)
    except ValueError:
        print(f"AVISO: {name}={raw!r} no es válido; uso {default}.")
        return default

    if value < minimum:
        print(f"AVISO: {name}={raw!r} es menor que {minimum}; uso {default}.")
        return default

    return value


# ----------------------------------------------------
# Velocidad de los movimientos (controller.py)
# ----------------------------------------------------

# Segundos que se mantiene pulsada cada flecha.
KEY_HOLD = setting("DR_KEY_HOLD", 0.06)

# Pausa extra después de cada movimiento ya comprobado en
# pantalla. Es lo primero a subir si la máquina es lenta y el
# agente se adelanta al juego, o a bajar para ir más rápido.
STEP_DELAY = setting("DR_STEP_DELAY", 0.05)

# Cada cuánto se mira la pantalla mientras se espera un movimiento.
POLL_INTERVAL = setting("DR_POLL_INTERVAL", 0.03, minimum=0.005)

# Segundos que se espera a que el jugador cambie de casilla
# antes de volver a pulsar la flecha.
MOVE_TIMEOUT = setting("DR_MOVE_TIMEOUT", 1.0, minimum=0.1)

# Segundos máximos esperando a que termine una animación
# (empujar una roca, abrir una puerta).
SETTLE_TIMEOUT = setting("DR_SETTLE_TIMEOUT", 1.0, minimum=0.1)

# Veces que se pulsa una flecha antes de dar el movimiento por fallido.
MAX_PRESSES = setting("DR_MAX_PRESSES", 3, int, minimum=1)

# Segundos que la imagen tiene que quedarse sin cambios para dar
# una animación por terminada. El juego dibuja por cuadros: dos
# capturas muy seguidas pueden caer en el mismo cuadro a mitad de
# una animación y parecer quietas. Si se pulsa la flecha siguiente
# en ese momento, el juego la ignora y el agente pierde la cuenta
# de dónde está el jugador (pasó en el nivel 19).
STILL_TIME = setting("DR_STILL_TIME", 0.1, minimum=0.03)

# Segundos que tarda una reja en abrirse o cerrarse: se esperan
# antes de mirarla, o se aprende algo falso.
GATE_ANIMATION = setting("DR_GATE_ANIMATION", 0.4)

# 1: en los tramos rectos que terminan contra un muro, mantener la
# flecha pulsada como una persona en lugar de pulsarla una vez por
# casilla. 0: siempre una pulsación por casilla.
HOLD_KEYS = setting("DR_HOLD_KEYS", 0, int)

# Casillas mínimas de un tramo para mantener la flecha pulsada.
HOLD_MIN_RUN = setting("DR_HOLD_MIN_RUN", 2, int, minimum=2)


# ----------------------------------------------------
# Partida (play.py)
# ----------------------------------------------------

# Segundos para hacer clic en el juego antes de empezar.
COUNTDOWN = setting("DR_COUNTDOWN", 4.0)

# Segundos de espera entre un nivel y el siguiente.
LEVEL_WAIT = setting("DR_LEVEL_WAIT", 4.0)

# Veces que se replanifica en un nivel si un movimiento falla.
REPLANS = setting("DR_REPLANS", 6, int)

# Niveles seguidos a jugar.
LEVELS = setting("DR_LEVELS", 1, int, minimum=1)
