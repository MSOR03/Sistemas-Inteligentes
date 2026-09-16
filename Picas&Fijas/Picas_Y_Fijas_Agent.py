# -*- coding: utf-8 -*-
"""
===============================================================================
 AGENTE PARA LA COMPETENCIA DE PICAS Y FIJAS
 Ambiente: Ambientes/Ambiente_Definitivo.ipynb  (juez central)
 Regla del curso: el agente no tiene ciclos indefinidos. Recibe un dato
 (feedBack), lo procesa (_refinar / _elegir_jugada) y devuelve un dato
 (try_attempt); el ciclo de turnos lo controla el ambiente.
===============================================================================

Como es el juego en este ambiente
---------------------------------
 * En cada ronda el JUEZ genera un unico secreto (random.sample(range(10), 4):
   uniforme sobre las 5040 combinaciones, el 0 inicial es valido).
 * Los dos agentes intentan adivinar ESE MISMO secreto, cada uno por su lado.
   Nadie evalua al rival ni ve sus intentos: gana quien lo resuelve en menos
   turnos (mismo turno = empate).
 * Por eso la unica forma de ganar mas rondas es resolver en menos turnos.

Contrato con el ambiente (interfazAgente)
-----------------------------------------
 * start()                 -> resetea el estado al comenzar la ronda.
 * try_attempt()           -> LISTA de 4 enteros unicos entre 0 y 9.
 * feedBack([picas,fijas]) -> incorpora la respuesta del juez.
 (receive_feedback(picas, fijas), `try` y discover() son alias/compatibilidad.)

Estrategia
----------
 1. Arbol de decision precalculado (ARBOL). Para cada historial de respuestas
    guarda la jugada que minimiza el numero TOTAL de turnos sobre todos los
    secretos todavia posibles. Se obtuvo fuera de linea con `generar_arbol.py`
    con busqueda en profundidad y poda; promedio exacto sobre los 5040
    secretos indicado en ARBOL_PROMEDIO. Jugar desde el arbol cuesta
    microsegundos por turno.
 2. Busqueda en linea de respaldo, solo si la partida se sale del arbol (por
    ejemplo si la retroalimentacion fuera inconsistente): elige, entre las
    5040 jugadas, la que minimiza el numero esperado de candidatos restantes.
 3. Candidatos como bitsets de 5040 bits: filtrar por una respuesta son unas
    pocas operaciones & | sobre enteros.
"""

from __future__ import annotations

import itertools
import os
import random
import sys
from abc import ABCMeta

# =============================================================================
#  Reglas del juego
# =============================================================================

LARGO = 4          # digitos por numero
BASE = 10          # digitos disponibles (0..9)

# El reglamento permite el 0 inicial ("4 digitos enteros unicos entre 0 y 9") y
# el juez lo usa. En este ambiente el secreto propio no se usa (lo genera el
# juez); se conserva `self.secret` valido por si un ambiente lo pidiera.
SECRETO_PERMITE_CERO_INICIAL = True

# =============================================================================
#  Universo de codigos y mascaras de bits precalculadas (una sola vez)
# =============================================================================

CODIGOS = list(itertools.permutations(range(BASE), LARGO))
N_CODIGOS = len(CODIGOS)                       # 5040
INDICE = {c: i for i, c in enumerate(CODIGOS)}
MASCARA_TOTAL = (1 << N_CODIGOS) - 1
_N_BYTES = (N_CODIGOS + 7) // 8


def _construir_mascaras():
    """POS[p][d]: bitset de codigos con el digito d en la posicion p.
    TIENE[d]:    bitset de codigos que contienen el digito d."""
    pos = [[bytearray(_N_BYTES) for _ in range(BASE)] for _ in range(LARGO)]
    tiene = [bytearray(_N_BYTES) for _ in range(BASE)]
    for i, codigo in enumerate(CODIGOS):
        byte, bit = i >> 3, 1 << (i & 7)
        for p in range(LARGO):
            d = codigo[p]
            pos[p][d][byte] |= bit
            tiene[d][byte] |= bit
    return (
        [[int.from_bytes(pos[p][d], "little") for d in range(BASE)] for p in range(LARGO)],
        [int.from_bytes(tiene[d], "little") for d in range(BASE)],
    )


POS, TIENE = _construir_mascaras()

try:                                    # Python >= 3.10
    (0).bit_count()
    _popcount = int.bit_count
except AttributeError:                  # respaldo para interpretes antiguos
    def _popcount(x):
        return bin(x).count("1")


def _celdas(conjunto, mascaras):
    """Reparte `conjunto` en 5 celdas disjuntas segun a cuantas de las 4
    `mascaras` pertenece cada codigo. celdas[k] = codigos que cumplen k de 4."""
    celdas = [conjunto, 0, 0, 0, 0]
    for nivel, m_i in enumerate(mascaras):
        for k in range(nivel, -1, -1):
            actual = celdas[k]
            if actual:
                dentro = actual & m_i
                if dentro:
                    celdas[k + 1] |= dentro
                    celdas[k] = actual ^ dentro
    return celdas


def _celdas_fijas(codigo, conjunto):
    """celdas[f] = codigos de `conjunto` con exactamente f fijas frente a `codigo`."""
    return _celdas(
        conjunto,
        (POS[0][codigo[0]], POS[1][codigo[1]], POS[2][codigo[2]], POS[3][codigo[3]]),
    )


def _celdas_comunes(codigo, conjunto):
    """celdas[m] = codigos de `conjunto` que comparten m digitos con `codigo`."""
    return _celdas(
        conjunto,
        (TIENE[codigo[0]], TIENE[codigo[1]], TIENE[codigo[2]], TIENE[codigo[3]]),
    )


def _particion(indice_jugada, conjunto):
    """Lista de ((picas, fijas), subconjunto) no vacios que produce la jugada
    sobre `conjunto`, sin la clase ganadora [0, 4]."""
    codigo = CODIGOS[indice_jugada]
    fijas = _celdas_fijas(codigo, conjunto)
    comunes = _celdas_comunes(codigo, conjunto)
    salida = []
    for m in range(LARGO + 1):
        grupo_m = comunes[m]
        if not grupo_m:
            continue
        for f in range(min(m, LARGO - 1) + 1):   # f == 4 es la clase ganadora
            interseccion = fijas[f] & grupo_m
            if interseccion:
                salida.append(((m - f, f), interseccion))
    return salida


