# -*- coding: utf-8 -*-
"""
sim_tune.py — 밸런스 튜닝 실험대 (sim_battle_v2 위에서 레버를 켜고 끄며 비교)

레버
  reward   : 'card'(개별 3택1, 구방식) | 'con'(별자리 3택1 → 그 별자리 카드 N장, v0.19 사용자 지시)
  needcut  : 3성 → 2성으로 낮출 별자리 목록
  m42      : 1막 보스 격노/아머 조정 배수
  act2     : 2막 적 전체 스케일
  potions  : 막당 사용하는 회복 물약 수 (시뮬이 아이템을 무시해 생기는 비관 보정)

실행: python sim_tune.py            # 표준 비교표
     python sim_tune.py --final    # 채택안만 크게 돌려 최종 수치 확인
"""
import argparse, copy, random, sys
from collections import defaultdict, Counter
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
import sim_battle_v2 as S

BY_CON = defaultdict(list)
for _cid, _v in S.STARS.items():
    BY_CON[_v['con']].append(_cid)
BASE_CONS = copy.deepcopy(S.CONS)
BASE_ENEM = copy.deepcopy(S.ENEMIES)

# 완성이 사실상 불가능하다고 측정된 3성 별자리 (카드 5~6장 규모)
NEEDCUT = ['taurus', 'leo', 'virgo', 'scorpius', 'pegasus', 'andromeda',
           'sagittarius', 'perseus', 'draco', 'cygnus']
# 필요 수를 낮추면 보너스가 싸지므로 큰 것만 소폭 하향
TRIM = {'taurus': {'v': 8}, 'leo': {'v': 6}, 'virgo': {'mana': 1, 'heal': 4},
        'scorpius': {'v': 2}, 'pegasus': {'mana': 1}, 'andromeda': {'v': 5},
        'sagittarius': {'v': 7}, 'perseus': {'v': 9}, 'draco': {'v': 5, 'burn': 2},
        'cygnus': {'block': 6}}


TAKE_MAX = 22      # v0.25: 사람 대신 쓰는 어림 규칙 — 덱이 이만큼 넘으면 새 별자리 카드는 담지 않는다


def apply(cfg):
    for k, v in BASE_CONS.items():
        S.CONS[k].clear(); S.CONS[k].update(copy.deepcopy(v))
    for k, v in BASE_ENEM.items():
        S.ENEMIES[k].clear(); S.ENEMIES[k].update(copy.deepcopy(v))
    if cfg.get('needcut'):
        for k in NEEDCUT:
            S.CONS[k]['need'] = 2
        if cfg.get('trim'):
            for k, p in TRIM.items():
                S.CONS[k]['bonus'].update(p)
    m = cfg.get('m42')
    if m:
        S.ENEMIES['m42'].update(m)
    global TAKE_MAX
    TAKE_MAX = cfg.get('takemax', 22)
    ms = cfg.get('mobscale', 1.0)
    if ms != 1.0:
        for k, e in S.ENEMIES.items():
            if e.get('boss') or e.get('elite') or k in ('babystar', 'asteroid', 'satgal'):
                continue
            e['hp'] = max(1, int(round(e['hp'] * ms)))
            e['atk'] = max(1, int(round(e['atk'] * ms)))
            if 'pattern' in e:
                e['pattern'] = [max(1, int(round(x * ms))) for x in e['pattern']]
    rh = cfg.get('resth')
    sc = cfg.get('allscale', 1.0)
    if sc != 1.0:
        for k, e in S.ENEMIES.items():
            if k in ('babystar', 'asteroid', 'satgal'):
                continue
            e['hp'] = max(1, int(e['hp'] * sc))
            e['atk'] = max(1, int(e['atk'] * sc))
            if 'pattern' in e:
                e['pattern'] = [max(1, int(x * sc)) for x in e['pattern']]
            if 'act1' in e:
                e['act1'] = {'hp': int(e['act1']['hp'] * sc), 'atk': max(1, int(e['act1']['atk'] * sc))}
    a2 = cfg.get('act2', 1.0)
    if a2 != 1.0:
        for k in ['uranus', 'neptune', 'pluto', 'titan', 'io', 'rogue', 'oort', 'm1', 'm13', 'blackhole']:
            e = S.ENEMIES[k]
            e['hp'] = int(e['hp'] * a2)
            e['atk'] = max(1, int(e['atk'] * a2))
            if 'pattern' in e:
                e['pattern'] = [max(1, int(x * a2)) for x in e['pattern']]
            if 'defend' in e:
                e['defend'] = dict(e['defend'], v=max(1, int(e['defend']['v'] * a2)))


GRADE_V = {1: 3, 2: 2.2, 3: 1.4, 4: 0.7, 5: 0}    # v0.25: rank 1(α)이 가장 높다


