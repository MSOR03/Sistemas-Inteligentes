# Picas y Fijas: how the environment and the agent work

This document explains two pieces of code:

1. **The environment**: `Ambiente.ipynb`, the notebook that runs the contest.
2. **The agent**: `Picas_Y_Fijas_Agent.py`, the file you submit.

Every number and example below was produced by running the current code. Line numbers refer to `Picas_Y_Fijas_Agent.py` as it is now. The code uses Spanish names; section 7 is a small dictionary.

---

## Contents

1. [The game](#1-the-game)
2. [The environment: `Ambiente.ipynb`](#2-the-environment-ambienteipynb)
3. [The agent: map of the file](#3-the-agent-map-of-the-file)
4. [The agent: how it represents knowledge](#4-the-agent-how-it-represents-knowledge)
5. [The agent: strategies](#5-the-agent-strategies)
6. [A real game, turn by turn](#6-a-real-game-turn-by-turn)
7. [Dictionary of Spanish names](#7-dictionary-of-spanish-names)
8. [How to use and test it](#8-how-to-use-and-test-it)

---

## 1. The game

- Each agent picks a **secret**: 4 digits from 0–9 with **no repeats**, stored as a list like `[4, 2, 7, 1]`.
- Each turn, both agents guess the other's secret.
- The answer to a guess is a list **`[picas, fijas]`**:
  - **fija**: a correct digit in the **correct** position;
  - **pica**: a correct digit in the **wrong** position.
- An agent that gets **`[0, 4]`** (4 fijas) wins the round.

Example with secret `4271` and guess `1234`:

| Position | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Secret | 4 | 2 | 7 | 1 |
| Guess | 1 | **2** | 3 | 4 |
| Result | pica (1 is in the secret) | **fija** | miss | pica (4 is in the secret) |

Answer: **`[2, 1]`**, which is 2 picas and 1 fija.

There are 10 × 9 × 8 × 7 = **5040** possible secrets. The whole problem is shrinking those 5040 down to one in as few turns as possible, and in fewer turns than the rival.

---

## 2. The environment: `Ambiente.ipynb`

### 2.1 What each cell does

| Cell | Type | Purpose |
|---|---|---|
| 0–4 | Markdown | Title and rules (the "Ambiente" and "Juego" sections) |
| 5 | Code | `interfazAgente`: the class every agent must follow |
| 6, 7, 9 | Markdown | Headings |
| 8 | Code | Mounts Google Drive and adds the agents' folder to `sys.path` |
| 10 | Code | The environment: validates, plays rounds and the tournament |

### 2.2 Cell 5: the interface

```python
from abc import ABC, abstractmethod

class interfazAgente(ABC):
  @abstractmethod
  def start(): ...
  @abstractmethod
  def try_attempt(): ...
  @abstractmethod
  def discover(numeroLista) -> list(int): ...
  @abstractmethod
  def feedBack(retroalimentacionLista): ...
```

**What it means.** `ABC` plus `@abstractmethod` is Python's way of declaring a required contract. If a class inherits from `interfazAgente` but is missing any of the four methods, `AgentClass()` raises `TypeError`. The contest requires every agent to follow this contract:

| Method | When the environment calls it | What it must do / return |
|---|---|---|
| `start()` | Once at the start of **every round** | Create a new secret |
| `try_attempt()` | Once per turn | Return a `list` of 4 unique `int` from 0–9 |
| `discover(numeroLista)` | Once per turn, with the **rival's** guess | Return `[picas, fijas]` for that guess against **your** secret |
| `feedBack(retroalimentacionLista)` | Once per turn, with the answer to **your** guess | Update what you know |

**Two problems in this cell:**

- **`-> list(int)` breaks on Colab.** Before Python 3.14, annotations are evaluated when the function is defined, and `list(int)` raises `TypeError: 'type' object is not iterable`. On Colab (Python 3.12) the cell fails and `interfazAgente` never exists. The fix is `-> list[int]`.
- **The methods have no `self`.** This is harmless: they are never called, only overridden.

### 2.3 Cell 8: Google Drive

```python
drive.mount("/content/drive")
ruta_carpeta = "/content/drive/MyDrive/Competencia Picas y fijas"
sys.path.append(ruta_carpeta)
```

Once the folder is in `sys.path`, any file in it can be imported by name. For example, `Picas_Y_Fijas_Agent.py` is imported with `from Picas_Y_Fijas_Agent import ...`.

### 2.4 Cell 10: the environment code

#### Imports (currently broken)

```python
from Picas_Y_Fijas_Agent imp        # ← SyntaxError: the whole cell fails
```

This line has to define two names, because the rest of the cell uses `AgenteClase1` and `AgenteClase2`:

```python
from Picas_Y_Fijas_Agent import AgentePicasFijas as AgenteClase1
from rival_module import RivalClass as AgenteClase2
```

#### `es_intento_valido(lista)`: is this a valid number?

```python
if not isinstance(lista, list) or len(lista) != 4: return False
if not all(isinstance(x, int) and 0 <= x <= 9 for x in lista): return False
if len(set(lista)) != 4: return False
return True
```

A number passes only if **all three** conditions hold:

- it is a `list` (a tuple or a string fails);
- it has exactly 4 `int` values, each from 0 to 9;
- it has no repeated digits: `set` removes duplicates, so its length must still be 4.

| Input | Result | Why |
|---|---|---|
| `[1, 2, 3, 4]` | ✅ | |
| `[0, 1, 2, 3]` | ✅ | A leading zero is accepted |
| `(1, 2, 3, 4)` | ❌ | A tuple, not a list |
| `"1234"` | ❌ | A string |
| `[1, 1, 2, 3]` | ❌ | Repeated digit |

#### `invocar_try(agente)`: call the guessing method

```python
if hasattr(agente, "try"):
    return getattr(agente, "try")()
elif hasattr(agente, "try_attempt"):
    return agente.try_attempt()
else:
    raise AttributeError(...)
```

The rules call the method `try`, but `def try(self):` is a syntax error because `try` is a reserved word. So the environment first looks for an attribute literally named `"try"`, which can only be created with `setattr`. If there isn't one, it uses `try_attempt`.

#### `jugar_ronda(agente1, agente2, numero_ronda)`: one round

Step by step:

```text
1. agente1.start(); agente2.start()          ← new secrets
2. repeat for turno = 1 … 100:
   a. intento1 = invocar_try(agente1)        ← agent 1 guesses
      intento2 = invocar_try(agente2)        ← agent 2 guesses
   b. if a guess is invalid → only print a message (no penalty, the turn continues)
   c. eval_para_1 = agente2.discover(intento1)   ← agent 2 scores agent 1's guess
      eval_para_2 = agente1.discover(intento2)   ← agent 1 scores agent 2's guess
   d. agente1.feedBack(eval_para_1)          ← each agent receives the answer to ITS guess
      agente2.feedBack(eval_para_2)
   e. gana1 = eval_para_1 is a list of length 2 and eval_para_1[1] == 4
      gana2 = the same for eval_para_2
   f. both win    → print tie,               return 0
      only 1 wins → print "Agente 1 gana",   return 1
      only 2 wins → print "Agente 2 gana",   return 2
3. after 100 turns without a winner → tie, return 0
```

Details that matter:

- **Both agents guess before either gets an answer.** Agent 1 being "first" gives no advantage. Winning on the same turn is a tie, so every round is a **race**.
- **`feedBack` runs before the win check**, so the winner also receives its `[0, 4]`.
- **The first `gana1 = eval_para_1 == [0, 4] or ...` line is dead code.** It is immediately overwritten by the second check, which only looks at `fijas == 4`.
- **An answer that is not a `list` can never win.** If an agent's `discover` returns a tuple `(0, 4)`, the isinstance check fails and its rival can never win. Your agent always returns a `list`.
- **Invalid guesses are not penalised.** The guess is still passed to the rival's `discover`.
- **Exceptions are not caught.** If any agent raises an error in any method, the notebook cell stops and the tournament is over.

#### `ejecutar_torneo()`: three rounds

```python
agente1 = AgenteClase1()     # created ONCE
agente2 = AgenteClase2()
for i in range(1, 4):
    resultado = jugar_ronda(agente1, agente2, i)
    # count victories; ties count for nobody
# print totals and the champion (or a tie)
```

**The same two objects play all 3 rounds.** Anything an agent remembers from round 1 is still there in round 2, unless `start()` clears it. This is why your agent's `start()` resets its whole state.

### 2.5 Written rules vs. cell 10

The Markdown describes functions named `Ambiente.setup`, `initRound`, `getAttempts`, `evaluateAttempts`, `dispatchFeedback` and `getWinner`. **None of them exist in cell 10**; it is a simpler draft. The official contest may enforce the written rules, so the agent is built to satisfy both.

| Rule | Written rules | Cell 10 | Your agent |
|---|---|---|---|
| Inherit from `interfazAgente` | Checked in `setup` | Not checked | Inherits for real (section 5.8) |
| Invalid secret | Round lost | Not checked | Always valid |
| Invalid guess | Recorded as invalid | Printed only | Always valid |
| Answer `[P, F]` with P + F ≤ 4 | Validated | Not checked | Always valid and honest |
| An agent raises an exception | Not mentioned | Tournament stops | No public method ever raises |

---

## 3. The agent: map of the file

| Lines | Section | What is there |
|---|---|---|
| 1–51 | Docstring | Summary of the agent |
| 73–83 | Game constants | `LARGO = 4`, `BASE = 10`, `SECRETO_PERMITE_CERO_INICIAL = False` |
| 89–121 | Precomputation | `CODIGOS`, `INDICE`, `MASCARA_TOTAL`, `POS`, `TIENE`, `SIN_CERO_INICIAL`, `_popcount` |
| 124–193 | Bitset algebra | `_celdas`, `_celdas_fijas`, `_celdas_comunes`, `_estadisticas`, `_refinar` |
| 196–258 | Helpers | `_evaluar` (scoring), `_normalizar_numero`, `_normalizar_respuesta` |
| 265–303 | Class constants | Strategy settings: `CRITERIO`, `CARRERA`, `UMBRAL_*`, … |
| 305–347 | Setup | `__init__`, `_reiniciar_estado`, `start` |
| 352–429 | Interface methods | `try_attempt`, `discover`, `_actualizar_modelo_rival`, `feedBack` |
| 434–551 | Decision core | `_elegir_jugada`, `_debe_arriesgar`, `_actualizar_sospecha_adversarial`, `_recuperar` |
| 556–582 | Compatibility | `compute`, `respond`, `guess`, `feedback`, `reset`, `initRound` |
| 585–658 | Glue | `_indices`, the `try` alias, interface inheritance, class aliases |
| 665– | Self-test | Runs when you execute `python3 Picas_Y_Fijas_Agent.py` |

### 3.1 The agent's memory (`_reiniciar_estado`, line 316)

`start()` resets all of this at the beginning of each round:

| Attribute | Meaning |
|---|---|
| `self.secret` | My secret, e.g. `[2, 4, 1, 6]` |
| `_mascara` | **Bitmask of codes that could still be the rival's secret** (section 4) |
| `_candidatos` | The same set, as a list of indices |
| `_historia` | Every `(guess_index, (picas, fijas))` so far, used for recovery |
| `_ultima_jugada` | Index of my last guess, still waiting for its answer |
| `_jugadas_hechas` | Guesses already played (never repeated) |
| `_turno` | How many guesses I have made |
| `_rival_mascara` | **My model of the rival:** codes still consistent with the answers **I** gave |
| `_rival_usa_info` | How many times the rival guessed inside its own candidate set |
| `_racha_adversarial` | Consecutive "suspicious" answers (liar detection) |
| `_particion_previa` | `(largest_group, total)` for my last guess, used by liar detection |
| `resuelto` | True once I got `[0, 4]` |

### 3.2 The four interface methods, in plain words

#### `start()` (line 334)

```python
digitos = self._rng.sample(range(BASE), LARGO)          # 4 distinct digits
while not SECRETO_PERMITE_CERO_INICIAL and digitos[0] == 0:
    digitos = self._rng.sample(range(BASE), LARGO)      # re-draw if it starts with 0
self.secret = [int(d) for d in digitos]
self._reiniciar_estado()
return self.secret
```

1. It draws 4 different digits.
2. If the first digit is 0, it draws again (rejection sampling). Every one of the 4536 allowed secrets is equally likely.
3. It resets all memory, because the environment reuses the same object for all 3 rounds.

It avoids a leading 0 because a real classmate's agent only searches `1023…9876`. Against a secret like `0123` its candidate list becomes empty and `random.choice([])` crashes, and cell 10 does not catch exceptions. This stopped 130 of 600 test tournaments.

`self._rng` is a private random generator seeded from `os.urandom`. Another agent calling `random.seed(...)` cannot make your secret predictable.

#### `try_attempt()` / `try` (line 352)

```python
indice = self._elegir_jugada()          # all the strategy lives here (section 5)
self._ultima_jugada = indice            # remember it for feedBack
self._jugadas_hechas.add(indice)
self._turno += 1
return [int(d) for d in CODIGOS[indice]]
```

If `_elegir_jugada` ever raised an error, it would fall back to a random code. Line 603 adds `try` as an alias that simply calls `try_attempt`.

#### `discover(numeroLista)` (line 366)

1. `_normalizar_numero` turns the rival's guess into a list of 4 ints. It accepts a list, tuple, `"1234"` or `1234`; anything else returns `[0, 0]`.
2. `_evaluar` (line 196) computes the **honest** score:
   - `fijas` = positions where the digits are equal;
   - `comunes` = digits of the guess that appear anywhere in the secret;
   - `picas = comunes − fijas`.
3. `_actualizar_modelo_rival` records what this answer taught the rival (section 5.5).
4. It returns `[picas, fijas]` as a list of `int`.

#### `feedBack(retroalimentacionLista)` (line 402)

1. `_normalizar_respuesta` checks that it is 2 ints with P + F ≤ 4. If not, or if there is no pending guess, it ignores the call.
2. If `fijas == 4`: the round is solved, and it stops.
3. `_actualizar_sospecha_adversarial` updates liar detection (section 5.6).
4. It appends the answer to `_historia`.
5. `_mascara = _refinar(_mascara, guess, picas, fijas)` keeps only the codes consistent with the answer (section 4.3).
6. If nothing is left, the rival contradicted itself, so `_recuperar()` runs (section 5.7).
7. It rebuilds `_candidatos` from the mask.

---

## 4. The agent: how it represents knowledge

### 4.1 All codes, numbered

```python
CODIGOS = list(itertools.permutations(range(10), 4))   # 5040 tuples
INDICE  = {code: i for i, code in enumerate(CODIGOS)}  # tuple → number
```

`CODIGOS[0] = (0,1,2,3)`, `CODIGOS[1] = (0,1,2,4)`, … `CODIGOS[5039] = (9,8,7,6)`. From here on, a code is just its index 0…5039.

### 4.2 A set of codes = one big integer (bitmask)

Instead of a Python list of candidates, the agent stores **one integer with 5040 bits**: bit *i* is 1 if code *i* is still possible.

```text
_mascara = ...0 1 1 0 1 0 0 1      (bit i = 1 ⇔ CODIGOS[i] still possible)
MASCARA_TOTAL = 2**5040 − 1        (all 5040 bits on: "anything is possible")
```

Set operations become single integer operations, which Python performs in fast C code:

| Set operation | Bitmask operation |
|---|---|
| A ∩ B (codes in both sets) | `A & B` |
| A ∪ B | `A \| B` |
| A minus B | `A & ~B` or `A ^ (A & B)` |
| size of A | `_popcount(A)`, i.e. `int.bit_count` |
| is code *i* in A? | `(A >> i) & 1` |

At import, the agent precomputes 50 masks (`_construir_mascaras`, line 96):

- `POS[p][d]`: all codes with **digit d at position p** (4 × 10 = 40 masks);
- `TIENE[d]`: all codes that **contain digit d** anywhere (10 masks).

It also builds `SIN_CERO_INICIAL = MASCARA_TOTAL & ~POS[0][0]`, the 4536 codes that do not start with 0.

### 4.3 Splitting a set by answer: `_celdas` (line 124)

`_celdas(conjunto, mascaras)` takes a set and 4 masks. It returns 5 disjoint groups: codes that belong to exactly 0, 1, 2, 3 or 4 of those masks.

- With the guess's **position** masks `POS[0][g0], POS[1][g1], POS[2][g2], POS[3][g3]`, the groups are codes with **0–4 fijas**. This is `_celdas_fijas`.
- With the guess's **digit** masks `TIENE[g0] … TIENE[g3]`, the groups are codes sharing **0–4 digits** with the guess (picas + fijas). This is `_celdas_comunes`.

**How the loop works.** It starts with everything in group 0. For each mask in turn, the part of every group that is inside the mask moves up one group. Groups are processed from high to low so that no code moves twice for the same mask.

A real trace with 6 codes and guess `1234`:

```text
start                  g0=[1234 1289 1567 2134 4321 5678]  g1=[]  g2=[]  g3=[]  g4=[]
mask POS[0][1] (1 at position 0)
                       g0=[2134 4321 5678]  g1=[1234 1289 1567]
mask POS[1][2] (2 at position 1)
                       g0=[2134 4321 5678]  g1=[1567]  g2=[1234 1289]
mask POS[2][3] (3 at position 2)
                       g0=[4321 5678]  g1=[1567 2134]  g2=[1289]  g3=[1234]
mask POS[3][4] (4 at position 3)
                       g0=[4321 5678]  g1=[1567]  g2=[1289 2134]  g4=[1234]
```

So against guess `1234`: `5678` and `4321` have 0 fijas; `1289` and `2134` have 2; `1234` has 4. The same call with `TIENE` masks gives shared digits: `5678`→0, `1567`→1, `1289`→2, and `1234`, `2134`, `4321`→4.

### 4.4 Filtering by an answer: `_refinar` (line 188)

Codes consistent with answer `[P, F]` to a guess are exactly:

```python
_celdas_fijas(guess, set)[F]  &  _celdas_comunes(guess, set)[P + F]
```

That is, "exactly F fijas" **and** "exactly P + F shared digits".

Real example: first guess `1234`, answer `[2, 1]`. `_refinar(MASCARA_TOTAL, index_of_1234, 2, 1)` leaves **216** of the 5040 codes, 207 of which do not start with 0.

### 4.5 Scoring a guess: `_estadisticas` (line 153)

Before playing, the agent asks for each possible guess: *if I play this, how would the candidates split by answer?*

The first guess `1234` splits all 5040 codes into these groups:

| Answer [P,F] | Codes | Answer [P,F] | Codes |
|---|---|---|---|
| [1,0] | 1440 | [0,2] | 180 |
| [2,0] | 1260 | [1,2] | 72 |
| [1,1] | 720 | [0,3] | 24 |
| [0,1] | 480 | [4,0] | 9 |
| [0,0] | 360 | [3,1] | 8 |
| [3,0] | 264 | [2,2] | 6 |
| [2,1] | 216 | [0,4] | 1 (win) |

For a guess and the current candidate set, `_estadisticas` intersects every fijas group with every shared-digits group. Each non-empty intersection is one answer group, of size *nᶜ*. It returns three numbers:

- `suma_cuadrados` = Σ *nᶜ*²
- `suma_cubos` = Σ *nᶜ*³
- `peor` = the largest *nᶜ*

The winning group `[0, 4]` is skipped (`range(min(m, 3) + 1)`), because nothing remains to solve there.

**What Σ *nᶜ*² means.** If the secret is equally likely to be any of the *n* candidates, the answer lands in group *c* with probability *nᶜ/n*, leaving *nᶜ* candidates. The expected number left is therefore Σ (*nᶜ/n*)·*nᶜ* = Σ *nᶜ*² / *n*. Minimising the sum of squares minimises the expected number of candidates left.

---

## 5. The agent: strategies

All strategy lives in `_elegir_jugada` (line 434). It runs these steps **in this order** every turn.

### 5.1 Step order in `_elegir_jugada`

```text
1. If there are 0 candidates (should never happen) → reset to all 5040.
2. adversarial = (_racha_adversarial >= 3)                    → section 5.6
3. Leading-zero preference (if not adversarial)               → section 5.3
4. If 1–2 candidates → play one I have not played yet.
5. If this is my first guess → random code.
6. criterio = "minimax" if adversarial else "cubos".
7. Pool of guesses: my candidates only if race mode is on     → section 5.5
                    otherwise all 5040 codes.
8. Score every guess in the pool (skipping ones already played);
   keep the smallest key.
9. Save (largest group, total) of the chosen guess for liar detection.
```

### 5.2 Strategy 1: pick the guess that leaves the fewest candidates

For each guess in the pool it builds a **key** tuple. Python compares tuples item by item, and the smallest key wins:

| `criterio` | Key | Meaning |
|---|---|---|
| `"cubos"` (default) | `(suma_cubos, peor, es_candidato)` | Small groups, punishing big ones hard |
| `"cuadrados"` | `(suma_cuadrados, peor, es_candidato)` | Smallest expected number left |
| `"minimax"` | `(peor, suma_cuadrados, es_candidato)` | Smallest worst case |

`es_candidato` is 0 if the guess could itself be the secret and 1 otherwise. So between two equally good guesses, the one that **could win this turn** is preferred.

**Real example.** After `1234` → `[2, 1]`, 216 candidates remain. Some second guesses:

| Second guess | Could be the secret? | Σn² | Expected left | Σn³ | Largest group |
|---|---|---|---|---|---|
| `0235` (best) | no | 8 920 | **41.3** | 433 008 | **60** |
| `2156` | no | 9 816 | 45.4 | 576 720 | 72 |
| `1325` | yes | 10 327 | 47.8 | 656 945 | 80 |
| `5678` | no | 18 144 | 84.0 | 1 679 616 | 108 |
| `1234` (repeat) | no | 46 656 | 216.0 | 10 077 696 | 216 |

Two lessons from this table:

- **The agent scores all 5040 codes, not only candidates.** The best guess `0235` cannot be the secret, yet it splits the 216 candidates better than any candidate does. That is why the pool is `range(N_CODIGOS)`.
- **Repeating a guess teaches nothing.** It leaves all 216, which is why played guesses are skipped.

**Why cubes and not squares.** In a race, what matters is solving in 5 turns when the rival needs 6, not shaving the average. Cubing makes a single large group much more expensive, so the agent avoids guesses that sometimes leave a big group. That trims the long games. Measured with `tune.py` over 400 games:
- average turns: 5.260 (`cubos`) vs 5.298 (`cuadrados`);
- solved in 5 turns or fewer: 61.7% vs 59.3%.

**Why it is fast enough.** Scoring one guess takes two `_celdas` calls (8 mask passes) plus up to 14 intersections and popcounts on big integers. That is about 5040 guesses per turn in roughly 50 ms of plain Python.

### 5.3 Strategy 2: prefer secrets without a leading zero

```python
if self.PRIORIZAR_SIN_CERO_INICIAL and not adversarial:
    preferidos = conjunto & SIN_CERO_INICIAL
    if preferidos and preferidos != conjunto:
        conjunto = preferidos          # score against these codes only
```

Many students generate "a 4-digit number" as `range(1023, 9876)`, which never starts with 0. So, while at least one candidate does not start with 0, the agent **scores guesses only against those candidates**.

- **This limits what the agent assumes about the secret, not what it may guess.** The guess can still start with 0, like `0235` above.
- **It is self-correcting.** If the rival's secret really starts with 0, the answers eventually eliminate every other candidate, `preferidos` becomes 0, and the agent uses the full set.
- **Measured over 1200 games:**
  - 0.12 fewer turns against secrets without a leading 0;
  - 0.04 more turns against uniformly random secrets;
  - against `rival_real.py`, wins minus losses went from +70 to +128.
- **It turns off against liars** (section 5.6).

### 5.4 Strategy 3: shortcuts

- **1 or 2 candidates:** play one directly. With one it wins now. With two it wins now or next turn, and no other guess can do better.
- **First guess: random.** Before any answer, all 5040 openings are equivalent: renaming digits turns any opening into any other. A random one costs nothing and makes the agent unpredictable.
- **Never repeat a guess** (`_jugadas_hechas`). A repeat gives no information, and it guarantees the agent cannot loop forever.

### 5.5 Strategy 4: race mode, using a model of the rival

**The model.** `discover` answers honestly, so the agent knows exactly what the rival has learned. `_actualizar_modelo_rival` (line 381) applies the same filtering the rival would:

```python
self._rival_mascara = _refinar(self._rival_mascara, rival_guess, picas, fijas)
```

`_popcount(_rival_mascara)` is then how many codes the rival still cannot rule out for **my** secret. This is an upper bound: a rival that searches fewer codes may know a bit more.

**Evidence that the rival is smart.** A random guesser almost never guesses inside its own small candidate set. So, when that set has at most 300 codes and the rival's guess is inside it, `_rival_usa_info` goes up by 1.

**Race mode** (`_debe_arriesgar`, line 511) turns on when all of these hold:

```python
CARRERA is True
and _rival_usa_info >= EVIDENCIA_RIVAL        # 2: the rival really uses its information
and rival_left <= UMBRAL_RIESGO               # 6: the rival is about to solve
and rival_left <= my_total                    # and it is not behind me
```

When it is on, the pool of guesses is **only my own candidates**. A non-candidate may split the set better, but it can never win this turn. If the rival is about to win, a guess that might win or tie is worth more than information for a turn that may never come.

### 5.6 Strategy 5: detecting a lying rival

Some agents keep no fixed secret. They answer every guess with the answer that keeps the **largest** group alive, to make the game last as long as possible. `test_torneo.py` has one, called `RivalTramposo`.

**How it is detected.** After each guess, `_elegir_jugada` saves `(largest_group_size, total)` for the chosen guess, always measured on the full candidate set. When the answer arrives, `_actualizar_sospecha_adversarial` (line 520) does this:

```python
if total < 8 or peor * 2 >= total:  return        # not enough evidence
if size_of_the_group_the_answer_left == peor:  _racha_adversarial += 1
else:                                          _racha_adversarial = 0
```

- The check is skipped when the largest group is at least half of all candidates. Landing there is then normal for an honest rival.
- An honest rival lands in the largest group only sometimes. Doing it **3 turns in a row** (`UMBRAL_ADVERSARIAL`) is suspicious.

**What changes once a liar is suspected:**
- `criterio` becomes `"minimax"`. Against someone who always picks the biggest group, the agent should minimise the biggest group.
- The leading-zero preference turns off. Otherwise the liar could keep choosing groups made of codes that start with 0, which the agent is not splitting.

### 5.7 Strategy 6: recovering from contradictions (`_recuperar`, line 537)

If a rival lies or makes a mistake, the answers can contradict each other, and `_refinar` returns an empty set. Instead of starting over from all 5040, the agent drops the **oldest** answers one at a time until the remaining answers agree on something:

```text
history = [a1, a2, a3, a4]        (a4 made the set empty)
try [a2, a3, a4] → empty?  try [a3, a4] → not empty → use it
```

If even the last answer alone is impossible, it resets to all 5040.

### 5.8 Fitting the environment's structure

| Mechanism | Where | Why |
|---|---|---|
| `setattr(AgentePicasFijas, "try", _alias_try)` | line 603 | `invocar_try` looks for `try` first; `def try` is illegal |
| `_heredar_de_interfaz` | line 627 | **Real inheritance** from the notebook's `interfazAgente` |
| `_registrar_en_interfaz` | line 616, called in `__init__` | Backup when the interface is defined *after* the import |
| `AgenteClase1`, `AgenteClase2`, `Agente`, `TuAgente` | lines 653–658 | Any import name the notebook uses works |
| `compute`, `respond`, `guess`, … | lines 556–577 | Older environments like the ones in `examples/` |

**How real inheritance works.** A notebook runs its cells inside the `__main__` module. When your file is imported, `_buscar_interfaz` looks for `interfazAgente` in `__main__`. If it finds it, it builds a new class:

```python
AgentePicasFijas = ABCMeta("AgentePicasFijas", (OriginalClass, interfazAgente), {...})
```

Its MRO (method lookup order) is `AgentePicasFijas → OriginalClass → interfazAgente → ABC → object`. Your methods come first, so they override the abstract ones.

- If `__abstractmethods__` is empty, every required method is implemented and this new class is used.
- If the interface demanded a method the agent does not have, creating an agent would fail. In that case the agent keeps the plain class and **registers** it with `interfazAgente.register(...)` instead, so `isinstance` is still True and no `TypeError` is raised.

**Therefore: run cell 5 before cell 10.**

### 5.9 Robustness rules

- **Every public method is wrapped in `try/except` with a safe result.** A bug can never stop the tournament.
- **Guesses** are always a `list` of 4 unique `int`.
- **Answers** are always `[int, int]` with P + F ≤ 4.
- **Bad input is tolerated:** a malformed guess from the rival gives `[0, 0]`, and malformed feedback is ignored.

---

## 6. A real game, turn by turn

Your agent against `rival_real.py`, replayed with fixed seeds. Here `rival_real.py` is the classmate's agent: it plays a random code that fits all its answers so far.

My secret `[2, 4, 1, 6]`, rival secret `[3, 5, 0, 9]`.

| Turn | My guess | Could it be the secret? | Answer | My candidates left | Rival's guess | My answer | Rival's candidates left (my model) |
|---|---|---|---|---|---|---|---|
| 1 | `5291` | (first guess, random) | [2,0] | 1260 | `5678` | [1,0] | 1440 |
| 2 | `1324` | yes | [1,0] | 304 | `3960` | [1,0] | 378 |
| 3 | `2167` | **no**, but the best split | [0,0] | 44 | `9714` | [1,1] | 62 |
| 4 | `9485` | yes | [2,0] | **5** | `9821` | [2,0] | 18 |
| 5 | `3509` | yes | **[0,4]** ✅ | 1 | `1732` | [2,0] | 3 |

How to read it:

- **Turn 1:** `[2,0]` leaves 1260 of 5040 codes. That is exactly the size of the `[2,0]` group in the table in section 4.5; every first guess splits the codes the same way.
- **Turn 3:** the agent plays `2167`, which **cannot** be the secret. Scored against turn 2's guess `1324`, `2167` would give `[2,0]`, but the real answer was `[1,0]`. It is still the best splitter. Its answer `[0,0]` proves that none of 2, 1, 6, 7 are in the secret: 304 → 44.
- **Turn 4:** 44 → 5, which is typical for a good guess at this size.
- **Turn 5:** 5 candidates, and the chosen guess is the secret.
- **Race mode stayed off.** The rival still had 18, then 3, candidates, and never reached the threshold of 6 while being ahead of me.

The agent won in 5 turns, while the rival still had 3 candidates for my secret.

---

## 7. Dictionary of Spanish names

| Code name | Meaning |
|---|---|
| `picas`, `fijas` | digit elsewhere / digit in place |
| `intento`, `jugada` | a guess |
| `secreto` | secret |
| `codigo`, `CODIGOS` | a 4-digit code / all 5040 codes |
| `conjunto`, `mascara` | set / bitmask |
| `candidatos` | codes that could still be the secret |
| `celdas`, `grupo` | groups of a split |
| `comunes` | shared digits (picas + fijas) |
| `refinar` | filter by an answer |
| `estadisticas` | scores of a guess |
| `suma_cuadrados`, `suma_cubos`, `peor` | sum of squares, sum of cubes, worst case |
| `reserva` | the pool of guesses considered |
| `hechas` | already played |
| `carrera`, `arriesgar` | race / take the risk |
| `racha adversarial` | streak of suspicious answers |
| `recuperar` | recover |
| `SIN_CERO_INICIAL` | codes that do not start with 0 |
| `retroalimentacion` | feedback |

---

## 8. How to use and test it

**In the contest notebook (Colab):**

1. Put `Picas_Y_Fijas_Agent.py` in the Drive folder from cell 8.
2. In cell 5, change `-> list(int)` to `-> list[int]`, then run cell 5.
3. In cell 10, replace the broken import line:

   ```python
   from Picas_Y_Fijas_Agent import AgentePicasFijas as AgenteClase1
   from rival_module import RivalClass as AgenteClase2
   ```

4. Run cell 10. `ejecutar_torneo()` prints every round and the champion.

**Locally, from the `Picas&Fijas` folder:**

```bash
python3 test_ambiente.py 300    # runs the notebook's real cells: interface + 300 tournaments
python3 validar.py 800 100      # turn statistics + rivals from examples/
python3 test_rival_real.py 300  # against the classmate's agent
python3 Picas_Y_Fijas_Agent.py  # quick self-test
```

**Measured results:**

- **Solving alone:** 5.24–5.29 turns on average, never more than 7, 61% solved in 5 turns or fewer.
- **Against `rival_real.py` on the notebook's code:** 63–66% of tournament points.
- **Rule violations:** 0.

**Settings you can change** (class constants, lines 270–303, and line 83):

| Constant | Default | Effect |
|---|---|---|
| `SECRETO_PERMITE_CERO_INICIAL` | `False` | Allow secrets like `0123` |
| `CRITERIO` | `"cubos"` | `"cuadrados"` or `"minimax"` |
| `PRIORIZAR_SIN_CERO_INICIAL` | `True` | Leading-zero preference (5.3) |
| `CARRERA` / `UMBRAL_RIESGO` / `EVIDENCIA_RIVAL` | `True` / `6` / `2` | Race mode (5.5) |
| `UMBRAL_ADVERSARIAL` | `3` | Suspicious answers in a row before minimax (5.6) |