def _estadisticas(indice_jugada, conjunto):
    """(suma de cuadrados, peor caso) de los tamanos de las clases de respuesta.
    suma_cuadrados / n = numero esperado de candidatos que sobreviven."""
    suma_cuadrados = 0
    peor = 0
    for _, grupo in _particion(indice_jugada, conjunto):
        cuenta = _popcount(grupo)
        suma_cuadrados += cuenta * cuenta
        if cuenta > peor:
            peor = cuenta
    return suma_cuadrados, peor


def _refinar(conjunto, indice_jugada, picas, fijas):
    """Subconjunto de `conjunto` compatible con la respuesta [picas, fijas]."""
    if not (0 <= fijas <= LARGO and 0 <= picas <= LARGO and picas + fijas <= LARGO):
        return conjunto                     # respuesta imposible: no se filtra
    codigo = CODIGOS[indice_jugada]
    return _celdas_fijas(codigo, conjunto)[fijas] & _celdas_comunes(codigo, conjunto)[picas + fijas]


def _evaluar(intento, secreto):
    """Picas y fijas de `intento` contra `secreto` (listas de enteros)."""
    fijas = sum(1 for a, b in zip(intento, secreto) if a == b)
    comunes = len(set(intento) & set(secreto))
    picas = max(0, min(comunes - fijas, LARGO - fijas))
    return picas, fijas


def _indices(mascara):
    """Lista de indices activos en un bitset, de menor a mayor. Se lee la
    representacion binaria al reves (bit 0 primero)."""
    return [i for i, bit in enumerate(bin(mascara)[:1:-1]) if bit == "1"]


def _normalizar_numero(valor):
    """Convierte list/tuple/str/int a lista de 4 enteros 0..9, o None."""
    if isinstance(valor, str):
        valor = valor.strip()
        if len(valor) != LARGO or not valor.isdigit():
            return None
        return [int(c) for c in valor]
    if isinstance(valor, int) and not isinstance(valor, bool):
        texto = str(valor).zfill(LARGO)
        return [int(c) for c in texto] if len(texto) == LARGO else None
    if isinstance(valor, (list, tuple)) and len(valor) == LARGO:
        try:
            salida = [int(x) for x in valor]
        except (TypeError, ValueError):
            return None
        return salida if all(0 <= d <= 9 for d in salida) else None
    return None


def _normalizar_respuesta(valor):
    """Convierte la retroalimentacion a (picas, fijas) o None si es imposible."""
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        try:
            picas, fijas = int(valor[0]), int(valor[1])
        except (TypeError, ValueError):
            return None
        if 0 <= picas <= LARGO and 0 <= fijas <= LARGO and picas + fijas <= LARGO:
            return picas, fijas
    return None


# =============================================================================
#  Arbol de decision precalculado
# =============================================================================
#
# Cada respuesta [picas, fijas] se escribe con UNA letra:
#     letra = LETRAS[5 * picas + fijas]     ([0,0]='a', [0,1]='b', [1,0]='f', [2,1]='l', ...)
# La RUTA de un momento de la partida es la cadena de letras de las respuestas
# recibidas hasta entonces ("" antes del primer intento).
#
# ARBOL[ruta] = jugada (4 digitos) que se hace en ese momento. Solo se guardan
# los momentos con 3 o mas candidatos: con 1 o 2 lo optimo es jugar un
# candidato, y eso lo hace la busqueda en linea.
#
# El bloque entre las marcas lo escribe `generar_arbol.py`; no editar a mano.

LETRAS = "abcdefghijklmnopqrstu"