def card_value(cid):
    """정적 카드 가치 (물질 환산) — 플레이어가 '좋은 카드 2장'을 고르는 것을 흉내낸다.
    구버전은 별자리 안에서 무작위 2장을 집어 실제 플레이보다 덱 품질을 과소평가했다."""
    d = S.STARS[cid]
    v = 0.0
    for f in d['fx']:
        t = f['t']
        if t in ('dmg', 'dmgExec', 'dmgKill', 'dmgPerCon', 'dmgRand'):
            v += f['v'] / 6.0 * (1.2 if f.get('pierce') else 1.0)
        elif t == 'dmgMulti':
            v += f['v'] * f['n'] / 6.0
        elif t in ('aoe',):
            v += f['v'] * 1.4 / 6.0
        elif t == 'aoeBurn':
            v += f['v'] * 2.4 / 6.0
        elif t in ('block', 'blockPerCon'):
            v += f['v'] / 5.0
        elif t in ('varDmg', 'varBlock'):
            v += sum(f['opts']) / len(f['opts']) / 5.5
        elif t == 'draw':
            v += .45 * f['n']
        elif t == 'mana':
            v += f['v']
        elif t == 'heal':
            v += f['v'] * .21
        elif t == 'poison':
            v += f['v'] * (f['v'] + 1) / 12.0
        elif t == 'burn':
            v += f['v'] * 2 / 6.0
        elif t == 'weak':
            v += .45 * f['n']
        elif t == 'vuln':
            v += .6 * f['n']
        elif t == 'thorns':
            v += f['v'] * .15
        elif t in ('buffAtk', 'buffDef'):
            v += f['v'] / 8.0
        elif t in ('power', 'powerAtk'):
            v += f['v'] * .55
        elif t == 'seal':
            v += 1.5
        elif t == 'needDown':
            v += .8
        elif t == 'halfBlockDmg':
            v += 1.0
        elif t.startswith('sac'):
            v += .4
    return v - d['cost'] * 0.9 + GRADE_V.get(d.get('rank', 5), 0) * 0.05


GRADE_W = {1: 0.16, 2: 0.34, 3: 0.60, 4: 0.85, 5: 1.0}   # v0.25 빌드와 동일 (α가 가장 드물다)


def wpick(ids, rng, exclude=()):
    pool = [i for i in ids if i not in exclude] or list(ids)
    tot = sum(GRADE_W.get(S.STARS[i].get('rank', 5), 1) for i in pool)
    r = rng.random() * tot
    for i in pool:
        r -= GRADE_W.get(S.STARS[i].get('rank', 5), 1)
        if r <= 0:
            return i
    return pool[-1]


def con_reward(deck, rng, n):
    """v0.24: 별자리 3택1 → **그 별자리에서 희귀도 가중 무작위 n장을 전부 획득**(고르는 단계 없음).
    3택1 제안은 지금 계절 별자리에 가중치가 붙는다(제철 ×3 · 역철 ×0.5 · 주극 ×1.2)."""
    all_k = list(S.CONS.keys())
    cnt = Counter(S.STARS[S.norm(c)['id']]['con'] for c in deck)
    # v0.25: 3택 중 **둘**이 이미 모으던 별자리에서 나온다
    owned = [k for k in all_k if cnt[k]]
    rng.shuffle(owned)
    offer = owned[:2]
    while len(offer) < 3:
        k = rng.choice(all_k)
        if k not in offer:
            offer.append(k)
    def key(k):
        have = cnt[k]
        return (1 if have else 0, -abs(S.CONS[k]['need'] * 3 - have), have, rng.random())
    pick = max(offer, key=key)
    got, out = [], []
    for _ in range(n):
        cid = wpick(BY_CON[pick], rng, got)
        got.append(cid)
        # v0.25: 뽑힌 3장 중 **원하는 만큼만** 담는다.
        # 사람 대신 쓰는 어림 규칙 — 이미 모으던 별자리면 담고, 아니면 덱이 작을 때만 담는다.
        if TAKE_MAX is None or cnt[S.STARS[cid]['con']] or len(deck) + len(out) < TAKE_MAX:
            out.append({'id': cid, 'up': False})
    return out


def card_reward(deck, rng):
    picks = [S.roll_reward(rng, deck) for _ in range(3)]
    return [(S.pick_reward(deck, picks, rng), False)]


