import itertools
import random

class AgentA:
    def __init__(self):
        digits = '0123456789'
        self.candidates = [''.join(p) for p in itertools.permutations(digits, 4)]
        self.last_guess = random.choice(self.candidates)

    def compute(self, percept):
        if percept is None:
            return self.last_guess

        picas, fijas = percept
        new_candidates = []
        for c in self.candidates:
            if self.evaluate(c, self.last_guess) == (picas, fijas):
                new_candidates.append(c)
        self.candidates = new_candidates

        if self.candidates:
            self.last_guess = self.candidates[0]
            return self.last_guess
        else:
            return 'Humano.......'

    def evaluate(self, secret, guess):
        fijas = sum(s == g for s, g in zip(secret, guess))
        picas = sum(min(secret.count(d), guess.count(d)) for d in set(guess)) - fijas
        return picas, fijas


class AgentB:
    def __init__(self):
        self.used = set()
        self.good_digits = set()
        self.turn = 0
        self.last_guess = None

    def compute(self, percept):
        self.turn += 1

        if percept is not None and percept != '*':
            picas, fijas = percept
            if picas + fijas > 0:
                self.good_digits.update(self.last_guess)
            else:
                self.used.update(self.last_guess)

        if self.turn <= 3 or len(self.good_digits) < 4:
            available_digits = [d for d in '0123456789' if d not in self.used]
            temp_guess_list = []
            temp_guess_set = set()

            for d in available_digits:
                if len(temp_guess_list) < 4:
                    temp_guess_list.append(d)
                    temp_guess_set.add(d)
                else:
                    break

            all_digits_pool = [d for d in '0123456789' if d not in temp_guess_set]
            random.shuffle(all_digits_pool)

            while len(temp_guess_list) < 4 and all_digits_pool:
                d = all_digits_pool.pop()
                temp_guess_list.append(d)
                temp_guess_set.add(d)

            guess = temp_guess_list
            random.shuffle(guess)

        else:
            base = list(self.good_digits)
            current_guess_digits_set = set(base)

            remaining_digits_for_fill = [d for d in '0123456789' if d not in current_guess_digits_set]
            random.shuffle(remaining_digits_for_fill)

            while len(base) < 4 and remaining_digits_for_fill:
                d = remaining_digits_for_fill.pop()
                base.append(d)
                current_guess_digits_set.add(d)

            guess = random.sample(base, 4)

        self.last_guess = ''.join(guess)
        return self.last_guess


class Environment:
    def __init__(self):
        digits = '0123456789'
        self.secret_A = ''.join(random.sample(digits, 4))
        self.secret_B = ''.join(random.sample(digits, 4))

    def evaluate(self, secret, guess):
        fijas = sum(s == g for s, g in zip(secret, guess))
        picas = sum(min(secret.count(d), guess.count(d)) for d in set(guess)) - fijas
        return picas, fijas


env = Environment()
A = AgentA()
B = AgentB()

agents = [
    ('A', A, env.secret_B),
    ('B', B, env.secret_A)
]

random.shuffle(agents)

percepts = {'A': None, 'B': None}

print(f'Secret A: {env.secret_A}, Secret B: {env.secret_B}')
print(f'🎯 Empieza el Agente {agents[0][0]}')

game_over = False

for turn in range(1, 21):
    if game_over:
        break

    print(f'\n--- Turno {turn} ---')

    for name, agent, secret in agents:
        guess = agent.compute(percepts[name])
        result = env.evaluate(secret, guess)
        percepts[name] = result

        print(f'Agente {name} → {guess} | Picas/Fijas: {result}')

        if result[1] == 4:
            print(f'\n🏆 Agente {name} gano')
            game_over = True
            break

if not game_over:
    print('\n⏹ Nadie ganó')