# >>> ARBOL (generado por generar_arbol.py)
ARBOL_CONFIGURACION = 'rivales=AgenteLexicografico,AgenteJuan,AgenteCrucetero,AgenteEntropico peso_rivales=1 peso_carrera=1 K=[[500, 3], [150, 5], [40, 8], [0, 12]] k2=8'
ARBOL_PROMEDIO = 5.2321
ARBOL_DISTRIBUCION = {1: 1, 2: 6, 3: 69, 4: 660, 5: 2453, 6: 1714, 7: 135, 8: 2}
ARBOL_TEXTO = """
:0123 a:4576 ac:4968 acl:4879 acp:8596 ad:0568 adg:4596 adl:4586 ag:4698 agg:5978 agh:4897
agk:9587 agku:8975 agl:8796 aglk:4985 aglp:4987 agm:4968 agp:5986 agpk:8479 agpp:8549 agpq:6589
agq:4869 agu:8946 ah:4587 ahg:4956 ahgl:7596 ahh:4786 ahk:5976 ahl:6578 ahp:5876 ahq:4875
ak:6798 akd:5798 akg:5948 akgq:9458 akh:8794 akhg:5698 akhq:9748 akk:5984 akkm:8954 akkq:9854
akkqq:9485 akku:9845 akl:6489 aklg:8759 aklh:6859 aklk:7895 akll:8497 aklm:6984 aklp:7948
aklu:8694 akm:6897 akmq:7698 akp:7849 akpg:8659 akpk:8965 akpl:9864 akpm:9847 akpp:9684
akpq:7984 akq:6987 akqq:8697 aku:7869 akum:7689 al:4786 alc:4759 ald:4785 alg:4965 algq:5946
algu:9456 alh:4685 alk:9547 alkh:6549 alkl:7569 alkp:5679 alkq:7594 alku:5974 all:5846 allk:4967
allp:7584 allq:4865 allu:6584 alm:4687 almq:7486 alp:8475 alpg:6974 alpl:8564 alpp:6548
alpq:5874 alq:4867 alu:6478 am:4675 amq:4756 amqq:5476 ap:5649 apc:0548 apd:5749 apg:7685
apgl:5487 apgp:6748 apgu:5768 aph:5097 apk:6784 apkh:6758 apkl:6857 apkm:6487 apkp:7458
apku:8467 apl:7694 aplk:6845 apll:7945 aplp:6759 apm:5469 app:6794 appg:6458 appl:6957 appm:6497
appp:7965 apq:6459 apqq:6945 apu:6495 aq:0476 aqh:6475 aql:5746 aqp:4765 aqpq:7564 au:5764
aum:5467 auq:5647 auqq:7654 auu:6457 b:0456 ba:7913 bag:7829 bah:7893 bak:8729 bal:8793 bap:8179
bapm:9178 bb:7493 bbb:7826 bbbg:8196 bbc:7428 bbd:7483 bbf:8159 bbg:8427 bbgf:9853 bbgg:7926
bbh:0159 bbk:0178 bbkl:0987 bbl:9427 bc:0479 bcb:8426 bcc:0859 bcd:0489 bcf:9156 bcg:0896
bcgg:0758 bch:0759 bchg:0498 bcl:0796 bd:4876 bdg:0496 bdk:0458 bf:7148 bfb:5928 bfbh:9628
bfc:6198 bfd:7149 bff:9825 bffb:9673 bffc:9627 bfff:6793 bffg:6729 bffgk:9683 bffh:9527
bffk:6983 bffl:5729 bffm:5829 bffp:5983 bfg:5189 bfgd:5179 bfgf:7863 bfgg:6197 bfggf:7583
bfgh:8169 bfgk:8943 bfh:4198 bfhc:5178 bfk:9724 bfkb:8763 bfkf:5873 bfkg:6827 bfkk:4893
bfkl:4793 bfl:4189 bflc:5187 bflg:8167 bflk:7824 bfm:7184 bfmq:8147 bfp:4827 bfq:4187 bg:0487
bga:1926 bgb:5293 bgc:0967 bgcg:6427 bgd:0587 bgf:8526 bgfb:9146 bgff:4953 bgfk:6753 bgfp:6158
bgg:0698 bgga:7425 bggf:7463 bggg:0975 bggh:0895 bggk:4186 bgh:0785 bgk:4853 bgkb:4726 bgl:0749
bglg:0875 bgm:0784 bgq:0748 bh:0468 bhc:0475 bhd:0469 bhg:0657 bhh:0485 bhl:0746 bk:5628
bkb:5741 bkc:4672 bkd:5629 bkf:6149 bkfc:6743 bkfg:9543 bkfh:6943 bkfhg:9145 bkfk:4593 bkfl:7164
bkfm:4169 bkg:4725 bkgb:4683 bkgf:5169 bkgg:5763 bkgh:4529 bkgk:5167 bkh:8624 bkhc:7625 bkk:6184
bkkb:6573 bkkc:6195 bkkf:7563 bkkg:9165 bkkl:6843 bkl:6529 bklc:8524 bkm:6528 bkp:6583 bl:0567
blc:0548 bld:0568 blg:0846 blh:0865 blhg:0647 blk:6154 blkl:6425 bll:0685 bllc:0745 bm:0546
bmq:0654 bp:5164 bpl:5643 bpp:4625 bq:0564 c:0254 ca:6173 cac:8193 cad:6193 cah:7193 cb:0376
cbb:0189 cbc:0178 cbf:8153 cbg:0197 cbgc:0893 cbh:0873 cbk:7153 cbl:0683 cbld:0693 cc:6184
cca:0753 ccb:0157 ccc:0174 ccf:0653 ccg:0158 cf:6127 cfb:4183 cfbd:4193 cfbg:9823 cfc:8129
cfcg:6923 cfd:6128 cfg:9427 cfgf:4163 cfgg:8723 cfgk:7143 cfh:7128 cg:3148 cga:0729 cgad:0629
cgah:0926 cgb:1675 cgc:0147 cgcd:0149 cgf:2867 cgg:6704 cgk:0463 cgkd:0493 cgl:0843 ch:0627
chc:0824 ck:5187 cka:6423 ckb:5623 ckc:5126 ckcc:5143 ckf:4723 ckfc:6523 ckg:6125 ckgg:5823
ckk:7523 ckl:7125 cl:2567 clf:0428 clg:0528 clk:0825 clp:0725 cp:4523 d:0246 db:0178 dbc:0193
df:5017 dff:8123 dg:2158 dgf:0723 dgg:0127 dgk:0523 dk:4123 dl:0423 f:1456 fa:7089 fad:7289
fah:3789 fal:2879 falp:3987 falq:2987 falu:9782 fam:7809 famq:7980 fap:3978 faph:8972 fapl:9872
fapm:9378 fapp:8792 fapq:9738 fapu:8397 faq:7908 faqq:8709 faqqu:9078 faqu:8097 fau:8790
fauq:9870 fb:7259 fbb:3489 fbbg:7386 fbc:5839 fbd:0128 fbf:8906 fbfc:8736 fbfd:8936 fbff:3478
fbfg:3876 fbfh:3986 fbfk:3498 fbfl:3896 fbfm:8096 fbg:8950 fbgb:7936 fbgf:3479 fbgg:7906
fbggf:3857 fbgh:8057 fbgk:1789 fbh:2859 fbk:8472 fbkb:3976 fbkf:3796 fbkg:3497 fbkk:1987
fbkl:2876 fbl:2958 fblg:9057 fblk:7492 fbm:2759 fbmq:9257 fbp:2796 fbq:9752 fc:7419 fca:8012
fcb:8254 fcbb:7056 fcbg:8406 fcc:0752 fcf:9012 fcff:3956 fcg:3496 fcgc:2476 fcgd:2496 fcgg:9450
fck:1896 fcl:1487 fcp:1796 fd:2468 fdb:1459 fdf:1756 fdg:1496 ff:4297 ffb:5837 ffbc:6807
ffbd:5807 ffbf:6098 ffbg:6087 ffbh:3867 ffbk:8095 ffbkg:6398 ffbl:8367 ffbm:5387 ffbp:3598
ffc:3487 ffcb:5097 ffcc:3697 ffcf:5298 ffcg:6397 ffck:4890 ffd:0218 ffdb:6297 fff:7508 fffb:6938
fffbm:9638 fffc:9608 fffcc:7638 fffd:7608 fffdc:7538 ffff:6389 ffffm:8369 ffffmq:6839 ffffq:8639
fffg:0679 fffgb:8539 fffgk:6738 fffh:6708 fffhg:8509 fffk:8935 fffkg:6980 fffkk:9680 fffkm:3985
fffkq:9385 fffl:7365 ffflb:8905 ffflf:9580 fffm:5708 fffp:3670 fffpf:5089 fffpg:8375 fffpl:6780
fffq:7085 fffqq:8705 fffu:5780 ffg:2867 ffgb:5937 ffgc:3967 ffgf:7395 ffgff:4980 ffgffm:4089
ffgg:6907 ffggf:5892 ffggk:7891 ffgk:4780 ffgkb:9285 ffgkg:8791 ffgl:9268 ffgp:5278 ffh:8247
ffhg:4937 ffhgg:2697 ffk:3849 ffkb:5079 ffkbl:7609 ffkc:3769 ffkf:8572 ffkfb:9670 ffkff:7960
ffkfg:5970 ffkfk:7905 ffkfl:6782 ffkfm:7582 ffkg:6739 ffkgb:8740 ffkgf:7048 ffkgk:9862
ffkgm:7639 ffkh:3874 ffkk:9682 ffkkb:9375 ffkkf:8074 ffkkg:9718 ffkkk:7918 ffkl:7348 ffkm:3948
ffkp:7384 ffkq:3984 ffku:8934 ffl:4872 fflc:4379 fflg:5792 fflgg:4739 fflk:3794 fflkk:2967
fflp:8249 fflq:2847 fflu:7248 ffm:4792 ffmq:7294 ffp:3749 ffpc:8742 ffpg:7842 ffpgk:2579
ffph:7049 ffpk:9572 ffpl:7940 ffpp:7904 ffpq:3974 ffpu:9374 ffq:4972 ffqq:2947 ffqu:7249
ffu:0749 fg:7419 fga:5286 fgad:5086 fgah:5836 fgal:8506 fgap:6058 fgau:6852 fgb:6408 fgbb:6359
fgbd:5408 fgbf:3659 fgbg:3485 fgbgf:7506 fgbh:6482 fgbl:8462 fgc:6409 fgcc:7405 fgcd:5409
fgch:3469 fgd:8419 fgf:5096 fgfb:4286 fgfbl:8346 fgfc:5736 fgfcb:8046 fgfd:5396 fgff:4358
fgffl:8254 fgfg:4058 fgfgf:3576 fgfh:2596 fgfk:2657 fgfl:6057 fgfp:6750 fgfu:6950 fgg:5407
fgga:1869 fggb:6492 fggc:3467 fggd:6407 fggf:1589 fggg:3495 fggh:5472 fggk:7246 fggl:3475
fggp:7254 fggpg:7046 fgh:7481 fgk:4936 fgka:1875 fgkam:1578 fgkb:4257 fgkc:4276 fgkd:4736
fgkf:1768 fgkfm:1867 fgkg:2746 fgkh:4296 fgkk:9054 fgkl:9246 fgkm:3946 fgl:1679 fglk:9481
fgm:7491 fgp:1894 fgpc:1697 fgpg:1967 fgph:1847 fgq:1749 fgu:1794 fh:7491 fhb:6450 fhf:0218
fhg:1468 fhh:1495 fhk:1576 fhl:1475 fhp:1954 fk:5340 fka:6817 fkad:6917 fkah:6891 fkal:6791
fkalp:8619 fkam:6871 fkap:8961 fkapl:7691 fkaq:6781 fkau:7681 fkb:5718 fkba:6249 fkbam:6942
fkbb:5692 fkbbg:6742 fkbc:5762 fkbd:5719 fkbf:6247 fkbg:5267 fkbh:5819 fkbk:7941 fkbl:5891
fkbm:5781 fkc:6049 fkcb:5247 fkcc:6347 fkcf:5367 fkcg:5369 fkch:6740 fkck:5670 fkcl:8640
fkcp:5690 fkd:0378 fkdk:5740 fkf:4762 fkfa:8591 fkfam:9581 fkfaq:8915 fkfb:4891 fkfbk:8715
fkfbm:4981 fkfc:4719 fkfd:4862 fkff:7815 fkffl:7591 fkffq:8517 fkfg:9265 fkfga:4817 fkfgf:4917
fkfh:4682 fkfk:2685 fkfl:2864 fkfm:2764 fkfp:6284 fkfu:2674 fkg:7560 fkgb:4369 fkgbf:8542
fkgc:4860 fkgd:8560 fkgf:2845 fkgg:8365 fkggf:4690 fkgh:6580 fkgk:6395 fkgkb:6048 fkgl:5069
fkgp:6375 fkgpk:5609 fkh:8540 fkhd:9540 fkhg:9345 fkhk:5374 fkhl:5047 fkk:6804 fkkb:2594
fkkc:6905 fkkcc:6835 fkkd:6704 fkkdc:6834 fkkf:3567 fkkg:9634 fkkgb:7605 fkkgk:3865 fkkh:6074
fkkhg:6508 fkkk:4637 fkkkb:4582 fkkkk:7065 fkkl:4609 fkklg:8634 fkkm:6084 fkkp:4069 fkkq:4608
fkl:4375 fkld:4385 fklg:4580 fklk:5084 fkll:3845 fklp:3548 fklu:3547 fkp:9504 fkpc:3584
fkpd:7504 fkpg:4537 fkph:4508 fkpk:4735 fkpl:4805 fkpp:4085 fl:1758 flb:4652 flbg:1694 flbl:6354
flc:1764 flf:5462 flfg:6419 flfl:6405 flfp:4506 flg:1569 flgg:1647 flgk:4716 flgu:6951 flh:1548
flk:8461 flkg:5419 flkk:5916 fll:1675 fllh:1865 fllk:4851 flll:8651 fllq:7651 flp:5471 fm:1546
fmq:1654 fp:8571 fpb:4560 fpbh:2564 fpbk:6941 fpbl:6534 fpc:4591 fpd:4571 fpf:4605 fpfh:4265
fpfl:6245 fpfm:5604 fpfp:5264 fpfq:5640 fpg:4761 fpgg:5691 fpgk:6519 fph:4581 fpk:5698 fpkb:7614
fpkk:6814 fpl:4517 fpld:4518 fplk:5681 fplp:5841 fpp:5617 fppl:6815 fq:0465 fqh:6415 fql:1645
fqp:4516 fu:4561 fuq:6514 g:0157 ga:2643 gac:2893 gad:2683 gag:8293 gah:2483 gak:3928 gakm:9328
gal:6293 gald:4293 gam:2463 gap:3824 gapd:3924 gapg:6329 gaph:9324 gapl:6328 gapm:3428 gaq:3624
gau:3426 gb:0264 gba:3198 gbam:9138 gbb:3148 gbbg:0398 gbbk:0839 gbc:0349 gbcc:0289 gbd:0269
gbdc:0284 gbf:3186 gbfc:2189 gbff:2953 gbfg:2198 gbfh:9136 gbfk:2853 gbfl:6139 gbg:0396
gbgc:0892 gbgf:2168 gbgg:0982 gbgh:0836 gbgk:2169 gbgl:0439 gbh:0286 gbk:2148 gbkc:2196
gbkf:6327 gbkg:2453 gbkh:2186 gbkk:4327 gbkl:4192 gbl:0428 gblg:0692 gbll:0682 gbm:0462 gbp:2146
gc:0437 gca:2069 gcak:6152 gcb:0268 gcbg:2167 gcbl:0852 gcc:6082 gcd:0618 gcf:2468 gcg:0368
gch:0397 gchd:0367 gcl:3147 gd:0357 gf:4813 gfa:6029 gfam:6920 gfb:2793 gfbc:6093 gfbd:2593
gfbf:4620 gfbg:9063 gfbh:5293 gfbk:4920 gfbl:7263 gfbm:7293 gfc:6403 gfcc:6913 gfcg:4273
gfd:0618 gff:3625 gffb:8920 gffc:3729 gffg:6028 gffh:3529 gffl:7326 gffm:6325 gfg:6083 gfgb:5243
gfgc:7283 gfgd:6043 gfgf:9821 gfgg:1693 gfgh:6403 gfgk:1826 gfh:8613 gfk:5374 gfka:1628
gfkb:1924 gfkf:1429 gfkg:7328 gfkk:3528 gfkl:3724 gfl:0463 gflg:1683 gfll:8043 gfm:1843 gfp:1428
gg:0481 gga:2753 ggau:5327 ggb:0395 ggbb:0762 ggbc:0792 ggbcg:0265 ggbd:0295 ggbg:0972 ggbh:0379
ggbhg:0592 ggbl:0739 ggc:0285 ggcb:0691 ggd:0461 ggf:2179 ggfb:3165 ggfc:3176 ggfcg:5139
ggfd:3179 ggff:9053 ggfg:9135 ggfh:2195 ggfhg:7139 ggfk:1953 ggfl:7162 ggfp:1627 ggg:0278
gggb:0916 gggbb:0345 gggc:0538 gggcg:0374 gggd:0274 gggg:0835 gggk:2185 ggh:0641 ggk:2174
ggkb:9106 ggkbb:5138 ggkbm:9160 ggkc:3178 ggkd:3174 ggkf:1853 ggkg:7138 ggkh:8172 ggkhg:7134
ggkp:1827 ggl:0618 ggld:0918 ggm:0418 ggp:4160 ggpd:4190 ggpg:8109 ggph:4109 ggpl:8106 ggpm:4106
ggq:0814 ggu:4108 gh:0418 ghb:0537 ghc:0617 ghf:5137 ghg:0651 ghh:0451 ghk:6107 ghp:4150 gk:5613
gka:4780 gkal:7420 gkap:7028 gkb:7039 gkbb:5028 gkbf:5420 gkbh:7043 gkbl:7403 gkbp:4703
gkbq:7903 gkc:7813 gkcb:5403 gkcc:5803 gkcd:7913 gkcg:5083 gkch:9713 gkd:4815 gkf:1729 gkfb:8520
gkfd:1724 gkfg:7026 gkfh:8721 gkfl:7421 gkg:1793 gkgb:8503 gkgd:1743 gkgf:5821 gkgg:6073
gkgh:1873 gkgk:5921 gkh:4508 gkha:6713 gkk:1485 gkkb:7325 gkkf:6520 gkkl:1528 gkkp:8521 gkl:1485
gkp:1526 gl:0618 glb:0275 glc:0514 glcd:0519 gld:0518 glf:3175 glfp:1527 glg:0471 glgh:0791
glh:0516 glk:7104 glkc:5109 glkd:7109 glkh:4105 glkl:9170 gll:0287 glp:7106 glph:6105 glpl:5160
gm:5107 gmq:0517 gp:5730 gpp:1573 gq:0715 gqq:0571 h:0245 hb:0167 hbc:0138 hbg:0813 hbl:0613
hc:0267 hcc:0283 hf:1728 hfc:1623 hff:6103 hfg:3126 hfh:1823 hfk:0167 hfp:2173 hg:6821 hgb:0327
hgc:0721 hgf:0513 hgg:0326 hgk:0172 hgp:0162 hh:0253 hk:3157 hkb:6120 hkbd:8120 hkf:6023
hkfd:8023 hkg:4103 hkk:7023 hl:0152 hp:4023 k:1462 ka:3057 kac:3098 kad:3058 kag:3890 kagm:3809
kagu:8039 kah:8035 kahp:3807 kak:8309 kakm:8390 kakq:8930 kal:3805 kalg:3790 kalh:3708 kall:3780
kalp:5039 kalq:3580 kalu:5038 kam:5037 kamq:3507 kap:5830 kapc:7930 kapd:7830 kapg:7390
kaph:8730 kapl:7380 kapm:8530 kapp:9305 kaq:3570 kaqq:3705 kaqu:5307 kau:1530 kb:1580 kba:0371
kbag:7392 kbak:7932 kbb:3572 kbbb:3490 kbbc:3982 kbbf:9360 kbbg:3760 kbbh:3782 kbbk:1397
kbc:3578 kbcg:3480 kbd:1570 kbf:5732 kbfc:8932 kbfd:8732 kbff:3069 kbfg:3892 kbfgg:9072
kbfh:7832 kbfk:3407 kbfl:3872 kbfm:5372 kbg:1378 kbgc:1079 kbgd:1398 kbgf:3450 kbgg:1097
kbgh:1938 kbgk:8532 kbgl:1839 kbh:1087 kbhg:1538 kbhl:1750 kbk:8092 kbkc:5072 kbkd:8072
kbkg:5702 kbkh:9052 kbkl:5902 kbl:1098 kblc:1358 kbld:1095 kblg:1705 kblh:1059 kbll:1905
kbm:1085 kbmq:1508 kbp:5802 kbq:1058 kc:1670 kca:3058 kcak:8432 kcb:0582 kcbc:1592 kcbf:1438
kcbg:1892 kcc:0584 kcf:5369 kcff:7432 kcfl:3962 kcg:4308 kcga:1752 kcgb:1369 kcgg:1405 kch:0518
kck:3567 kckb:9062 kcl:1068 kcld:1069 kd:2457 kdf:1862 kdg:1482 kdk:1562 kf:2058 kfa:3719
kfam:3791 kfaq:9317 kfau:7931 kfb:3076 kfbb:3918 kfbc:3049 kfbd:3096 kfbf:9318 kfbg:9034
kfbgf:3718 kfbgg:7019 kfbh:9036 kfbk:7318 kfbkk:2937 kfbl:4037 kfc:9238 kfcb:7018 kfcc:4038
kfcf:3056 kfck:2097 kfd:0157 kff:9306 kffb:8317 kffc:9381 kffcb:7304 kffd:7306 kfff:8731
kfffl:3571 kfffm:7831 kffg:8319 kffgb:4370 kffgk:7901 kffh:3706 kffk:3819 kffkg:7910 kffl:3607
kffm:6309 kffp:3670 kffq:3609 kffu:6930 kfg:2735 kfga:8019 kfgb:8036 kfgc:2790 kfgcf:4035
kfgf:3084 kfgfb:5019 kfgfg:8017 kfgg:9238 kfggb:5034 kfggk:2970 kfgh:2837 kfgk:3718 kfgkf:4350
kfgl:2387 kfgm:2375 kfgp:3259 kfh:2075 kfhg:2538 kfhl:2950 kfk:5630 kfkb:7810 kfkc:5237
kfkcb:4830 kfkf:7801 kfkg:7510 kfkgb:4380 kfkgg:8531 kfkh:4530 kfkk:3295 kfkkf:7501 kfkkg:8315
kfkl:5304 kfkp:3806 kfkq:3605 kfku:6305 kfl:2705 kflc:2385 kflg:2890 kflh:2780 kflk:5238
kfll:2870 kfm:2508 kfmq:2085 kfp:7205 kfpc:3285 kfpg:8501 kfph:7280 kfpk:5810 kfpl:8270 kfq:2580
kfqq:2805 kfu:8205 kg:5602 kga:1834 kgad:1734 kgah:1394 kgal:1347 kgap:3491 kgaq:1348 kgau:3418
kgb:3742 kgbb:8912 kgbc:8712 kgbd:3842 kgbf:1639 kgbg:7812 kgbh:8342 kgbk:1637 kgbl:4382
kgbm:7342 kgc:3762 kgcb:4802 kgcc:4702 kgcf:1609 kgch:3682 kgcl:8632 kgd:7018 kgf:1084 kgfb:1396
kgfc:1287 kgfcb:1354 kgfd:1094 kgff:3761 kgfg:1298 kgfh:1049 kgfk:3861 kgfl:1740 kgfp:7410
kgg:4072 kgga:5361 kggb:6382 kggc:6372 kggd:4082 kggf:1806 kggg:7512 kggh:8042 kggk:5410
kggp:2408 kgh:1507 kghb:6802 kgk:1257 kgka:3064 kgkb:3268 kgkc:1356 kgkd:1258 kgkf:8061
kgkg:1540 kgkh:1285 kgkk:2470 kgl:6573 kglb:6082 kglf:2405 kglk:1650 kgp:7260 kgpd:8260
kgpg:2365 kgph:2860 kgpl:2069 kgq:5260 kgu:2560 kh:1257 khb:1364 khc:1268 khf:2450 khg:1682
khh:1652 khk:8412 khl:1672 khp:5412 kk:5204 kka:3671 kkad:3681 kkah:8631 kkal:6831 kkam:3617
kkap:6318 kkaq:3716 kkau:7316 kkb:7219 kkbb:8314 kkbbk:6238 kkbc:6239 kkbd:8219 kkbf:5631
kkbg:3296 kkbh:7281 kkbk:9601 kkbl:8271 kkbm:7291 kkc:3086 kkca:5271 kkcb:3294 kkcf:7234
kkcg:7206 kkck:6207 kkcl:8206 kkcp:6208 kkd:7084 kkf:6071 kkfb:3841 kkfbl:4931 kkfbm:8341
kkfc:2871 kkfcb:6531 kkfd:6081 kkff:2639 kkffg:2918 kkfg:2781 kkfgc:4731 kkfgg:7341 kkfh:6018
kkfk:2719 kkfkb:3615 kkfkg:2637 kkfl:6810 kkfp:8610 kkfq:7016 kkg:2834 kkga:5016 kkgb:2609
kkgc:2806 kkgd:2934 kkgf:7215 kkgg:4801 kkgh:2394 kkgk:8215 kkgkg:6280 kkgl:4237 kkgp:3247
kkh:2784 kkhp:4207 kkk:4710 kkka:2635 kkkb:2518 kkkc:2715 kkkd:4810 kkkf:2581 kkkfb:2096
kkkg:4036 kkkga:2517 kkkgg:6015 kkkgu:6340 kkkh:4018 kkkk:3046 kkkkc:3541 kkkkg:6051 kkkl:4081
kkkp:8041 kkl:4270 kklc:6250 kkld:4280 kklg:3245 kklh:8240 kklk:2506 kklp:2084 kkm:2504 kkp:4071
kkpf:2650 kkpg:2049 kkpk:2840 kkpl:2047 kkq:4250 kku:2540 kl:2851 klb:2406 klc:2471 kld:2451
klf:4632 klfg:1604 klfk:6410 klfl:4260 klfp:1346 klg:2417 klh:2561 klk:1274 klkd:1294 klkk:6912
klkp:6712 kll:2415 kllp:5261 klp:1245 klpp:5612 km:1642 kmq:1264 kp:2815 kpb:3614 kpbh:6014
kpc:2617 kpch:2714 kpd:2615 kpf:4206 kpfh:3246 kpfk:6341 kpg:4217 kpgc:6219 kpgd:6217 kpgh:7216
kpgp:2671 kph:4215 kpk:4271 kpkd:6271 kpl:6218 kplh:8214 kpp:4251 kppd:4281 kq:1246 kqq:2416
ku:2614 kum:2641 l:0246 lb:7218 lbb:0315 lbc:5213 lbf:0531 lbg:1253 lbk:0731 lbl:1273 lc:2517
lcf:0238 lcg:0218 lck:0281 lcp:0271 ld:0216 lf:3172 lfc:1580 lfcp:3108 lfd:0582 lfg:5018
lfh:5038 lfk:5018 lfkl:1083 lfkp:1803 lfl:2538 lfp:1325 lfpd:1328 lfph:8321 lfpp:2813 lfq:2137
lfu:1327 lg:0738 lgb:0512 lgc:0431 lgcc:0932 lgf:1263 lgg:0361 lggc:0392 lgk:5203 lgkg:3106
lgl:0372 lgp:7203 lh:0214 lk:5820 lkb:3421 lkc:3720 lkcd:1720 lkd:3820 lkf:2613 lkfh:6013
lkfl:2134 lkfu:6132 lkg:1027 lkgd:3027 lkh:1520 lkk:2073 lkl:1054 lklg:8021 lkp:2053 ll:0162
llh:0412 llk:2043 llp:6203 lp:3620 lpd:1620 lpg:4021 lph:3024 lpk:2104 lpl:2160 lpp:2403 m:0132
mq:0321 mqq:3120 p:1246 pb:5290 pbb:1830 pbc:3270 pbd:5230 pbf:1037 pbg:0157 pbh:3250 pbk:1305
pbl:3205 pc:7208 pcb:1235 pcc:1238 pccc:1209 pcf:1036 pcg:1237 pcgc:1290 pcl:1270 pd:1240
pf:3072 pfc:3015 pfcd:3018 pfch:3081 pfd:0258 pfg:3810 pfgd:3910 pfgl:3901 pfgp:5031 pfh:5032
pfhd:8032 pfhl:3802 pfk:5801 pfl:2035 pfld:2038 pflk:3701 pflp:8302 pfm:3702 pfp:2308 pfpd:2309
pfph:2390 pfpl:2530 pfq:2037 pfu:2307 pg:7281 pgb:3041 pgc:5231 pgcd:5201 pgd:3281 pgf:1630
pgfl:2036 pgg:3215 pgh:3271 pgk:1502 pgkc:1932 pgkd:1902 pgkh:1092 pgl:1082 pgp:1372 pgph:1832
ph:1342 phq:3241 pk:2781 pkb:2304 pkbh:4301 pkbk:3061 pkbl:2630 pkc:2051 pkcc:2391 pkcd:2091
pkch:2531 pkd:2701 pkf:3602 pkfg:3014 pkfh:3610 pkfm:6302 pkg:2015 pkgd:2315 pkh:2071 pkk:3512
pkkh:5012 pkl:1082 pkp:1328 pl:6210 plk:1432 pll:2316 plp:1362 plu:1602 pp:2361 ppg:2014
pph:2314 ppl:4312 ppp:3412 q:0134 qh:0231 ql:0312 qp:1320 qpq:1203 u:1302 um:1032 uq:2310
uqq:3012 uu:2031
"""
# <<< ARBOL


