# Agente para la Competencia de Picas y Fijas

Archivo a entregar: **`Picas_Y_Fijas_Agent.py`** (un solo archivo, sin dependencias
externas: solo la librería estándar de Python, no requiere `numpy`).

---

## 1. Cumplimiento del reglamento

El ambiente valida estructura en cuatro puntos. El agente los cumple todos de
forma explícita:

| Regla del ambiente | Qué exige | Qué devuelve el agente |
|---|---|---|
| `Ambiente.setup` | Heredar de `interfazAgente` | Implementa los 4 métodos y, si el ambiente definió la interfaz como ABC, se registra como subclase virtual (`issubclass` e `isinstance` dan `True`) |
| `Ambiente.initRound` → `start()` | Secreto de 4 dígitos **enteros únicos** 0–9 | `self.secret` es una `list` de 4 `int` únicos, aceptada por `es_intento_valido` |
| `Ambiente.getAttempts` → `try` | `list` de 4 `int` únicos 0–9 | `[d0, d1, d2, d3]`, siempre válida, nunca repite un intento |
| `Ambiente.evaluateAttempts` → `discover` | `list` de 2 `int` `[P, F]` con `P + F ≤ 4` | Evaluación **honesta** contra el secreto declarado |
| `Ambiente.dispatchFeedback` → `feedBack` | Recibe `[P, F]` | Actualiza la base de conocimiento |

Dos decisiones tomadas explícitamente por cumplimiento:

- **`discover` nunca miente.** La respuesta es siempre la evaluación real del
  secreto generado en `start()`. Existen agentes de ejemplo que responden sin
  fijar secreto para alargar la partida del rival; esa táctica contradice el
  espíritu del reglamento (*"el estado del número generado"* es verificable) y
  expone a perder la ronda por infracción. Toda la fuerza del agente está en el
  lado de la búsqueda, no en la respuesta.
- **El secreto es uniformemente aleatorio entre las 4536 combinaciones que no
  empiezan en 0** (muestreo por rechazo). El reglamento habla de un "número de
  cuatro cifras" y el agente real de un compañero (`rival_real.py`) busca en
  `range(1023, 9876)`: con un secreto como `0123` su lista de candidatos queda
  vacía, `random.choice` lanza `IndexError` y, como el ambiente no protege las
  llamadas, se aborta el torneo entero (≈21% de los torneos medidos).

`try` es palabra reservada de Python, así que no puede declararse con `def`. El
agente expone **ambas** vías que contempla el ambiente: el método `try_attempt`
y el atributo literal `try` (instalado con `setattr`), de modo que
`invocar_try` funciona por cualquiera de sus dos ramas.

---

## 2. Cómo se usa

Sube `Picas_Y_Fijas_Agent.py` a la carpeta de Drive de la competencia. En el
notebook del ambiente:

```python
from Picas_Y_Fijas_Agent import AgentePicasFijas

agente1 = AgentePicasFijas()
```

El módulo además exporta los alias `Agente`, `AgenteClase1`, `AgenteClase2`,
`AgentePicasYFijas` y `TuAgente`, todos apuntando a la misma clase, para que
cualquier forma de importación del ambiente funcione sin editar el archivo.

Para probarlo localmente:

```bash
python3 Picas_Y_Fijas_Agent.py   # autoprueba: distribución de turnos y tiempos
python3 test_ambiente.py 300     # ejecuta la celda REAL de Ambiente.ipynb (interfaz + torneos)
python3 validar.py 800 100       # distribución de turnos + rivales de examples/
python3 test_rival_real.py 300   # contra el agente real del compañero
```

---

## 3. Cómo juega

### Representación

El espacio del juego son las 5040 permutaciones de 4 dígitos distintos. Un
conjunto de candidatos se guarda como un **entero de 5040 bits**, y las
particiones por respuesta se calculan con operaciones de bits sobre máscaras
precalculadas por `(posición, dígito)` y por `dígito presente`. Eso es lo que
permite evaluar **las 5040 jugadas posibles en cada turno** —no solo las
candidatas— en milisegundos y en Python puro.

### Elección de jugada

Cada turno se filtra el conjunto de candidatos consistentes con toda la
historia y se elige la jugada que minimiza el número esperado de candidatos
supervivientes, excluyendo la clase ganadora `[0,4]` (ahí el juego termina).
Los desempates son, en orden: menor peor caso, y preferir una jugada que además
sea candidata, porque solo esas pueden ganar en el turno actual.

**Prior de cero inicial.** Mientras quede algún candidato que no empiece en 0,
la búsqueda se hace solo sobre esos (muchos rivales generan "números de 4
cifras" sin cero inicial). Si la evidencia los descarta, vuelve sola a las 5040.
Se desactiva si se detecta un rival que miente, porque ese rival se refugiaría
en la parte del espacio que el agente no está partiendo.

### Modelo del rival

Cada respuesta honesta que el agente da es información que el rival recibe.
Replicando ese mismo filtrado, el agente sabe en todo momento **cuánta
incertidumbre le queda al rival sobre el secreto propio**. Con eso ajusta el
riesgo: si el rival está a punto de resolver y no está peor posicionado,
explorar regala el turno, así que el agente juega solo candidatos, que son los
únicos con probabilidad de ganar ya. Un empate vale más que una derrota.

### Defensas

- **Rival adversarial.** Si el rival responde sistemáticamente enviando al
  agente a la clase de respuesta más grande —firma de un agente que no fija
  secreto y responde para maximizar la incertidumbre— el criterio cambia a
  minimax puro, que es la respuesta óptima contra ese comportamiento.
- **Respuestas contradictorias.** Si el conjunto de candidatos queda vacío
  porque el rival respondió de forma inconsistente, se descartan las
  restricciones más antiguas hasta recuperar un conjunto viable, en lugar de
  reiniciar la búsqueda desde cero.
- **Robustez.** Ningún método público puede lanzar una excepción: todos tienen
  respaldo seguro. `discover` acepta el intento como lista, tupla, cadena o
  entero. Nunca se repite un intento ya jugado, así que el agente no puede
  entrar en un bucle aunque el ambiente omita la retroalimentación.
- **Secreto impredecible.** Se genera con un generador propio sembrado desde
  `os.urandom`, de modo que otro agente no puede predecirlo manipulando
  `random.seed()` en el proceso compartido.

---

## 4. Rendimiento medido

Medido con la versión actual (el secreto usa `os.urandom`, así que cada
ejecución varía unos ±4 puntos porcentuales).

**En solitario** (`validar.py`, 800 partidas, secreto uniforme de 5040):
promedio 5.29 turnos, peor caso 7, P(≤5 turnos) 0.61. Turno más lento: ~50 ms.

**Contra `rival_real.py`, con el código real del notebook** (600 torneos a 3 rondas):

| Versión | Torneos abortados por caída del rival | Puntos en torneos limpios | Rondas G/P |
|---|---|---|---|
| Antes (secreto con 0 inicial, sin prior) | 130 / 600 | 57.2% | 530 / 408 |
| Ahora | **0 / 600** | **63.2%** | **720 / 468** |

**Contra los rivales de `examples/`** (400 rondas, puntos = G + ½E):

| Rival | Antes | Ahora |
|---|---|---|
| Consistente | 57.8% | 59.6% |
| Entrópico | 49.5% | 51.6% |
| Minimax | 48.9% | 53.8% |
| Tramposo (miente, no fija secreto) | 30.9% | 36.9% |
| Aleatorio | 100% | 100% |

Infracciones reglamentarias del agente en todas las pruebas: **0**.