def try_forge(deck):
    """같은 별자리 중 값어치 높은 두 장을 합쳐 2성 카드로 (없으면 None)"""
    groups = {}
    for i, c in enumerate(deck):
        c = S.norm(c)
        if c.get('id2'):
            continue
        groups.setdefault(S.STARS[c['id']]['con'], []).append(i)
    best = None
    for con, idxs in groups.items():
        if len(idxs) >= 2:
            idxs = sorted(idxs, key=lambda i: -card_value(S.norm(deck[i])['id']))[:2]
            sc = card_value(S.norm(deck[idxs[0]])['id']) + card_value(S.norm(deck[idxs[1]])['id'])
            sc += 1.5 if S.CONS[con]['need'] >= 3 else 0     # 3성 별자리를 우선 합성
            if best is None or sc > best[0]:
                best = (sc, idxs)
    if not best:
        return None
    ia, ib = best[1]
    A, B = S.norm(deck[ia]), S.norm(deck[ib])
    out = [c for i, c in enumerate(deck) if i not in (ia, ib)]
    out.append({'id': A['id'], 'up': A.get('up', False), 'id2': B['id'], 'up2': B.get('up', False)})
    return out


def sim_act(act, deck, hp, relics, allies, rng, stats, cfg):
    season_off = rng.randrange(4)
    potions = cfg.get('potions', 2)
    # v0.21: 막당 13행(관문 15) · 특수 노드 = 상점3·휴식5·이벤트4·대장간1 / 중간보스 3
    for r in range(13):
        if r == 0:
            kind = 'battle'
        else:
            x = rng.random()
            kind = ('battle' if x < .556 else 'elite' if x < .639 else 'rest' if x < .778
                    else 'event' if x < .889 else 'shop' if x < .972 else 'forge')
        if kind in ('battle', 'elite'):
            tier = 'easy' if r <= 2 else 'normal' if r <= 8 else 'hard'
            foes = [rng.choice(S.ELITES[act])] if kind == 'elite' else list(rng.choice(S.ENC[act][tier]))
            s = S.Sim(deck, foes, act=act, hp=hp, season_off=season_off,
                      relics=relics, allies=allies, rng=rng)
            won = s.run()
            S.merge_stats(stats, s, act)
            if not won:
                if potions > 0 and hp > 25:        # 물약으로 한 번은 버틴다고 보정
                    potions -= 1
                    hp = min(70, hp + 15)
                    continue
                return None, hp
            hp = s.hp
            if kind == 'elite':
                pool = [x for x in S.D['RELICS'] if x not in relics and not S.D['RELICS'][x].get('boss')]
                if pool:
                    relics.add(rng.choice(pool))
            deck.extend(con_reward(deck, rng, cfg['ncards']) if cfg['reward'] == 'con' else card_reward(deck, rng))
        elif kind == 'forge':
            deck = try_forge(deck) or deck
        elif kind == 'rest':
            if try_forge(deck) is not None and hp >= 40:
                deck = try_forge(deck)
            elif hp < 50:
                hp = min(70, hp + cfg.get('resth', 30))
            else:
                j = rng.randrange(len(deck))
                _c = S.norm(deck[j])
                if not _c.get('id2'):
                    deck[j] = {'id': _c['id'], 'up': True}
        elif kind == 'event':
            if rng.random() < .5:
                hp = min(70, hp + 10)
            else:
                potions += 1
        else:
            deck.extend(con_reward(deck, rng, 1) if cfg['reward'] == 'con' else card_reward(deck, rng))
    hp = min(70, hp + 30 + (10 if 'waterjar' in relics else 0))   # 보스 전 고정 휴식 노드 (빌드: rest 30)
    s = S.Sim(deck, [S.BOSS[act]], act=act, hp=hp, season_off=season_off,
              relics=relics, allies=allies, rng=rng)
    won = s.run()
    S.merge_stats(stats, s, act)
    stats['boss_turns'][act].append(s.turn)
    return (deck, s.hp) if won else (None, s.hp)