def _letra(picas, fijas):
    return LETRAS[5 * picas + fijas]


def _cargar_arbol(texto):
    """'ruta:dddd ruta:dddd ...' -> {ruta: indice de la jugada}. Ignora
    cualquier entrada mal formada en lugar de fallar al importar."""
    arbol = {}
    for token in texto.split():
        ruta, _, jugada = token.partition(":")
        if len(jugada) == LARGO and jugada.isdigit():
            indice = INDICE.get(tuple(int(c) for c in jugada))
            if indice is not None and all(ch in LETRAS for ch in ruta):
                arbol[ruta] = indice
    return arbol


ARBOL = _cargar_arbol(ARBOL_TEXTO)


# =============================================================================
#  Agente
# =============================================================================

# Nombre con el que aparece el agente en el desplegable del ambiente. El
# ambiente usa la clave del modulo, y "&" no es valido en un identificador de
# Python, asi que la clase se publica al final con globals()[NOMBRE_AGENTE].
NOMBRE_AGENTE = "AgenteJJ&S"


class _AgenteJJyS:
    """Agente para Picas y Fijas: arbol optimizado + busqueda de respaldo."""

    # Apertura. Todas las aperturas son equivalentes (renombrar digitos
    # convierte una en otra); el arbol esta calculado para esta.
    PRIMER_INTENTO = (0, 1, 2, 3)

    # Poner en False para jugar solo con la busqueda en linea (comparaciones).
    USAR_ARBOL = True

    def __init__(self):
        self._rng = random.Random(int.from_bytes(os.urandom(16), "big"))
        self.secret = []
        self.start()
        _registrar_en_interfaz(type(self))

    # ------------------------------------------------------------------ #
    #  1) Inicio de ronda
    # ------------------------------------------------------------------ #
    def start(self):
        """Resetea todo lo aprendido. Tambien deja un secreto propio valido
        en `self.secret` (este ambiente no lo usa)."""
        iniciales = range(BASE) if SECRETO_PERMITE_CERO_INICIAL else range(1, BASE)
        primero = self._rng.choice(iniciales)
        resto = self._rng.sample([d for d in range(BASE) if d != primero], LARGO - 1)
        self.secret = [int(d) for d in [primero] + resto]

        self._mascara = MASCARA_TOTAL     # codigos que aun pueden ser el secreto
        self._ruta = ""                   # letras de las respuestas; None = fuera del arbol
        self._historia = []               # [(indice_jugada, (picas, fijas))]
        self._ultima_jugada = None        # jugada que espera respuesta
        self._jugadas_hechas = set()
        self.resuelto = False
        return self.secret

    # ------------------------------------------------------------------ #
    #  2) Intento del turno
    # ------------------------------------------------------------------ #
    def try_attempt(self):
        """Devuelve el intento del turno: lista de 4 enteros unicos 0..9."""
        try:
            indice = self._elegir_jugada()
        except Exception:
            libres = [i for i in _indices(self._mascara) if i not in self._jugadas_hechas]
            indice = libres[0] if libres else self._rng.randrange(N_CODIGOS)
        self._ultima_jugada = indice
        self._jugadas_hechas.add(indice)
        return [int(d) for d in CODIGOS[indice]]

    # ------------------------------------------------------------------ #
    #  3) Retroalimentacion del juez
    # ------------------------------------------------------------------ #
    def feedBack(self, retroalimentacionLista):
        """Filtra los candidatos con la respuesta [picas, fijas] del juez."""
        try:
            respuesta = _normalizar_respuesta(retroalimentacionLista)
            indice = self._ultima_jugada
            self._ultima_jugada = None
            if respuesta is None or indice is None:
                return
            picas, fijas = respuesta
            if fijas == LARGO:
                self.resuelto = True
                self._mascara = 1 << indice
                return

            self._historia.append((indice, respuesta))
            nueva = _refinar(self._mascara, indice, picas, fijas)
            if self._ruta is not None:
                self._ruta += _letra(picas, fijas)
            if not nueva:                  # respuestas contradictorias
                nueva = self._recuperar()
                self._ruta = None          # el arbol ya no describe la partida
            self._mascara = nueva
        except Exception:
            self._ruta = None

    def receive_feedback(self, picas, fijas):
        """Nombre que usa AdaptadorUniversal del ambiente nuevo."""
        return self.feedBack([picas, fijas])

    # ------------------------------------------------------------------ #
    #  Compatibilidad con el ambiente anterior (agentes que se evaluan)
    # ------------------------------------------------------------------ #
    def discover(self, numeroLista):
        """[picas, fijas] honestas del intento del rival contra `self.secret`."""
        try:
            intento = _normalizar_numero(numeroLista)
            if intento is None:
                return [0, 0]
            picas, fijas = _evaluar(intento, self.secret)
            return [int(picas), int(fijas)]
        except Exception:
            return [0, 0]

    # ------------------------------------------------------------------ #
    #  Nucleo de decision
    # ------------------------------------------------------------------ #
    def _elegir_jugada(self):
        conjunto = self._mascara
        if not conjunto:
            self._mascara = conjunto = MASCARA_TOTAL
            self._ruta = None
        hechas = self._jugadas_hechas

        # (a) Apertura fija.
        if not self._historia and self._ruta == "":
            indice = INDICE[tuple(self.PRIMER_INTENTO)]
            if indice not in hechas:
                return indice

        # (b) Arbol precalculado.
        if self.USAR_ARBOL and self._ruta is not None:
            indice = ARBOL.get(self._ruta)
            if indice is not None and indice not in hechas:
                return indice

        candidatos = _indices(conjunto)

        # (c) 1 o 2 candidatos: jugar uno (gana ya o en el turno siguiente).
        if len(candidatos) <= 2:
            for i in candidatos:
                if i not in hechas:
                    return i
            return candidatos[0]

        # (d) Busqueda en linea: minimiza el numero esperado de candidatos
        #     restantes; desempata por peor caso y por jugada candidata.
        mejor_indice, mejor_clave = candidatos[0], None
        for indice in range(N_CODIGOS):
            if indice in hechas:
                continue
            suma_cuadrados, peor = _estadisticas(indice, conjunto)
            clave = (suma_cuadrados, peor, 0 if (conjunto >> indice) & 1 else 1)
            if mejor_clave is None or clave < mejor_clave:
                mejor_clave, mejor_indice = clave, indice
        return mejor_indice

    def _recuperar(self):
        """Respuestas contradictorias: se descartan las restricciones mas
        antiguas hasta volver a tener candidatos."""
        historia = self._historia
        for descarte in range(1, len(historia) + 1):
            mascara = MASCARA_TOTAL
            for indice, (picas, fijas) in historia[descarte:]:
                mascara = _refinar(mascara, indice, picas, fijas)
                if not mascara:
                    break
            if mascara:
                self._historia = historia[descarte:]
                return mascara
        self._historia = []
        return MASCARA_TOTAL

    def __repr__(self):
        return "<AgenteJJ&S candidatos=%d ruta=%r>" % (_popcount(self._mascara), self._ruta)


