# -*- coding: utf-8 -*-
"""sim_bosses.py — "그 막 끝에 있을 법한 덱"으로 보스·중간보스 승률만 따로 잰다.

sim_tune.py 의 전 구간 완주율은 그리디 AI의 누적 실수가 곱해져 낮게 나온다.
보스 개별 난도를 보려면 덱을 고정해 놓고 그 전투만 반복하는 편이 정확하다.

사용:  python sim_bosses.py            # 기본 400판
       python sim_bosses.py --n 800
"""
import argparse, random, sys
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
import sim_battle_v2 as S

# 막 끝 기준 덱 — v0.32 맵 10행(관문 12), 전투 약 6회 기대 (막당 카드 수 하향)
FOCUS = {1: ['ursa', 'cassiopeia', 'canis'], 2: ['sagittarius', 'lyra'], 3: ['orion', 'virgo']}


def con_pool(k):
    return [cid for cid, v in S.STARS.items() if v['con'] == k]


def build_deck(act, rng, fuse_pairs, up_n, ncards=5):
    """주극 12장에서 시작해 막마다 집중 별자리 카드를 붙이고 합성·강화를 섞는다"""
    deck = [{'id': c, 'up': False} for c in S.D['POLAR_DECK']]
    for a in range(1, act + 1):
        for k in FOCUS[a]:
            pool = sorted(con_pool(k))
            rng.shuffle(pool)
            for cid in pool[:ncards]:
                deck.append({'id': cid, 'up': False})
    for _ in range(up_n):
        cands = [i for i, c in enumerate(deck) if not c.get('up') and not c.get('id2')]
        if cands:
            deck[rng.choice(cands)]['up'] = True
    # 대장간 — 같은 별자리끼리 묶는다
    for _ in range(fuse_pairs):
        groups = {}
        for i, c in enumerate(deck):
            if not c.get('id2'):
                groups.setdefault(S.STARS[c['id']]['con'], []).append(i)
        cand = [g for g in groups.values() if len(g) >= 2 and S.CONS[S.STARS[deck[g[0]]['id']]['con']]['need'] >= 3]
        if not cand:
            cand = [g for g in groups.values() if len(g) >= 2]
        if not cand:
            break
        g = rng.choice(cand)
        ia, ib = g[0], g[1]
        A, B = deck[ia], deck[ib]
        deck = [c for i, c in enumerate(deck) if i not in (ia, ib)]
        deck.append({'id': A['id'], 'up': A.get('up', False), 'id2': B['id'], 'up2': B.get('up', False)})
    return deck


def fight(deck, foe, act, n, rng, hp=70, relics=(), allies=()):
    w, turns = 0, []
    for _ in range(n):
        s = S.Sim(list(deck), [foe], act=act, hp=hp, season_off=rng.randrange(4),
                  relics=relics, allies=allies, rng=rng)
        if s.run():
            w += 1
        turns.append(s.turn)
    return w / n * 100, sum(turns) / len(turns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=400)
    a = ap.parse_args()
    rng = random.Random(20260809)   # 덱 구성용
    setups = [
        (1, 'pleiades', '플레이아데스(1막 중간)'),
        (1, 'hyades', '히아데스(1막 중간)'),
        (1, 'm42', 'M42(1막 보스)'),
        (2, 'm1', 'M1(2막 중간)'),
        (2, 'm13', 'M13(2막 중간)'),
        (2, 'blackhole', '블랙홀(2막 보스)'),
        (3, 'm31', 'M31(3막 중간)'),
        (3, 'quasar', '퀘이사(3막 중간)'),
        (3, 'darkmatter', '암흑 물질(3막 보스)'),
    ]
    # 막이 오를수록 덱·유물·조력자가 함께 자란다.
    # 중간보스는 **막 중반** 덱으로, 보스는 **막 끝** 덱으로 재야 실제 조우 시점과 맞는다.
    # v0.30: 휴식 합성 폐지 → 합성 기회 = 막당 대장간 1(경로 확률 ~1/3, 플레이어가 길을 고르므로 상향) + 2막 이벤트
    #        구 가정 fuse 3/5/7(END)·1/3/5(MID)은 휴식 합성 시대 수치 — 1/2/3·0/1/2로 하향 (밸런스로그 19차)
    END = {1: dict(fuse=1, up=3, cards=4, relics=['compass', 'ember'], allies=['brahe'], hp=62),
           2: dict(fuse=2, up=6, cards=4, relics=['compass', 'ember', 'orrery', 'lens'],
                   allies=['brahe', 'kepler'], hp=60),
           3: dict(fuse=3, up=10, cards=4, relics=['compass', 'ember', 'orrery', 'lens', 'galaxylens', 'polarshard'],
                   allies=['brahe', 'kepler', 'herschel'], hp=58)}
    MID = {1: dict(fuse=0, up=1, cards=3, relics=['compass'], allies=['brahe'], hp=52),
           2: dict(fuse=1, up=4, cards=3, relics=['compass', 'ember', 'orrery'], allies=['brahe', 'kepler'], hp=50),
           3: dict(fuse=2, up=8, cards=4, relics=['compass', 'ember', 'orrery', 'lens', 'galaxylens'],
                   allies=['brahe', 'kepler', 'herschel'], hp=50)}
    print('[조우 시점에 맞춘 덱으로 잰 승률 — 그리디 AI라 하한선]')
    for act, foe, label in setups:
        boss = S.ENEMIES[foe].get('boss')
        p = (END if boss else MID)[act]
        deck = build_deck(act, random.Random(4242 + act), p['fuse'], p['up'], p['cards'])
        wr, t = fight(deck, foe, act, a.n, random.Random(777), hp=p['hp'], relics=p['relics'], allies=p['allies'])
        print(f'  {label:22s} 승률 {wr:5.1f}%  평균 {t:4.1f}턴   (덱 {len(deck)}장 HP {p["hp"]})')


if __name__ == '__main__':
    main()
