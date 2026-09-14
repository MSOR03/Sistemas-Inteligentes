# Picas y Fijas: how the new environment and the agent work

This document explains two pieces of code:

1. **The environment**: `Ambientes/Ambiente_Definitivo.ipynb`, the notebook that runs the contest. It was not modified.
2. **The agent**: `Picas_Y_Fijas_Agent.py`, the file you submit.

Every number and example below comes from running the current code. The code uses Spanish names; section 8 is a small dictionary.

---

## Contents

1. [The game in this environment](#1-the-game-in-this-environment)
2. [The environment, cell by cell](#2-the-environment-cell-by-cell)
3. [What the environment means for strategy](#3-what-the-environment-means-for-strategy)
4. [The agent: map of the file](#4-the-agent-map-of-the-file)
5. [The agent: how it represents knowledge](#5-the-agent-how-it-represents-knowledge)
6. [The agent: strategy](#6-the-agent-strategy)
7. [A real round, turn by turn](#7-a-real-round-turn-by-turn)
8. [Dictionary of Spanish names](#8-dictionary-of-spanish-names)
9. [How to use and test it](#9-how-to-use-and-test-it)

---

## 1. The game in this environment

- **One secret per round.** A **central judge** picks it: 4 digits from 0–9 with no repeats, for example `[0, 5, 9, 8]`. **A leading 0 is valid**, and the judge uses one in 1 of every 10 rounds.
- **Both agents guess that same secret**, each on its own. An agent never sees the other agent's guesses or answers.
- **The judge scores every guess** as `[picas, fijas]`:
  - **fija**: a correct digit in the correct position;
  - **pica**: a correct digit in the wrong position.
- **Winning:** the agent that gets `[0, 4]` in fewer turns wins the round. Both on the same turn is a tie.

Example with secret `4271` and guess `1234`: the 2 is a fija, while 1 and 4 are picas, so the answer is `[2, 1]`.

There are 10 × 9 × 8 × 7 = **5040** possible secrets.

**What changed from the previous notebook:** agents no longer create a secret for the rival or score the rival's guesses (`discover`). The interface has only 3 methods.

---

## 2. The environment, cell by cell

| Cell | Type | Purpose |
|---|---|---|
| 0–5 | Markdown | Title, "Ambiente" rules and "Juego" rules |
| 6 | Code | `interfazAgente`: `start`, `try_attempt`, `feedBack` |
| 9 | Code | Mounts Google Drive and adds the contest folder to `sys.path` |
| 11 | Code | The environment: adapter, two example agents, and the tournament with its interface |

### 2.1 Cell 6: the interface

```python
class interfazAgente(ABC):
  @abstractmethod
  def start(self): ...                               # reset at the start of each round
  @abstractmethod
  def try_attempt(self): ...                         # return a guess
  @abstractmethod
  def feedBack(self, retroalimentacionLista): ...    # receive [picas, fijas]
```

`ABC` plus `@abstractmethod` means a class inheriting from `interfazAgente` cannot be instantiated unless it defines all three methods. This cell is valid Python on every version; the earlier `-> list(int)` problem is gone.

### 2.2 Cell 9: Google Drive

It mounts Drive and appends `/content/drive/MyDrive/Competencia Picas y fijas` to `sys.path`.

⚠️ **This does not decide which agents appear in the tournament.** The scanner in cell 11 looks in the **current working directory** (`os.listdir('.')`), which is `/content` in Colab. See section 9 for how to make your file visible.

### 2.3 Cell 11, part 1: `AdaptadorUniversal`

Every agent is wrapped in this adapter, so the tournament always calls the same method names:

```python
def start(self):            agente.start()                    # if it exists
def try_attempt(self):      agente.try_attempt()              # otherwise agente.try_()
                                                              # otherwise [-1,-1,-1,-1]
def receive_feedback(self, picas, fijas):
    agente.receive_feedback(picas, fijas)                     # if it exists
    # otherwise agente.feedBack([picas, fijas])
```

- An agent can implement **either** `feedBack([p, f])` or `receive_feedback(p, f)`. Your agent has both, and the adapter uses `receive_feedback`.
- An agent with no guessing method guesses `[-1,-1,-1,-1]` forever. That is always invalid, so it can never win.

### 2.4 Cell 11, part 2: the two built-in agents

- **`AgenteAleatorio`**: `random.sample(range(10), 4)` every turn and ignores feedback. It rarely wins.
- **`AgenteEstrategico`**:
  - `start()` lists all 5040 codes **in order** (`0123, 0124, …`);
  - it always guesses the **first** code still in the list;
  - after each answer, it keeps only the codes that would have given the same answer.

  It never guesses a code that has already been ruled out, but it doesn't choose informative guesses.

### 2.5 Cell 11, part 3: `TorneoPicasFijasUI`

Created by the last line, `UI = TorneoPicasFijasUI()`. Its methods:

| Method | What it does |
|---|---|
| `escanear_directorio()` | Imports every `.py` in the current folder, reloading ones already imported. It registers **every class** in each module that has `start` and (`try_attempt` or `try_`), named `"ClassName (file.py)"`. |
| `construir_interfaz()` | Two agent dropdowns, seed box, number of rounds (default 100), and the buttons Cargar .py, Preparar Test, Paso a Paso, Modo Auto, Torneo Masivo, plus a "Modo Visual" checkbox |
| `aplicar_semilla()` | With a seed: `random.seed(seed)`, so the judge's secrets repeat. Without one: random. |
| `iniciar_nueva_ronda()` | Draws the secret `random.sample(range(10), 4)`, **creates brand-new agent objects** `claseA()` and `claseB()`, and calls `start()` on both |
| `evaluar_intento(intento)` | Checks the guess (4 unique ints 0–9). Invalid: `(False, [0, 0])`. Valid: `(True, [picas, fijas])`. |
| `ejecutar_un_turno()` | Asks A for a guess, then B, timing each call; scores both; counts invalid guesses; sends feedback to both; checks for `[0, 4]` |
| `on_paso` / `on_auto` | Step by step, or automatic with a 0.1 s pause per turn |
| `on_masivo()` | Plays N rounds without drawing each turn, with a progress bar |
| `finalizar_torneo()` | Report: wins, win %, average turns **of the rounds each agent won or tied**, ms per turn, and 3 bar charts |

### 2.6 One turn in `ejecutar_un_turno`

```text
1. turno_actual += 1
2. intA = A.try_attempt()   (timed)      intB = B.try_attempt()   (timed)
3. validoA, fbA = evaluar_intento(intA)  validoB, fbB = evaluar_intento(intB)
   invalid guess → errores += 1 and the feedback is [0, 0]
4. A.receive_feedback(*fbA)              B.receive_feedback(*fbB)
5. winA = fbA == [0, 4]                  winB = fbB == [0, 4]
   both   → tie (both turn counts recorded)
   only A → A wins        only B → B wins        neither → next turn
```

### 2.7 Details of the environment that matter

| Detail | Consequence |
|---|---|
| **New agent objects every round** | Nothing carries over between rounds. `__init__` must take no arguments and be fast. |
| **No turn limit** | The round only ends when someone gets `[0, 4]`. An agent that never solves plays forever. |
| **Exceptions are not caught** | An agent that raises an error stops the whole tournament. `rival_real.py` does this whenever the secret starts with 0 (see 3.3). |
| **Invalid guess → feedback `[0, 0]`** | The offending agent receives a false "no digit matches". Your agent never sends an invalid guess. |
| **Every class with `start` + `try_attempt` is listed** | Class aliases in a module show up as duplicate dropdown entries, so your agent exports only `AgentePicasFijas`. |
| **The seed controls the global `random`** | Secrets repeat for a given seed. Your agent never uses the global `random`, so it cannot change the judge's sequence. |
| **The markdown's inheritance check is not in the code** | The scanner only checks `hasattr`. Your agent inherits from `interfazAgente` anyway (section 6.5). |
| **"Average turns" only counts won or tied rounds** | Use win counts to compare agents, not that average. |

---

## 3. What the environment means for strategy

### 3.1 It is a pure speed race

The rival cannot see or affect your game, and your game cannot affect theirs. The only thing you control is **how many turns you need for the judge's secret**. The best agent is the one that solves in the fewest turns.

Because the secret is uniformly random over all 5040 codes, the right target is the **average turns over all 5040 secrets**. Fewer turns on average means more rounds where you finish first.

### 3.2 What was removed from the previous agent, and why

| Old feature | Why it is gone |
|---|---|
| Honest `discover` as the core of the rules | The judge scores guesses now (`discover` is kept only as a harmless extra) |
| Model of what the rival knows / race mode | Rival guesses are invisible |
| Liar detection / minimax switch | The judge is honest; the detector could only misfire |
| Preference for secrets without a leading 0 | The judge's secret is uniform over all 5040 codes, so this preference now costs turns |
| Class aliases (`AgenteClase1`, …) | They appeared as 7 copies of the agent in the dropdown |

Measured over all 5040 secrets, the previous agent averaged **5.312** turns (worst case 8), or 5.303 with the leading-zero preference off.

### 3.3 The leading zero

The rules require "4 dígitos enteros únicos entre 0 y 9", and the judge draws with `random.sample(range(10), 4)`. So `[0, 1, 2, 3]` is a valid secret, and 504 of the 5040 secrets start with 0.

- **Your agent** considers all 5040 codes at every step.
- **`rival_real.py`** only searches `1023…9876`. When the judge's secret starts with 0, its candidate list empties and it crashes with `IndexError`, which stops the tournament. That is a bug in that agent, not in yours.

---

## 4. The agent: map of the file

| Section | What is there |
|---|---|
| Docstring | Summary of the game in this environment and the strategy |
| Game rules | `LARGO = 4`, `BASE = 10`, `SECRETO_PERMITE_CERO_INICIAL = True` |
| Precomputation | `CODIGOS`, `INDICE`, `MASCARA_TOTAL`, `POS`, `TIENE`, `_popcount` |
| Bitset algebra | `_celdas`, `_celdas_fijas`, `_celdas_comunes`, `_particion`, `_estadisticas`, `_refinar` |
| Helpers | `_evaluar`, `_indices`, `_normalizar_numero`, `_normalizar_respuesta` |
| Decision tree | `LETRAS`, the generated `ARBOL` block, `_letra`, `_cargar_arbol` |
| Class `AgentePicasFijas` | `start`, `try_attempt`, `feedBack`, `receive_feedback`, `discover`, `_elegir_jugada`, `_recuperar` |
| Interface glue | the `try` alias, `_buscar_interfaz`, `_registrar_en_interfaz`, `_heredar_de_interfaz` |
| Self-test | `python3 Picas_Y_Fijas_Agent.py` plays all 5040 secrets |

Two helper files go with it (you **don't** upload them):

- `generar_arbol.py` computes the decision tree and writes it into the agent file.
- `test_nuevo_ambiente.py` runs the real notebook code against the rivals.

### 4.1 The agent's memory (reset by `start()`)

| Attribute | Meaning |
|---|---|
| `_mascara` | Bitmask of the codes that could still be the secret |
| `_ruta` | The answers so far, one letter each (`None` = off the tree) |
| `_historia` | `(guess_index, (picas, fijas))` for every answer, used for recovery |
| `_ultima_jugada` | The guess waiting for its answer |
| `_jugadas_hechas` | Guesses already made (never repeated) |
| `resuelto` | True after `[0, 4]` |
| `secret` | A valid 4-digit secret. The new environment ignores it; it exists for the rules text and the old notebook. |

### 4.2 The methods, in plain words

- **`__init__()`**: no arguments. It creates a private random generator seeded from `os.urandom`, then calls `start()`. It takes about 0.02 ms, which matters because the environment creates a new agent every round.
- **`start()`**: sets `secret`, empties the memory, and sets `_mascara` to all 5040 codes and `_ruta` to `""`.
- **`try_attempt()`**: asks `_elegir_jugada()` for a code index, records it, and returns it as `[d0, d1, d2, d3]`. If anything went wrong inside, it falls back to the first candidate not yet played, so it always returns a valid guess.
- **`feedBack([picas, fijas])`**:
  1. checks the answer is possible (2 ints, P + F ≤ 4);
  2. on `[0, 4]`, marks the round solved and stops;
  3. otherwise appends to `_historia`, keeps only the codes consistent with the answer (`_refinar`), and adds the answer's letter to `_ruta`;
  4. if no code is left (impossible with an honest judge), runs `_recuperar()` and leaves the tree.
- **`receive_feedback(picas, fijas)`**: the adapter's preferred name; it calls `feedBack([picas, fijas])`.
- **`discover(numeroLista)`**: kept for the old notebook. It scores a guess against `self.secret`, and the new environment never calls it.

---

## 5. The agent: how it represents knowledge

### 5.1 All codes, numbered

```python
CODIGOS = list(itertools.permutations(range(10), 4))   # (0,1,2,3), (0,1,2,4), … (9,8,7,6)
INDICE  = {code: i for i, code in enumerate(CODIGOS)}  # tuple → 0…5039
```

### 5.2 A set of codes is one integer

The set of codes that could still be the secret is **one Python integer with 5040 bits**: bit *i* is 1 if `CODIGOS[i]` is still possible. `MASCARA_TOTAL = 2**5040 − 1` means every code is possible.

| Set operation | Integer operation |
|---|---|
| intersection | `A & B` |
| union | `A \| B` |
| size | `_popcount(A)`, i.e. `int.bit_count` |
| is code *i* in A? | `(A >> i) & 1` |

At import, 50 masks are built once:
- `POS[p][d]`: codes with digit *d* at position *p*;
- `TIENE[d]`: codes containing digit *d* anywhere.

### 5.3 Splitting a set by answer: `_celdas`

`_celdas(set, 4 masks)` returns 5 groups: codes inside exactly 0, 1, 2, 3 or 4 of the masks.

It starts with everything in group 0. For each mask, the part of each group inside that mask moves up one group. Groups are processed from high to low, so no code moves twice for the same mask.

- With the guess's position masks `POS[0][g0] … POS[3][g3]`, the groups are the codes with **0–4 fijas** (`_celdas_fijas`).
- With its digit masks `TIENE[g0] … TIENE[g3]`, the groups are the codes sharing **0–4 digits** with the guess, i.e. picas + fijas (`_celdas_comunes`).

Real trace with 6 codes and guess `1234`, using the position masks:

```text
start           g0=[1234 1289 1567 2134 4321 5678]
POS[0][1]       g0=[2134 4321 5678]  g1=[1234 1289 1567]
POS[1][2]       g0=[2134 4321 5678]  g1=[1567]  g2=[1234 1289]
POS[2][3]       g0=[4321 5678]  g1=[1567 2134]  g2=[1289]  g3=[1234]
POS[3][4]       g0=[4321 5678]  g1=[1567]  g2=[1289 2134]  g4=[1234]
```

### 5.4 Filtering and splitting

- **`_refinar(set, guess, P, F)`** keeps the codes consistent with the answer:

  ```python
  _celdas_fijas(guess)[F] & _celdas_comunes(guess)[P + F]
  ```

  For example, after guess `1234` with answer `[2, 1]`, **216** of the 5040 codes remain.
- **`_particion(guess, set)`** lists every non-empty answer group of a guess, leaving out the winning `[0, 4]`.
- **`_estadisticas`** returns (sum of squared group sizes, largest group) for the backup search.

Every first guess splits the 5040 codes the same way. For `0123`:

| Answer | Codes | Answer | Codes |
|---|---|---|---|
| [1,0] | 1440 | [0,2] | 180 |
| [2,0] | 1260 | [1,2] | 72 |
| [1,1] | 720 | [0,3] | 24 |
| [0,1] | 480 | [4,0] | 9 |
| [0,0] | 360 | [3,1] | 8 |
| [3,0] | 264 | [2,2] | 6 |
| [2,1] | 216 | [0,4] | 1 (win) |

---

## 6. The agent: strategy

### 6.1 Order of decisions in `_elegir_jugada`

```text
(a) First turn            → the fixed opening 0123
(b) Is _ruta in ARBOL?     → play the stored guess                    (≈ every turn)
(c) 1 or 2 candidates      → play one of them
(d) Otherwise (off-tree)   → live search over all 5040 guesses
```

With an honest judge, the tree covers every position with 3 or more candidates, so (d) never runs in this environment. It is there as insurance.

### 6.2 The decision tree: what it optimises

Think of the whole game as a tree:
- the root is "5040 candidates, no answers yet";
- each guess splits the current candidates into answer groups;
- each group is a child position.

For a set S of *n* candidates, define **cost(S)** as the total number of turns needed to solve **every** secret in S, summed:

```text
cost(S) = 1                          if n = 1   (guess it)
cost(S) = 3                          if n = 2   (1 turn for one, 2 for the other)
cost(S) = min over guesses g of   n + Σ cost(S_c)
                                  └┬┘   └───┬───┘
               every secret in S spends     then each answer group S_c (not [0,4])
               this turn on g               is solved on its own
```

Average turns = cost(all 5040) / 5040. The **best possible** tree for this game is known to average about **5.21**.

**Why a precomputed tree.** The exact minimum needs, at every position, the full cost of every possible guess, which is far too slow to do during a game. So `generar_arbol.py` does the search **once, offline**, and the agent stores only the resulting choices.

### 6.3 How `generar_arbol.py` searches

At each position with *n* ≥ 3 candidates:

1. **Shortlist the guesses.** Score all 5040 guesses cheaply, then keep:
   - the top K(n) by **sum of squared group sizes** (fewest candidates left on average);
   - the top K(n)/2 by **largest group** (minimax);
   - the best few **candidates** (guesses that could win immediately).
2. **Evaluate each shortlisted guess exactly:** *n* + Σ cost(child), computed recursively. The same set of candidates can be reached by different paths, so results are memoised by bitmask.
3. **Prune.** A group of *k* codes costs at least `1 + 2·min(k−1, 13) + 3·max(0, k−14)` turns: one code can be solved on the next guess, at most 13 more on the guess after, and the rest need at least 3. If the cost so far plus these lower bounds already reaches the best guess found, stop evaluating this guess.
4. **Choose the second guess in parallel.** The second guess matters most, so its shortlist is larger and evaluated in separate processes.

Result used by the agent:

- **Exact average:** ⟦AVG⟧ turns over all 5040 secrets (⟦TOTAL⟧ turns in total).
- **Worst case:** ⟦MAX⟧ turns.
- **Table:** ⟦NODES⟧ entries; a turn takes microseconds.
- **Search settings:** ⟦SETTINGS⟧, taking ⟦GEN_TIME⟧ on 12 cores.

**Second guesses chosen** (the first guess is always `0123`):

⟦SECOND_TABLE⟧

Some of these second guesses **cannot be the secret**. After `[1,0]` (1440 candidates), a guess that tests new digits splits the candidates far better than any candidate does.

### 6.4 How the tree is stored in the file

Each answer `[picas, fijas]` becomes one letter:

```python
LETRAS = "abcdefghijklmnopqrstu"
letter = LETRAS[5 * picas + fijas]    # [0,0]='a' [0,1]='b' [0,2]='c' [1,0]='f' [1,1]='g' [2,0]='k' [2,1]='l' …
```

The **path** is the string of letters received so far. The block written by `generar_arbol.py` contains entries of the form `path:guess`:

```text
:0123  f:1456  k:1435  fa:....  …
```

- `:0123` means with no answers yet, play `0123`.
- `f:1456` means after `[1,0]`, play `1456`.

`_cargar_arbol` turns this text into a dictionary `{path: code index}` at import, skipping any malformed entry instead of failing. Positions with 1 or 2 candidates are not stored, because rule (c) already plays optimally there.

### 6.5 Fitting the environment

| Mechanism | Why |
|---|---|
| Only `start`, `try_attempt`, `feedBack` are needed | The three abstract methods of cell 6 |
| `receive_feedback(p, f)` | The adapter's preferred name |
| `__init__()` without arguments, ~0.02 ms | A new object is created every round |
| No global `random` | Never changes the judge's secret sequence, even with a seed |
| `_heredar_de_interfaz` | Real inheritance from `interfazAgente` (below) |
| Only one class exported | One dropdown entry |
| Every public method has a fallback | The tournament cannot crash because of this agent |
| Guesses are never repeated and always valid | No wasted turns, no `[0, 0]` penalty feedback |

**How real inheritance works.** A notebook runs its cells in the `__main__` module. When the scanner imports your file, `_buscar_interfaz` finds `interfazAgente` there, since cell 6 ran first, and creates:

```python
AgentePicasFijas = ABCMeta("AgentePicasFijas", (OriginalClass, interfazAgente), {...})
```

- The MRO is `AgentePicasFijas → OriginalClass → interfazAgente → ABC → object`, so your methods override the abstract ones.
- If `__abstractmethods__` is empty, this class is exported.
- If the interface demanded a method the agent lacked, the plain class would be kept and registered with `interfazAgente.register(...)`. `isinstance` is then still True, and no `TypeError` is raised.

---

## 7. A real round, turn by turn

⟦TRACE⟧

---

## 8. Dictionary of Spanish names

| Code name | Meaning |
|---|---|
| `picas`, `fijas` | digit elsewhere / digit in place |
| `intento`, `jugada` | a guess |
| `secreto`, `juez` | secret, judge |
| `codigo`, `CODIGOS` | a 4-digit code / all 5040 codes |
| `conjunto`, `mascara` | set / bitmask |
| `candidatos` | codes that could still be the secret |
| `celdas`, `particion` | groups of a split |
| `comunes` | shared digits (picas + fijas) |
| `refinar` | filter by an answer |
| `arbol`, `ruta` | decision tree, path of answers |
| `costo` | total turns of a subtree |
| `cota` | lower bound |
| `hechas` | already played |
| `recuperar` | recover |
| `retroalimentacion` | feedback |

---

## 9. How to use and test it

### In the contest notebook

1. **Put `Picas_Y_Fijas_Agent.py` where the scanner looks.** The scanner reads the **working directory**, not the Drive path in cell 9. Either:
   - add a cell after cell 9 with `import os; os.chdir(ruta_carpeta)`, then run cell 11; or
   - copy the file into `/content`.
2. **Run cell 6, then cell 11.** If cell 6 runs first, the agent inherits from `interfazAgente`.
3. **Pick `AgentePicasFijas (Picas_Y_Fijas_Agent.py)`** as Agente A or B, choose the number of rounds, and press **⚖️ Torneo Masivo**. Use **🔄 Cargar .py** if you add files after the interface was built.

### Locally

```bash
python3 Picas_Y_Fijas_Agent.py        # plays all 5040 secrets: exact average, worst case, time
python3 test_nuevo_ambiente.py 1000   # real notebook code vs 6 rivals
python3 generar_arbol.py              # recompute the tree (minutes; writes the ARBOL block)
```

`test_nuevo_ambiente.py`:
- reads cells 6 and 11 of the notebook and runs them as they are;
- replaces only the drawing libraries, which don't exist outside Colab;
- copies the agents into a temporary "Drive" folder;
- presses the controls from code.

The rivals:
- **Built into the notebook:** `AgenteEstrategico`, `AgenteAleatorio`.
- **Classmate's agent:** `rival_real.py`.
- **From `examples/`, adapted to the new interface in `rivales_nuevo_ambiente.py`:** `AgenteJuan`, `AgenteCrucetero` (minimax), `AgenteEntropico`.

### Measured results

⟦RESULTS⟧