def _alias_try(self):
    """Metodo literal `try` que menciona el reglamento. No puede declararse con
    `def try(...)` porque es palabra reservada de Python."""
    return self.try_attempt()


setattr(_AgenteJJyS, "try", _alias_try)


# =============================================================================
#  Herencia de la interfaz del ambiente
# =============================================================================

def _buscar_interfaz():
    """`interfazAgente` tal como la definio el notebook (sus celdas viven en
    __main__) o un modulo aparte; None si no existe."""
    for nombre_modulo in ("__main__", "builtins", "Ambiente", "interfaz", "interfazAgente"):
        base = getattr(sys.modules.get(nombre_modulo), "interfazAgente", None)
        if isinstance(base, ABCMeta):
            return base
    return None


def _registrar_en_interfaz(clase):
    """Respaldo si la interfaz se define DESPUES de importar este archivo:
    registra la clase como subclase virtual (issubclass/isinstance dan True)."""
    base = _buscar_interfaz()
    if base is not None and not issubclass(clase, base):
        try:
            base.register(clase)
        except Exception:
            pass


def _heredar_de_interfaz(clase):
    """Si `interfazAgente` ya existe al importar, la clase publica HEREDA de
    ella (aparece en __mro__). Si la interfaz exigiera un metodo que el agente
    no tiene, se usa la clase normal registrada como subclase virtual, para no
    provocar un TypeError al instanciar."""
    base = _buscar_interfaz()
    if base is None or base in clase.__mro__:
        return clase
    try:
        nueva = type(base)(clase.__name__, (clase, base), {
            "__module__": clase.__module__,
            "__qualname__": clase.__qualname__,
            "__doc__": clase.__doc__,
        })
        if not getattr(nueva, "__abstractmethods__", None):
            return nueva
    except Exception:
        pass
    _registrar_en_interfaz(clase)
    return clase


