# -*- coding: utf-8 -*-
"""Agente rival, copiado VERBATIM tal como lo entrego el companero."""

import random


class PicasFijasAgent:

  candidate_set = []
  my_number = []
  my_guess = []

  def __init__(self):
    pass

  def start(self):
    self.populate_candidate_set()
    self.choose_random_number()
    self.my_guess = [5,6,7,8]

  def populate_candidate_set(self):
    self.candidate_set = [[int(d) for d in str(n)] for n in range(1023, 9876 + 1) if len(set(str(n))) == 4]
    #print(len(list(self.candidate_set)))

  def choose_random_number(self):
    self.my_number = random.choice(self.candidate_set)
    #print(self.my_number)

  def try_attempt(self) -> list[int]:
    return self.my_guess

  def discover(self, enemy_guess: list[int]) -> list[int]:
    return self.check_option(enemy_guess, self.my_number)

  def feedBack(self, enemy_answer: list[int]):
    self.clean_candidate_set(enemy_answer)
    self.my_guess = random.choice(self.candidate_set)

  def clean_candidate_set(self, enemy_answer: list[int]):
    self.candidate_set = [opcion for opcion in self.candidate_set
                          if self.check_option(self.my_guess, opcion) == enemy_answer]

  def check_option(self, option:list[int], guessing_number: list[int]) -> list[int]:
    picas = 0
    fijas = 0

    for i in range(4):
      if option[i] in guessing_number:
        if option[i] == guessing_number[i]:
          fijas += 1
        else:
          picas += 1

    return [picas, fijas]
