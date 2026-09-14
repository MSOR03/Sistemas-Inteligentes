# Agente para la Competencia de Picas y Fijas

Archivo a entregar: **`Picas_Y_Fijas_Agent.py`** (un solo archivo, solo librería
estándar de Python).

Ambiente oficial: **`Ambientes/Ambiente_Definitivo.ipynb`** (juez central).
La explicación completa del ambiente y del agente está en
[`explanation.md`](explanation.md).

---

## Archivos

| Archivo | Para qué sirve | ¿Se entrega? |
|---|---|---|
| `Picas_Y_Fijas_Agent.py` | El agente | **Sí** |
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

| Ambiente | Agente |
|---|---|
| `interfazAgente.start()` | Resetea lo aprendido (el ambiente crea un agente nuevo por ronda) |
| `interfazAgente.try_attempt()` | `list` de 4 `int` únicos 0–9, nunca repetida |
| `interfazAgente.feedBack([P, F])` | Filtra los candidatos |
| `AdaptadorUniversal.receive_feedback(P, F)` | Alias de `feedBack` |

El agente **hereda de verdad** de `interfazAgente` si la celda de la interfaz se
ejecutó antes, exporta **una sola clase** (una sola entrada en el desplegable) y
ningún método puede lanzar excepción.

---

## Cómo se usa en el notebook

1. Ejecuta la celda de `interfazAgente` y la de Drive.
2. **El escáner busca archivos en la carpeta de trabajo (`os.listdir('.')`),
   no en la ruta de Drive.** Antes de la celda del ambiente ejecuta
   `import os; os.chdir(ruta_carpeta)`, o copia el `.py` a `/content`.
3. Ejecuta la celda del ambiente, elige
   `AgentePicasFijas (Picas_Y_Fijas_Agent.py)` y pulsa **⚖️ Torneo Masivo**.

Pruebas locales:

```bash
python3 Picas_Y_Fijas_Agent.py        # juega los 5040 secretos posibles
python3 test_nuevo_ambiente.py 1000   # código real del notebook vs 6 rivales
python3 generar_arbol.py              # recalcula el árbol (tarda minutos)
```

---

## Estrategia (resumen)

1. **Apertura fija `0123`** (todas las aperturas son equivalentes).
2. **Árbol de decisión precalculado**: para cada secuencia de respuestas guarda
   la jugada que minimiza el total de turnos sobre los 5040 secretos. Lo calcula
   `generar_arbol.py` con búsqueda exacta sobre las mejores jugadas de cada
   posición, memoria por bitset y poda por cota inferior.
3. **1–2 candidatos**: juega un candidato.
4. **Respaldo en línea** (solo si la partida sale del árbol): la jugada que
   minimiza el número esperado de candidatos restantes.

Los candidatos se guardan como un entero de 5040 bits; filtrar por una
respuesta son unas pocas operaciones `&`.

---

## Rendimiento medido

⟦RESULTADOS⟧