_AgenteJJyS.__name__ = _AgenteJJyS.__qualname__ = NOMBRE_AGENTE
globals()[NOMBRE_AGENTE] = _heredar_de_interfaz(_AgenteJJyS)

# Nota: no se exportan alias de la clase (por eso se borra _AgenteJJyS). El
# ambiente nuevo lista en su desplegable CADA clase del modulo, y los alias
# aparecerian repetidos.
del _AgenteJJyS


# =============================================================================
#  Autoprueba: los 5040 secretos posibles
# =============================================================================

if __name__ == "__main__":
    import time
    from collections import Counter

    Agente = globals()[NOMBRE_AGENTE]
    inicio = time.time()
    turnos = []
    for secreto in CODIGOS:
        agente = Agente()
        agente.start()
        for turno in range(1, 30):
            intento = agente.try_attempt()
            assert isinstance(intento, list) and len(set(intento)) == 4, intento
            picas, fijas = _evaluar(intento, secreto)
            agente.feedBack([picas, fijas])
            if fijas == 4:
                turnos.append(turno)
                break
    duracion = time.time() - inicio
    cuenta = Counter(turnos)
    print("Secretos probados : %d (todos)" % len(turnos))
    print("Turnos promedio   : %.4f" % (sum(turnos) / len(turnos)))
    print("Peor caso         : %d" % max(turnos))
    print("Distribucion      : %s" % dict(sorted(cuenta.items())))
    print("Tiempo por ronda  : %.2f ms" % (1000.0 * duracion / len(turnos)))