def trial(label, cfg, n=400, seed=5, show=False):
    apply(cfg)
    cfg.setdefault('ncards', 3)
    cfg.setdefault('reward', 'con')
    rng = random.Random(seed)
    st = {'comp': defaultdict(int), 'had': defaultdict(int), 'turns': [], 'boss_turns': defaultdict(list)}
    a1 = a2 = a3 = reach = 0
    decks = []
    for _ in range(n):
        deck = [{'id': c, 'up': False} for c in (cfg.get('startdeck') or S.D['POLAR_DECK'])]
        allies = [rng.choice(list(S.D['COMPANIONS']))]
        relics = set()
        d2, hp = sim_act(1, deck, 70, relics, allies, rng, st, cfg)
        if d2 is None:
            continue
        a1 += 1; reach += 1; decks.append(len(d2))
        bp = [r for r in S.D['RELICS'] if S.D['RELICS'][r].get('boss')]
        if bp:
            relics.add(rng.choice(bp))
        p2 = [c for c in S.D['COMPANIONS'] if c not in allies]
        if p2:
            allies.append(rng.choice(p2))
        d3, hp3 = sim_act(2, d2, min(70, hp + 22), relics, allies, rng, st, cfg)
        if d3 is not None:
            a2 += 1
            p3 = [c for c in S.D['COMPANIONS'] if c not in allies]
            if p3:
                allies.append(rng.choice(p3))
            d4, _ = sim_act(3, d3, min(70, hp3 + 22), relics, allies, rng, st, cfg)
            if d4 is not None:
                a3 += 1
    dk = sum(decks) / len(decks) if decks else 0
    bt = st['boss_turns']
    print(f'{label:26s} 1막 {a1/n*100:5.1f}%  2막 {a2/max(1,a1)*100:5.1f}%  3막 {a3/max(1,a2)*100:5.1f}%  '
          f'(완주 {a3/n*100:4.1f}%)  덱 {dk:4.0f}장  '
          f'보스전 {sum(bt[1])/max(1,len(bt[1])):4.1f}/{sum(bt[2])/max(1,len(bt[2])):4.1f}/{sum(bt[3])/max(1,len(bt[3])):4.1f}턴')
    if show:
        rows = sorted(((st['comp'][k] / st['had'][k] if st['had'][k] else 0), S.CONS[k]['name'], S.CONS[k]['need'])
                      for k in S.CONS)
        print('   완성률 하위: ' + ', '.join(f'{nm}({nd}) {r*100:.0f}%' for r, nm, nd in rows[:6]))
        print('   완성률 상위: ' + ', '.join(f'{nm}({nd}) {r*100:.0f}%' for r, nm, nd in rows[-4:]))
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--final', action='store_true')
    ap.add_argument('--n', type=int, default=400)
    ap.add_argument('--diff', action='store_true')
    ap.add_argument('--supply', action='store_true')
    ap.add_argument('--start', action='store_true')
    a = ap.parse_args()
    if a.final:
        # v0.21 출시 구성 = 빌드 데이터 그대로 (needcut·trim·보스 보정 전부 끔)
        trial('v0.25 출시 구성', dict(reward='con', ncards=3), n=a.n * 2, show=True)
        return
    if a.start:
        base = list(S.D['POLAR_DECK'])
        d10 = base + ['caph']
        d12 = base + ['caph', 'merak', 'kochab']
        print('── v0.25 시작 덱 크기 ──')
        trial('9장 (현행)', dict(reward='con', ncards=3), n=a.n, show=True)
        trial('10장', dict(reward='con', ncards=3, startdeck=d10), n=a.n)
        trial('12장', dict(reward='con', ncards=3, startdeck=d12), n=a.n, show=True)
        return
    if a.supply:
        print('── v0.25 카드 수급: 담기 정책 ──')
        trial('전부 담기(구 v0.24식)', dict(reward='con', ncards=3, takemax=None), n=a.n, show=True)
        for t in (18, 22, 28, 34):
            trial('덱 %d장까지 담기' % t, dict(reward='con', ncards=3, takemax=t), n=a.n, show=(t == 28))
        return
    if a.diff:
        print('── v0.21 난이도 레버 ──')
        for k in (1.0, 0.9, 0.82, 0.75):
            trial('쫄몹 %.2f배' % k, dict(reward='con', ncards=2, mobscale=k), n=a.n)
        for k in (0.9, 0.82):
            trial('쫄몹 %.2f배 + 휴식25' % k, dict(reward='con', ncards=2, mobscale=k, resth=25), n=a.n)
        trial('쫄몹 0.82 + 휴식25 + 3장', dict(reward='con', ncards=3, mobscale=0.82, resth=25), n=a.n)
        return
    print('── 카드 수급 방식 ──')
    trial('구방식(개별 카드 3택1)', dict(reward='card'), n=a.n)
    trial('별자리 3택1 → 1장', dict(reward='con', ncards=1), n=a.n)
    trial('별자리 3택1 → 2장', dict(reward='con', ncards=2), n=a.n, show=True)
    trial('별자리 3택1 → 3장', dict(reward='con', ncards=3), n=a.n)
    print('── 성좌 필요 수 ──')
    trial('+ need컷', dict(reward='con', ncards=2, needcut=True), n=a.n)
    trial('+ need컷 + 보너스 하향', dict(reward='con', ncards=2, needcut=True, trim=True), n=a.n, show=True)
    print('── 보스·2막 ──')
    trial('+ M42 격노 완화', dict(reward='con', ncards=2, needcut=True, trim=True,
                              m42={'defend': {'every': 4, 'v': 10}}), n=a.n)
    trial('+ 2막 0.85', dict(reward='con', ncards=2, needcut=True, trim=True,
                           m42={'defend': {'every': 4, 'v': 10}}, act2=0.85), n=a.n)
    trial('+ 2막 0.8', dict(reward='con', ncards=2, needcut=True, trim=True,
                          m42={'defend': {'every': 4, 'v': 10}}, act2=0.8), n=a.n)


if __name__ == '__main__':
    main()
