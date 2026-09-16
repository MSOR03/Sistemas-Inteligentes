# Agente para la Competencia de Picas y Fijas

Archivo a entregar: **`Picas_Y_Fijas_Agent_Compute.py`** (un solo archivo, solo
librería estándar de Python). Es el que cumple la interfaz `compute` del
ambiente definitivo; `Picas_Y_Fijas_Agent.py` se conserva para el ambiente
viejo y porque es sobre él que escribe `generar_arbol.py`.

Ambiente oficial: **`Ambientes/Ambiente_Definitivo.ipynb`** (juez central).
La explicación completa del ambiente y del agente está en
[`explanation.md`](explanation.md).

---

## Archivos

| Archivo | Para qué sirve | ¿Se entrega? |
|---|---|---|
| `Picas_Y_Fijas_Agent_Compute.py` | El agente (interfaz `compute`) | **Sí** |
| `Picas_Y_Fijas_Agent.py` | Versión vieja (interfaz `start`/`try_attempt`/`feedBack`) | No |
| `Ambientes/Ambiente_Definitivo.ipynb` | Ambiente del torneo (sin modificar) | No |
| `explanation.md` | Cómo funcionan el ambiente y el agente | No |
| `generar_arbol.py` | Recalcula el árbol de decisión y lo escribe dentro del agente | No |
| `test_nuevo_ambiente.py` | Ejecuta el código real del notebook contra 6 rivales | No |
| `rivales_nuevo_ambiente.py` | Agentes de `examples/` adaptados a la interfaz nueva | No |
| `rival_real.py` | Agente real de un compañero (rival de prueba) | No |
| `examples/` | Agentes y ambiente de ejemplo originales | No |

---

## Cómo es el juego ahora

- En cada ronda el **juez** genera un secreto (`random.sample(range(10), 4)`,
  el **0 inicial es válido**).
- Los dos agentes adivinan **el mismo secreto**, cada uno por su lado, y el
  juez les da `[picas, fijas]`.
- Gana quien llega a `[0, 4]` en menos turnos; el mismo turno es empate.
- Es una **carrera de velocidad**: ganar más rondas = resolver en menos turnos.

## Interfaz que cumple el agente

El ambiente definitivo habla por **un solo método**:

```python
intento = agente.compute([picas, fijas])
```

| | |
|---|---|
| Entrada | `[picas, fijas]` del turno anterior; `[-1, -1]` en el primer turno de la ronda |
| Salida | `list` de 4 `int` únicos 0–9 (el 0 inicial es válido) |

- `compute` **no tiene ciclos dentro**: el ciclo de turnos y el de rondas los
  lleva el ambiente. Cada llamada es un turno.
- El ambiente crea **una instancia nueva por ronda**; además el agente se
  reinicia solo al recibir `[-1, -1]`, así que tampoco se rompe si se reutiliza.
- El módulo exporta **una sola clase** (una sola entrada en el desplegable) y
  `compute` nunca lanza excepción: ante cualquier fallo devuelve una jugada
  válida.
- El agente **no guarda nada entre rondas**: cada ronda empieza de cero, como
  exige el reglamento.

---

## Cómo se usa en el notebook

1. Ejecuta la celda de `interfazAgente` y la de Drive.
2. **El escáner busca archivos en la carpeta de trabajo (`os.listdir('.')`),
   no en la ruta de Drive.** Antes de la celda del ambiente ejecuta
   `import os; os.chdir(ruta_carpeta)`, o copia el `.py` a `/content`.
3. Ejecuta la celda del ambiente, elige
   `AgenteDJS (Picas_Y_Fijas_Agent_Compute.py)` y pulsa **⚖️ Torneo Masivo**.

Pruebas locales:

```bash
python3 Picas_Y_Fijas_Agent_Compute.py   # juega los 5040 secretos posibles
python3 test_nuevo_ambiente.py 1000   # código real del notebook vs 6 rivales
python3 generar_arbol.py              # recalcula el árbol (tarda minutos)
```

---

## Estrategia (resumen)

1. **Apertura fija `0123`** (todas las aperturas son equivalentes: renombrar
   los dígitos convierte una en otra).
2. **Árbol de decisión precalculado**, si lo hay. Hoy `ARBOL_TEXTO` está
   **vacío** y el agente juega solo con la búsqueda del punto 4; la maquinaria
   del árbol sigue en el archivo para poder pegar un bloque cuando se quiera.
   Lo genera `generar_arbol.py`.
3. **1–2 candidatos**: juega un candidato (gana ya o en el turno siguiente).
4. **Búsqueda en línea** sobre las 5040 jugadas: elige la que **menos turnos
   costará**, sumando `|clase| * T(|clase|)` sobre las clases de respuesta.

### Por qué turnos y no candidatos

