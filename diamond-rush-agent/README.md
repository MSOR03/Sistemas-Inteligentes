# Diamond Rush Agent

Agente inteligente que juega **Diamond Rush** en
[minijuegos.com/juego/diamond-rush](https://www.minijuegos.com/juego/diamond-rush)
mirando la pantalla y pulsando las flechas del teclado, como lo haría una persona.

El agente:

1. **Percibe**: captura la pantalla, encuentra el juego y convierte la imagen en un
   tablero lógico (muros, diamantes, rocas, huecos, llaves, puertas, rejas, placas,
   púas, salida...).
2. **Planifica**: busca con A\* la secuencia de movimientos que recoge todos los
   diamantes y llega a la salida.
3. **Actúa**: envía las flechas y **comprueba en pantalla** que cada movimiento se
   realizó antes de enviar el siguiente.
4. **Se corrige**: si un movimiento no tiene efecto, o si al pisar una placa la reja
   que se abre no es la esperada, aprende de ello, vuelve a leer el tablero y
   replanifica.

No modifica el juego, no lee la página (nada de *web scraping* ni del DOM) y no usa
una versión descargada: solo píxeles de la pantalla y teclas simuladas.

> La explicación completa del algoritmo y la arquitectura está en
> [docs/GUIA.md](docs/GUIA.md).

---

## Requisitos

| | |
|---|---|
| Python | 3.11 a 3.13 (probado con 3.13.13) |
| Sistema | Windows 10/11 (probado). Linux con X11 y macOS deberían funcionar (ver abajo). |
| Navegador | Cualquiera; probado con Chrome |
| Pantalla | El juego completo visible en el **monitor principal** |

---

## Instalación

Desde la carpeta `diamond-rush-agent`:

**Windows (PowerShell o Git Bash)**

```bash
python -m venv .venv
.venv\Scripts\activate          # Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Comprobar que todo quedó bien (no necesita el juego abierto):

```bash
cd src
python test_solver.py
```

Debe terminar con `Todo bien.`

### Notas por sistema

- **Windows**: con la escala de pantalla al 125 % o 150 % no hay que hacer nada; el
  agente busca el juego a cualquier tamaño.
- **Linux**: necesita una sesión **X11** (en Wayland las capturas salen negras).
  `python-xlib` se instala solo en Linux.
- **macOS**: hay que darle a la terminal permiso de *Grabación de pantalla* y de
  *Accesibilidad* (Ajustes del Sistema → Privacidad y seguridad).

---

## Preparar el juego

1. Abrir el juego en el navegador y dejarlo en el nivel que se va a jugar.
2. Que el **juego se vea entero**: sin la barra de anuncios encima, sin otras ventanas
   delante. Si no cabe, alejar el zoom del navegador (Ctrl + −); el agente se adapta.
3. Que esté en el **monitor principal**.
4. Al correr el agente, **hacer clic sobre el juego** durante la cuenta regresiva
   (4 s) para que reciba las teclas. Después no tocar el mouse ni el teclado.

Para detener el agente en cualquier momento: **llevar el mouse a una esquina de la
pantalla** (*fail-safe* de PyAutoGUI) o Ctrl + C en la terminal.

---

## Uso

Todos los comandos se corren desde `src/` con el entorno virtual activado.

```bash
cd src

# 1. Ensayo: lee el tablero y muestra el plan, SIN pulsar teclas
python play.py --dry-run

# 2. Jugar el nivel que está en pantalla
python play.py

# Jugar 3 niveles seguidos
python play.py --levels 3
```

Al terminar cada nivel, el agente muestra cuánto tardó (ejemplo):

```
Plan (22 movimientos, calculado en 0.04 s): right x5, down x3, ...

=== Nivel 1 terminado ===
  Lectura y plan:     0.11 s
  Teclado:            6.80 s (22 movimientos, 0.31 s por movimiento)
  Replanificaciones: 0
  Total:              6.91 s
```

- **Lectura y plan**: capturar la pantalla, leer el tablero y buscar el plan (sumando
  las replanificaciones).
- **Teclado**: enviar los movimientos y comprobar cada uno en pantalla.
- **Total**: desde que empezó a mirar el nivel hasta enviar el último movimiento (la
  entrada a la salida).

Si el nivel no se termina, se muestra igual, como `sin terminar`. Con `--levels N`
se agrega un resumen de todos los niveles.

### `play.py`: el agente

| Opción | Por defecto | Qué hace |
|---|---|---|
| *(ninguna)* | | Juega el nivel que está en pantalla. |
| `--dry-run` | | Captura, lee el tablero y planifica, pero no envía teclas. Para revisar que todo se ve bien antes de jugar. |
| `--image RUTA` | | Resuelve una imagen guardada del área del juego (por ejemplo `../screenshots/last_game.png`). No necesita el juego abierto. |
| `--levels N` | `DR_LEVELS` (1) | Cantidad de niveles seguidos a jugar. |
| `--countdown S` | `DR_COUNTDOWN` (4) | Segundos de espera al empezar, para hacer clic en el juego. |
| `--delay S` | `DR_STEP_DELAY` (0.05) | Pausa extra después de cada movimiento ya comprobado. Subirla si la máquina es lenta y el agente se adelanta al juego. |
| `--replans N` | `DR_REPLANS` (6) | Veces que replanifica en un nivel si un movimiento falla, antes de rendirse. |
| `--level-wait S` | `DR_LEVEL_WAIT` (4) | Segundos de espera entre un nivel y el siguiente (animación de cambio de nivel). |
| `--explore` | apagado | Si no se ve la salida, recorre el nivel para descubrir el resto (ver [GUIA](docs/GUIA.md#9-exploración-opcional)). Puede empujar rocas: usar solo si el nivel realmente no cabe en pantalla. |
| `--explore-moves N` | `400` | Movimientos máximos de cada recorrido de exploración. |

Los valores por defecto salen de la configuración (siguiente sección); una opción
escrita en el comando manda sobre ella.

### Configuración: velocidad y tiempos (`.env`)

Los tiempos del agente se cambian sin tocar el código:

```bash
cp .env.example .env      # Windows (PowerShell): copy .env.example .env
```

y editar `.env` (en la carpeta `diamond-rush-agent`). Cada ajuste está explicado en
`.env.example`; una línea borrada o comentada usa el valor por defecto del código.

`.env.example` trae el **perfil rápido** (sin pausas extra, mirando la pantalla más
seguido y manteniendo la flecha en los tramos rectos). Los valores por defecto del
código, que se usan si no hay `.env`, son los conservadores de la tabla. En simulación,
el perfil rápido baja el tiempo de teclado de ~0.20 s a ~0.13 s por movimiento; en el
juego real conviene comparar el `s por movimiento` del resumen.

| Variable | Por defecto | Qué controla |
|---|---|---|
| `DR_STEP_DELAY` | 0.05 (rápido: 0) | Pausa extra tras cada movimiento comprobado. **El principal ajuste de velocidad.** |
| `DR_KEY_HOLD` | 0.06 (rápido: 0.05) | Tiempo que se mantiene pulsada cada flecha. |
| `DR_POLL_INTERVAL` | 0.03 (rápido: 0.01) | Cada cuánto se mira la pantalla al esperar un movimiento. |
| `DR_MOVE_TIMEOUT` | 1.0 (rápido: 0.7) | Espera máxima a que el jugador cambie de casilla antes de volver a pulsar. |
| `DR_SETTLE_TIMEOUT` | 1.0 | Espera máxima a que termine una animación. |
| `DR_MAX_PRESSES` | 3 | Pulsaciones antes de dar un movimiento por fallido. |
| `DR_STILL_TIME` | 0.1 | Tiempo sin cambios en pantalla para dar una animación por terminada. **No bajarlo**: con menos, el agente puede pulsar en mitad de un empujón y perder la cuenta del jugador. |
| `DR_GATE_ANIMATION` | 0.4 | Tiempo que tarda una reja en abrirse o cerrarse. |
| `DR_HOLD_KEYS` | 0 (rápido: 1) | `1`: mantener la flecha pulsada en los tramos rectos que terminan contra un muro, como una persona (ver abajo). |
| `DR_HOLD_MIN_RUN` | 2 | Casillas mínimas de un tramo para mantener la flecha. |
| `DR_COUNTDOWN` | 4 (rápido: 3) | Segundos para hacer clic en el juego. |
| `DR_LEVEL_WAIT` | 4 (rápido: 3) | Espera entre niveles. Subirla si el nivel siguiente se lee mal por la animación de entrada. |
| `DR_REPLANS` | 6 | Replanificaciones por nivel. |
| `DR_LEVELS` | 1 | Niveles seguidos. |

También se pueden poner como variables de entorno, que mandan sobre `.env`:

```bash
DR_STEP_DELAY=0.02 python play.py              # Git Bash / Linux / macOS
$env:DR_STEP_DELAY="0.02"; python play.py      # PowerShell
```

Prioridad: opción del comando > variable de entorno > `.env` > valor por defecto. Un
valor mal escrito no detiene al agente: avisa y usa el valor por defecto. `.env` no se
sube a git, así cada máquina tiene el suyo.

**Ir más rápido sin perder movimientos**: bajar primero `DR_STEP_DELAY` (por ejemplo
a 0) y mirar el `s por movimiento` del resumen. Cada movimiento se comprueba en
pantalla antes del siguiente, así que ir más rápido no hace que el agente se salte
pasos; si empiezan a aparecer movimientos `no tuvo efecto`, volver a subirlo.

`DR_MOVE_TIMEOUT` y `DR_SETTLE_TIMEOUT` son esperas **máximas**: solo se agotan cuando
algo falla, así que bajarlos no acelera los movimientos normales (y no pueden ser
menores que 0.1).

**Mantener la flecha pulsada (`DR_HOLD_KEYS=1`)**: normalmente el agente pulsa una
vez por casilla y espera a ver al jugador llegar, lo que deja una pequeña pausa entre
casillas. Con esta opción, en un tramo recto el agente mantiene la flecha pulsada y la
suelta al llegar, como una persona. Solo lo hace si el tramo es solo piso o diamantes
y **termina contra un muro**: así, si suelta la tecla un poco tarde, el jugador choca
con el muro en lugar de dar un paso de más. Al soltar, comprueba en pantalla hasta
dónde llegó el jugador. Si el juego no lo mueve con la tecla pulsada, el agente lo
nota en el primer tramo y sigue con una pulsación por casilla. Conviene probarlo
primero en un nivel fácil.

### Otras herramientas

| Comando | Qué hace |
|---|---|
| `python test_solver.py` | Pruebas de regresión: lee las capturas de `dataset/raw/`, compara cada tablero con el etiquetado a mano y comprueba que el planificador encuentra solución (también para los niveles 13 y 20, solo con el tablero). Devuelve código 1 si algo falla. |
| `python dataset_collector.py --level N` | Captura el juego en pantalla y guarda la imagen y todas sus celdas en `dataset/raw/level_NNN/`. Sirve para crear templates nuevos o agregar un nivel a las pruebas. |
| `python create_template.py` | Vuelve a crear el ancla (`assets/templates/game_anchor.png`): se selecciona con el mouse el engranaje del juego. Solo hace falta si el juego cambia de aspecto. |

Los archivos `test_*.py` restantes (`test_cells.py`, `test_grid_detection.py`, ...) son
experimentos de las primeras etapas del proyecto; no se usan para jugar.

---

## Qué archivos genera

| Archivo | Contenido |
|---|---|
| `screenshots/last_game.png` | Última área del juego leída. Es lo primero que hay que mirar si el tablero sale mal. |
| `screenshots/last_screen.png` | Pantalla completa de esa misma lectura. |
| `screenshots/debug_no_game.png` | Lo que se capturó cuando no se encontró el juego. |
| `screenshots/last_map.png` | Mapa armado al explorar (solo con `--explore`). |
| `dataset/unknown/*.png` | Celdas que no se reconocieron (se tratan como obstáculo). |
| `knowledge.json` | Lo aprendido jugando: qué placa **no** abre qué reja, por nivel. Se reutiliza en partidas siguientes. |

---

## Agregar un objeto nuevo (template)

Si un nivel trae algo que el agente no conoce (así pasó con la estatua del nivel 20):

1. Correr `python play.py --dry-run`. Las celdas desconocidas aparecen como `?` y se
   guardan en `dataset/unknown/`. Si el objeto se parece a un muro, puede salir como
   `#`: revisar `screenshots/last_game.png`.
2. Copiar el recorte a `assets/templates/cells/` con el **prefijo de su clase** y un
   número nuevo: el prefijo define qué es.

   | Prefijo | Símbolo | Objeto |
   |---|---|---|
   | `wall_` | `#` | Muro |
   | `floor_` | `.` | Piso |
   | `diamond_` | `D` | Diamante |
   | `player_` | `P` | Jugador |
   | `exit_` | `E` | Salida / meta (reja de salida, estatua) |
   | `rock_` | `R` | Roca |
   | `key_` | `K` | Llave |
   | `door_` | `G` | Puerta con cerradura |
   | `gate_` | `B` | Reja que abre una placa |
   | `plate_` | `O` | Placa de presión |
   | `lava_` | `L` | Lava |
   | `spike_` | `S` | Trampa de púas |
   | `filled_` | `.` | Hueco ya rellenado con una roca |

   Los huecos (`H`) y las púas levantadas (`X`) no usan templates: se detectan por
   color.

   Si no hay recorte en `dataset/unknown/`, se puede sacar con
   `python dataset_collector.py --level N`, que guarda cada celda por separado.
3. Volver a correr `--dry-run` y comprobar el tablero.

---

## Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `ERROR: no se encontró Diamond Rush en pantalla` | El juego no se ve, está tapado o en otro monitor | Dejarlo visible en el monitor principal. Revisar `screenshots/debug_no_game.png`. |
| `El movimiento 1 de N (...) no tuvo efecto` | El juego no tiene el foco, o el tablero se leyó mal | Hacer clic en el juego durante la cuenta regresiva. Revisar el tablero impreso contra `last_game.png`. |
| `No se ve la salida` | La salida es un objeto sin template | Agregar el template (sección anterior). |
| `No se encontró solución` | Una celda mal leída, o un nivel fuera del alcance del planificador | Comparar el tablero impreso con `last_game.png`; corregir con un template. |
| `AVISO: N celdas no reconocidas` | Objetos sin template | Ver `dataset/unknown/` y agregar el template. |
| El agente se adelanta a la animación | Máquina lenta | Subir `DR_STEP_DELAY` en `.env` o `--delay` (por ejemplo `0.15`). |
| Algunas flechas no se registran | Pulsación demasiado corta | Subir `DR_KEY_HOLD` a `0.1`. |
| Tildes raras en la terminal | Codificación de la consola | Solo es visual; el agente sigue funcionando. |

---

## Estructura

```
diamond-rush-agent/
├── README.md              este archivo
├── docs/GUIA.md           algoritmo, arquitectura y decisiones de diseño
├── requirements.txt
├── .env.example           ajustes de velocidad y tiempos (copiar como .env)
├── knowledge.json         lo aprendido (rejas/placas) por nivel
├── assets/templates/
│   ├── game_anchor.png    engranaje: ubica el juego en la pantalla
│   ├── walkthrough.png    botón WALKTHROUGH (solo para --explore)
│   └── cells/             un template por tipo de celda
├── dataset/
│   ├── raw/level_NNN/     capturas de niveles (pruebas y templates)
│   └── unknown/           celdas no reconocidas
├── screenshots/           capturas de diagnóstico
└── src/
    ├── play.py            punto de entrada: ciclo percibir-planificar-actuar
    ├── config.py          ajustes desde .env / variables de entorno
    ├── agent.py           agente: percepción + plan + aprendizaje de rejas
    ├── capture.py         capturas de pantalla
    ├── game_detector.py   ubicar el juego (ancla, escala) y recortarlo
    ├── level_reader.py    imagen → tablero lógico
    ├── cell_classifier.py carga de templates
    ├── board_classifier.py geometría de la cuadrícula
    ├── solver.py          planificador A*
    ├── controller.py      teclado y comprobación de cada movimiento
    ├── image_io.py        leer/escribir imágenes con cualquier ruta
    ├── stitcher.py        mapa de varias capturas (--explore)
    ├── explorer.py        exploración (--explore)
    └── test_solver.py     pruebas de regresión
```