`T(m)` son los turnos que faltan en promedio cuando quedan `m` candidatos. Se
midió jugando 500 rondas y ajustando `T(m) ≈ A + B·ln(m)`, con `T(1)=1` y
`T(2)=1.5` exactos.

Antes se minimizaba el número esperado de **candidatos** restantes (la suma de
cuadrados de los tamaños de clase). Eso trata una clase de 40 como cuatro veces
peor que una de 20, cuando en turnos reales solo es ~0.3 peor. Puntuar por
turnos corrige esa escala.

> ⚠️ `T` tiene que ser **no decreciente**, y el código lo fuerza. Si `T` bajara
> al crecer `m`, partir un grupo podría parecer peor que no partirlo: con
> `T(3) < T(2)` el agente llega a gastar 20 turnos con 3 candidatos sobre la
> mesa sin probar ninguno, y pierde la ronda.

Los candidatos se guardan como un entero de 5040 bits; filtrar por una
respuesta son unas pocas operaciones `&`. Para **puntuar** jugadas el universo
se comprime a los candidatos vivos: el bitset general ocupa 629 bytes siempre,
queden 4 candidatos o 5000, así que comprimirlo hace el barrido el doble de
rápido sin cambiar ni una decisión.

---

## Rendimiento medido

Los 5040 secretos, exhaustivo. El agente es determinista dado el secreto, así
que esto **no es una muestra**: es el valor exacto.

| | turnos | peor | distribución |
|---|---|---|---|
| **Este agente** | **5.2397** | 8 | `{1:1, 2:7, 3:74, 4:611, 5:2457, 6:1789, 7:100, 8:1}` |
| Puntuación anterior (`Σ\|S_c\|²`) | 5.2688 | 7 | `{1:1, 2:4, 3:59, 4:574, 5:2425, 6:1891, 7:86}` |
| Minimax (grupo mayor) | 5.3429 | 7 | `{1:1, 2:3, 3:43, 4:565, 5:2217, 6:2030, 7:181}` |
| Árbol generado (consciente de rivales) | 5.2321 | 8 | — |

**Velocidad:** 66 ms por ronda, 12.6 ms por jugada de media y 49.5 ms la peor.
Antes del barrido comprimido eran 126 ms por ronda, con decisiones idénticas.

### Cara a cara (5040 secretos, mismo secreto para los dos, gana quien tarde menos)

| Rival | gana | empata | pierde | turnos del rival |
|---|---|---|---|---|
| `AgenteLexicografico` | 40.4% | 40.9% | 18.7% | 5.560 |
| `AgenteJuan` | 35.3% | 38.6% | 26.1% | 5.354 |
| `AgenteCrucetero` | 32.2% | 50.1% | 17.7% | 5.408 |
| `AgenteEntropico` | 13.5% | 76.4% | 10.1% | 5.281 |

> ⚠️ **Mira la columna de empates.** Este agente tiene mejor promedio que los
> cuatro rivales y aun así contra `AgenteEntropico` solo gana el 13.5%, porque
> **empata el 76.4%**. Los turnos son números enteros y están muy
> correlacionados entre dos agentes buenos sobre el mismo secreto: bajar el
> promedio mueve el resultado *dentro* del empate, no fuera. Para ganar más
> rondas hace falta una política que rompa el empate a favor, que es lo que
> optimiza el árbol de `generar_arbol.py` (llega a 47.5 / 40.0 / 38.2 / 32.2%
> contra estos mismos cuatro), a cambio de estar ajustado a esos rivales
> concretos.

### En el ambiente real (última celda del notebook, 200 rondas por rival)

- Detectado con **una sola entrada** en el desplegable.
- **0 intentos inválidos** en 400 rondas.
- vs `AgenteEstrategico`: gana 40.5%, empata 42.5%, pierde 17.0%.
- vs `AgenteAleatorio`: gana 100%.

> Los rivales de `rival_real.py` y `rivales_nuevo_ambiente.py` usan la interfaz
> vieja (`start`/`try_attempt`/`feedBack`), y el ambiente definitivo solo
> registra clases con `compute`, así que no aparecen en su desplegable. Contra
> ellos se mide simulando las partidas (tabla de arriba).

### Ajuste del peor caso

`A_TURNOS` y `B_TURNOS` deciden el equilibrio entre promedio y peor caso:

| `A_TURNOS` | `B_TURNOS` | promedio | peor | rondas de 8 turnos |
|---|---|---|---|---|
| **1.1078** | **0.6200** | **5.2397** | 8 | 1 de 5040 |
| 1.800 | 0.350 | 5.2581 | 7 | ninguna |

Ambos mejoran el 5.2688 de partida. Se eligió el primero por promedio; el
segundo garantiza techo de 7 turnos.
