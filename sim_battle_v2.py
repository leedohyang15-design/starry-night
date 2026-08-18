# -*- coding: utf-8 -*-
"""
sim_battle_v2.py — Starry Night 밸런스 시뮬레이터 v2 (2026-08-09)

v1(52종·전투 누적 규칙) 폐기 후 재작성. 현행 규칙을 재현한다:
  · 별 150종 / 별자리 26개 · 성좌 완성 = **한 턴** 기준 · 발동 = **턴당 성좌마다 1회**
  · 계절: 1막 = 보정 없음 / 2막 = 턴마다 봄→여름→가을→겨울 (제철 +25% 올림 / 역철 −25% 내림, 주극 무보정)
  · 적 아머(성막)와 관통·중독·화상의 아머 무시, 블랙홀의 중력(다음 턴 물질 −1)
  · 마나 3 / 드로우 5 / HP 70, 물질 이월 최대 2(v0.46), 미자르-알코르 2성 계산, 알페라츠 겸용

데이터는 빌드 HTML에서 그대로 떠낸 sim_data_v019.json 사용 (node dump_sim_data.js).

실행:
  python sim_battle_v2.py --runs 300            # 1막+2막 완주 시뮬 (승률·완성률)
  python sim_battle_v2.py --cons 2000           # 성좌 완성 난도만 측정 (별자리별)
  python sim_battle_v2.py --validate            # 규칙 검산 시나리오
"""
import argparse, json, math, os, random, sys
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, 'sim_data_v025.json'), encoding='utf-8'))   # 저장소에 있는 최신 덤프 (v0.25~29 데이터 동일)
STARS, CONS, ENEMIES = D['STARS'], D['CONSTELLATIONS'], D['ENEMIES']
SEASONS, OPP = D['SEASONS'], D['OPP']
ENC = {3: {'easy': D['ENC3_EASY'], 'normal': D['ENC3_NORMAL'], 'hard': D['ENC3_HARD']},
       1: {'easy': D['ENC_EASY'], 'normal': D['ENC_NORMAL'], 'hard': D['ENC_HARD']},
       2: {'easy': D['ENC2_EASY'], 'normal': D['ENC2_NORMAL'], 'hard': D['ENC2_HARD']}}
ELITES = {1: D['ELITES'], 2: D['ELITES2'], 3: D['ELITES3']}
BOSS = {1: 'm42', 2: 'blackhole', 3: 'darkmatter'}
DAWN = {3: {'from': 14, 'dmg': 3, 'step': 2}}   # v0.21 3막 — 여명(성막 무시 누적 피해)


# ═════════════════ 카드 데이터 ═════════════════
def up_data(cid):
    """빌드의 강화 일괄 규칙 재현 (UP_COST_ONLY / 수치형 +25% / 약화·취약 +1턴 / 비용 −1)"""
    d = json.loads(json.dumps(STARS[cid]))
    if cid in D['UP_COST_ONLY']:
        d['cost'] = max(0, d['cost'] - 1); return d
    done = False
    for f in d['fx']:
        if f['t'] in D['UP_NUM']:
            f['v'] = math.ceil(f['v'] * 1.25); done = True
        elif f['t'] == 'dmgMulti':
            f['plus'] = math.ceil(f['v'] * f['n'] * 0.25); done = True
        elif f['t'] in ('varDmg', 'varBlock'):
            f['opts'] = [math.ceil(v * 1.25) for v in f['opts']]; done = True
        elif f['t'] == 'halfBlockDmg':
            f['bonus'] = f.get('bonus', 0) + 2; done = True
    if not done:
        for f in d['fx']:
            if f['t'] in ('weak', 'vuln'):
                f['n'] += 1; done = True
    if not done:
        if d['cost'] > 0:
            d['cost'] = max(0, d['cost'] - 1); done = True
        else:
            for f in d['fx']:
                if f['t'] == 'draw':
                    f['n'] += 1; break
    return d


_UPC = {}


GRADE_ORD = {1: 4, 2: 3, 3: 2, 4: 1, 5: 0}      # v0.25: 등급 = 바이어 순위(rank 1 = α = 으뜸)
GRADE_W = {1: 0.16, 2: 0.34, 3: 0.60, 4: 0.85, 5: 1.0}
_FUSC = {}


def fused_data(c):
    """v0.20 대장간: 같은 별자리 2장 → 1장 (비용 max · 효과 합 · 2성 계산)"""
    k = (c['id'], c['id2'], bool(c.get('up')), bool(c.get('up2')))
    if k in _FUSC:
        return _FUSC[k]
    A = up_data(c['id']) if c.get('up') else STARS[c['id']]
    B = up_data(c['id2']) if c.get('up2') else STARS[c['id2']]
    d = dict(A)
    d.update({'name': (A.get('name') or A.get('by','')) + '·' + (B.get('name') or B.get('by','')), 'type': '융합', 'fused': True,
              'rank': min(A.get('rank', 5), B.get('rank', 5)),
              'cost': max(A['cost'], B['cost']),
              'target': bool(A.get('target') or B.get('target')),
              'fx': json.loads(json.dumps(A['fx'])) + json.loads(json.dumps(B['fx'])),
              'countAs': A.get('countAs', 1) + B.get('countAs', 1)})
    _FUSC[k] = d
    return d


def norm(card):
    """튜플/딕셔너리 어느 쪽이든 딕셔너리로"""
    if isinstance(card, dict):
        return card
    return {'id': card[0], 'up': card[1]}


SIM_TOKENS = {   # v0.46: addCard 토큰 — 성좌 계산 제외·소멸
    'starlet': {'id': 'starlet', 'by': '', 'name': '새끼 별', 'con': 'auriga', 'rank': 5,
                'type': '공격', 'cost': 0, 'target': True,
                'fx': [{'t': 'noCount'}, {'t': 'vanish'}, {'t': 'dmg', 'v': 4}]}}


def card_id(card):
    c = norm(card)
    return c.get('id')


def cdata(card):
    c = norm(card)
    if c.get('tok'):
        return SIM_TOKENS[c['id']]
    if c.get('id2'):
        return fused_data(c)
    if not c.get('up'):
        return STARS[c['id']]
    cid = c['id']
    if cid not in _UPC:
        _UPC[cid] = up_data(cid)
    return _UPC[cid]


class Enemy:
    def __init__(self, eid, act1_nerf=False):
        sp = ENEMIES[eid]
        ov = sp.get('act1') if act1_nerf else None
        self.id = eid
        self.sp = sp
        self.hp = self.maxhp = (ov or sp)['hp']
        self.atk_ov = ov['atk'] if ov else None
        self.block = self.poison = self.weak = self.vuln = self.burn = self.burn_t = self.enrage = 0
        self.sealed = False
        self.boss = bool(sp.get('boss'))
        self.intent = None


class Sim:
    def __init__(self, deck, enemies, act=1, hp=70, season_off=0, relics=(), allies=(), rng=None):
        self.rng = rng or random
        self.deck = list(deck)
        self.rng.shuffle(self.deck)
        self.hand, self.disc = [], []
        self.hp, self.maxhp = hp, 70
        self.act = act
        self.season_off = season_off
        self.relics, self.allies = set(relics), list(allies)
        self.enemies = [Enemy(e, act1_nerf=(act == 1 and e == 'm42')) for e in enemies]
        self.turn = 0
        self.block = 0
        self.energy_drain = 0
        self.power_block = self.power_atk = 0
        self.keep_block = False
        self.delay_draw = 0
        self.battle_counts = defaultdict(int)
        self.ever = set()
        self.crown = 0
        self.sheliak_atk = True
        self.seal_next = 0
        self.sealed = 0
        self.con_seal = None
        self.con_seal_next = None
        self.gravity_always = False
        self.con_seal_all = False
        self.con_seal_all_next = False
        self.dawn = DAWN.get(act)
        # v0.43 깊은 밤 — 일반 9 · 중간보스 12 · 보스 14턴부터 적 공격 +1 누적
        self.night_from = (14 if any(ENEMIES[e].get('boss') for e in enemies)
                           else 12 if any(ENEMIES[e].get('elite') for e in enemies) else 9)
        # v0.37: 블랙홀 '계절 왜곡' — seasonWarp 턴마다 계절이 한 칸 밀린다 (구 역행 폐지)
        self.season_warp = next((ENEMIES[e].get('seasonWarp') for e in enemies
                                 if ENEMIES[e].get('seasonWarp')), None)
        # v0.47 천문 메커니즘 상태
        self.auras = []          # 항성풍
        # v0.50 떠오름 상태
        self.completed = set()   # 전투 내내 유지 (구: 턴 리셋)
        self.rose_this_turn = []
        self.rise = {}           # 정적 패시브 (dmgPlus·pierce·keepBlock·execBonus·riseDraw·carryPlus)
        self.crown = 0           # 대관 — 전투 지속
        self.grown = {}          # 강착 (전투 scope)
        self.expose = {}         # 노출 누적
        self._grow_kill = None
        self._return_kill = None
        self._maxhp_kill = None
        # 통계
        self.completed_log = defaultdict(int)     # 실제 완성 횟수
        self.had_cards = defaultdict(int)         # 그 별자리 카드를 손에 쥔 턴 수
        self.dmg_taken = 0

    # ── 계절 ──
    def season(self):
        if self.act == 1:
            return None                            # 1막은 계절 없음 (v0.19)
        # v0.37: 계절은 전투당 하나로 고정 (턴 순환 폐지) — 블랙홀 왜곡만 전투 중 계절을 민다
        idx = self.season_off
        if self.season_warp and self.turn > 1:
            idx += (self.turn - 1) // self.season_warp
        return SEASONS[idx % 4]

    def smod(self, ss):
        cur = self.season()
        if cur is None or ss == '주극':
            return 0
        if ss == cur:
            return 1
        return -1 if OPP[ss] == cur else 0

    def sadj(self, v, ss):
        m = self.smod(ss)
        return math.ceil(v * 1.5) if m == 1 else math.floor(v * 0.75) if m == -1 else v   # v0.37: 제철 +50%

    # ── 유틸 ──
    def alive(self):
        return [e for e in self.enemies if e.hp > 0]

    def need(self, k):
        return max(1, CONS[k]['need'] - self.need_reduce)

    def draw(self, n):
        got = 0
        for _ in range(n):
            if not self.deck:
                if not self.disc:
                    break
                self.deck = self.disc
                self.disc = []
                self.rng.shuffle(self.deck)
            self.hand.append(self.deck.pop())
            got += 1
        if got and not getattr(self, '_in_aura_draw', False):     # v0.47 항성풍(재귀 방지)
            self._in_aura_draw = True
            self.aura_fire('draw')
            self._in_aura_draw = False

    def hit(self, e, dmg, pierce=False):
        if e is None or e.hp <= 0:
            return
        if self.rise.get('pierce'):                               # v0.50 궁수 패시브
            pierce = True
        if self.rise.get('execBonus') and e.hp * 2 <= e.maxhp:    # v0.50 페르세우스 패시브
            dmg += self.rise['execBonus']
        if e.sp.get('huddle') and any(x.id == 'babystar' and x.hp > 0 for x in self.enemies):
            dmg = math.ceil(dmg * (1 - e.sp['huddle']))
        if e.vuln > 0:
            dmg = int(dmg * 1.5)
        if e.block > 0 and not pierce:
            b = min(e.block, dmg)
            e.block -= b
            dmg -= b
        was_alive = e.hp > 0
        e.hp = max(0, e.hp - dmg)
        if was_alive and e.hp == 0:                               # v0.47 강착·공전·항성풍
            if self._grow_kill:
                cid, gv = self._grow_kill
                self.grown[cid] = self.grown.get(cid, 0) + gv
            if self._return_kill is not None:
                rc = self._return_kill
                if rc in self.disc:
                    self.disc.remove(rc); self.hand.append(rc)
                self._return_kill = None
            if getattr(self, '_maxhp_kill', None):             # v0.51 포식
                self.maxhp += self._maxhp_kill
                self.hp += self._maxhp_kill
                self._maxhp_kill = None
            self.aura_fire('kill', e)
        if was_alive and e.hp == 0 and e.sp.get('deathBurst'):   # v0.43 임종 폭발
            _bd = max(0, e.sp['deathBurst'] - 0)
            _b = min(self.block, _bd); self.block -= _b
            self.hp = max(0, self.hp - (_bd - _b)); self.dmg_taken += _bd - _b
        sp = e.sp
        if e.hp > 0 and sp.get('split') and not getattr(e, 'split_done', False) and e.hp <= e.maxhp * sp['split']['at']:
            e.split_done = True
            e.block = (e.block or 0) + sp['split']['block']
            for _ in range(sp['split']['n']):
                nb = Enemy('babystar')
                self.set_intent(nb)
                self.enemies.append(nb)
        if e.hp > 0 and sp.get('phase') and not getattr(e, 'phased', False) and e.hp <= e.maxhp * sp['phase']['at']:
            e.phased = True
            if sp['phase'].get('atk'):
                e.atk_bonus = getattr(e, 'atk_bonus', 0) + sp['phase']['atk']
            if sp['phase'].get('minionCap'):
                e.cap_bonus = sp['phase']['minionCap']
            if sp['phase'].get('sealHand'):
                e.seal_bonus = sp['phase']['sealHand']
            if sp['phase'].get('gravity'):
                self.gravity_always = True

    # ── 턴 ──
    def start_turn(self):
        self.turn += 1
        self.con_seal_all = self.con_seal_all_next
        self.con_seal_all_next = False
        if self.dawn and self.turn + 1 >= self.dawn['from']:
            t = self.turn + 1
            self.hp = max(0, self.hp - (self.dawn['dmg'] + (t - self.dawn['from']) * self.dawn['step']))
        for _e in self.enemies:
            _c = _e.sp.get('creep')
            if _c and self.turn >= 1 and _e.hp > 0:
                _e.atk_bonus = min(_c['max'], getattr(_e, 'atk_bonus', 0) + _c['v'])
            _rg = _e.sp.get('regen')                     # v0.43 자기 회복
            if _rg and self.turn >= 1 and 0 < _e.hp < _e.maxhp:
                _e.hp = min(_e.maxhp, _e.hp + _rg)
        if self.keep_block:
            self.keep_block = False
        elif self.rise.get('keepBlock'):
            pass                                                  # v0.50 케페우스 — 성막 유지
        else:
            self.block = 0
        self.block += self.power_block
        if self.turn > 1:
            self.aura_fire('turn')                                # v0.47 항성풍 — 매 턴
        if self.power_atk > 0:
            t = self.rng.choice(self.alive()) if self.alive() else None
            self.hit(t, self.power_atk)
        self.energy = 3 + (min(2 + self.rise.get('carryPlus', 0), self.energy) if self.turn > 1 else 0)   # v0.46 이월 + v0.50 작은곰
        self.con_seal = self.con_seal_next
        self.con_seal_next = None
        if self.gravity_always:
            self.energy_drain += 1
        if self.energy_drain:
            self.energy = max(0, self.energy - self.energy_drain)
            self.energy_drain = 0
        self.turn_counts = defaultdict(int)
        self.rose_this_turn = []                                  # v0.50: completed는 전투 유지
        self.need_reduce = 0
        self.played_turn = 0
        self.thorns = 0
        self.atk_buff = self.def_buff = self.cost_down = 0
        for _c in list(self.hand):        # v0.47 노출(retain) — 손에 남긴 채 턴을 넘기면 밝아진다
            _d = cdata(_c)
            _rf = next((f for f in _d['fx'] if f['t'] == 'retain'), None)
            if _rf:
                k = id(_c)
                self.expose[k] = self.expose.get(k, 0) + _rf.get('v', 0)
        n = max(2, 5 - len(self.hand))
        if 'compass' in self.relics and self.turn == 1:
            self.block += 5
        if 'ember' in self.relics:
            self.atk_buff += 2
        if 'lens' in self.relics and self.turn == 1:
            n += 1
        if 'orrery' in self.relics:
            self.energy += 1
        if 'eternal' in self.relics:
            self.keep_block = True
        if 'polarshard' in self.relics:
            self.need_reduce += 1
        for a in self.allies:
            if a == 'brahe':
                self.block += 2
            elif a == 'herschel' and self.turn % 2 == 0:
                n += 1
            elif a == 'kepler' and self.turn % 3 == 0:
                self.energy += 2
            elif a == 'hubble' and self.turn == 1:
                n += 2
        self.draw(n)
        self.sealed = min(self.seal_next, len(self.hand))
        self.seal_next = 0
        for a in self.allies:                       # 코페르니쿠스: 손패 1장 교체
            if a == 'copernicus' and self.hand:
                self.disc.append(self.hand.pop(self.rng.randrange(len(self.hand))))
                self.draw(1)
        if self.delay_draw:
            self.draw(self.delay_draw)
            self.delay_draw = 0
        for e in self.enemies:
            self.set_intent(e)
        for k in {cdata(c)['con'] for c in self.hand}:
            self.had_cards[k] += 1

    def enemy_atk(self, e, v):
        """v0.20 적 계절 보정 + v0.43 깊은 밤(문턱부터 매 턴 +1 누적)"""
        ss = e.sp.get('season')
        if ss:
            m = self.smod(ss)
            v = math.ceil(v * 1.5) if m == 1 else math.floor(v * 0.75) if m == -1 else v
        if self.turn >= self.night_from:
            v += self.turn - self.night_from + 1
        return v

    def set_intent(self, e):
        sp = e.sp
        if sp.get('defend') and self.turn > 1 and self.turn % sp['defend']['every'] == 0:
            e.intent = ('def', sp['defend']['v']); return
        if sp.get('drain') and self.turn > 1 and self.turn % sp['drain']['every'] == 0:
            e.intent = ('drain', sp['drain']['v']); return
        if sp.get('swallow') and self.turn > 1 and self.turn % sp['swallow']['every'] == 0:
            e.intent = ('swallow', sp['swallow']['n']); return
        if sp.get('conSeal') and self.turn > 1 and self.turn % sp['conSeal']['every'] == 0:
            e.intent = ('conseal', 1); return
        if sp.get('pulsar') and self.turn > 1 and self.turn % sp['pulsar']['every'] == 0:
            e.intent = ('pulsar', 0); return
        if sp.get('nullify') and self.turn > 1 and self.turn % sp['nullify']['every'] == 0:
            e.intent = ('nullify', 0); return
        if sp.get('jet') and self.turn > 1 and self.turn % sp['jet']['every'] == 0:
            e.intent = ('jet', self.enemy_atk(e, sp['jet']['v'] + getattr(e, 'atk_bonus', 0))); return
        if sp.get('minionMax') is not None:
            _mid = sp.get('minionId', 'babystar')
            minions = len([x for x in self.enemies if x.id == _mid and x.hp > 0])
            base = self.enemy_atk(e, (e.atk_ov if e.atk_ov is not None else sp['atk']) + e.enrage + getattr(e, 'atk_bonus', 0))
            cap = getattr(e, 'cap_bonus', 0) or sp['minionMax']
            e.intent = ('summon', 0) if (minions < cap and self.turn % 2 == 1) else ('atk', base)
            return
        pat = sp.get('pattern')
        v = pat[(self.turn - 1) % len(pat)] if pat else sp['atk']
        e.intent = ('atk', self.enemy_atk(e, v + getattr(e, 'atk_bonus', 0)))

    def incoming(self):
        return sum(e.intent[1] for e in self.enemies if e.hp > 0 and e.intent and e.intent[0] in ('atk', 'jet'))

    def enemy_turn(self):
        self.disc.extend(self.hand)
        self.hand = []
        for a in self.allies:
            if a == 'galileo':
                t = self.rng.choice(self.alive()) if self.alive() else None
                self.hit(t, 3)
        for e in list(self.enemies):
            if e.hp <= 0:
                continue
            if e.poison > 0:
                e.hp = max(0, e.hp - e.poison); e.poison -= 1
            if e.hp > 0 and e.burn > 0 and e.burn_t > 0:
                e.hp = max(0, e.hp - e.burn); e.burn_t -= 1
                if e.burn_t == 0:
                    e.burn = 0
            if e.hp <= 0:
                continue
            if e.sealed:
                e.sealed = False
                e.weak = max(0, e.weak - 1); e.vuln = max(0, e.vuln - 1)
                continue
            e.block = 0
            kind, v = e.intent
            if kind == 'summon':
                sp = e.sp
                _mid = sp.get('minionId', 'babystar')
                n = len([x for x in self.enemies if x.id == _mid and x.hp > 0])
                for _ in range(min(sp['summonN'], (getattr(e, 'cap_bonus', 0) or sp['minionCap']) - n)):
                    nb = Enemy(_mid)
                    self.set_intent(nb)
                    self.enemies.append(nb)
            elif kind == 'def':
                e.block = v
                _sh = getattr(e, 'seal_bonus', 0) or e.sp.get('sealHand')
                if _sh:
                    self.seal_next = _sh
            elif kind == 'swallow':
                for _ in range(v):
                    if self.hand:
                        self.deck.insert(0, self.hand.pop(self.rng.randrange(len(self.hand))))
            elif kind == 'conseal':
                pool = [k for k in CONS if k not in self.completed]
                self.con_seal_next = self.rng.choice(pool) if pool else None
            elif kind == 'nullify':
                self.con_seal_all_next = True
            elif kind == 'pulsar':
                e.block = (e.block or 0) + self.block
                self.block = 0
            elif kind == 'drain':
                self.energy_drain += v
            else:
                if e.weak > 0:
                    v = int(v * 0.75)
                self.aura_fire('hurt')                            # v0.47 항성풍 — 맞을 때마다
                blocked = 0 if (e.sp.get('pierce') or kind == 'jet') else min(self.block, v)
                self.block -= blocked
                thru = v - blocked
                self.hp = max(0, self.hp - thru)
                self.dmg_taken += thru
                if self.thorns > 0:
                    e.hp = max(0, e.hp - self.thorns)
                if e.id == 'm42':
                    e.enrage = min(e.sp.get('enrageMax', 99), e.enrage + 1)
            e.weak = max(0, e.weak - 1); e.vuln = max(0, e.vuln - 1)
        self.enemies = [e for e in self.enemies if e.hp > 0 or e.boss]

    # ── 카드 사용 ──
    def eff_cost(self, d):
        return max(0, d['cost'] - 1) if self.cost_down > 0 else d['cost']

    # ═══ v0.47: 조건 리더(cond) — 하나의 프리미티브가 수십 카드 문장을 만든다 ═══
    def cond_met(self, when, target):
        if when == 'enemyAtk':
            return bool(target and target.intent and target.intent[0] in ('atk', 'jet', 'charging'))   # sim의 intent는 (kind, v) 튜플
        if when == 'lastCard':
            return len(self.hand) == 0
        if when == 'conDone':
            return bool(self.rose_this_turn)                      # v0.50: 이번 턴에 떠올랐다면
        if when == 'enemyPoisoned':
            return bool(target and (target.poison > 0 or target.burn > 0))
        if when == 'enemyNoBlock':
            return bool(target and not (target.block or 0) > 0)
        if when == 'selfLowHp':
            return self.hp * 2 <= self.maxhp
        if when == 'handSmall':
            return len(self.hand) <= 2
        if when == 'enemyVuln':
            return bool(target and (target.vuln or 0) > 0)
        if when == 'enemyWeak':
            return bool(target and target.weak > 0)
        return False

    def cond_scan(self, d, target):
        r = {'mult': 1, 'add': None, 'per': 0, 'perTo': 'dmg'}
        for f in d['fx']:
            if f['t'] != 'cond':
                continue
            if f.get('when') == 'playedN':
                r['per'] = f.get('per', 1) * max(0, self.played_turn - 1)
                r['perTo'] = f.get('to', 'dmg')
                continue
            if self.cond_met(f['when'], target):
                if f.get('mult'):
                    r['mult'] *= f['mult']
                if f.get('add'):
                    r['add'] = dict(r['add'] or {}, **f['add'])
        return r

    def fire_on_discard(self, c):
        d = cdata(c)
        f = next((x for x in d['fx'] if x['t'] == 'onDiscard'), None) if d else None
        if not f:
            return
        if f.get('draw'):
            self.draw(f['draw'])
        if f.get('mana'):
            self.energy += f['mana']
        if f.get('block'):
            self.block += f['block']
        if f.get('dmg') and self.alive():
            self.hit(self.rng.choice(self.alive()), f['dmg'])

    def _match(self, x, f):
        dd = cdata(x)
        if not dd:
            return False
        if f.get('con') and dd['con'] != f['con']:
            return False
        if f.get('type') and dd['type'] != f['type']:
            return False
        return True

    def aura_fire(self, on, enemy=None):                        # v0.47 항성풍
        for a in self.auras:
            if a['on'] != on:
                continue
            q = a['do']
            if q.get('dmg'):
                t = enemy if (enemy and enemy.hp > 0) else (self.rng.choice(self.alive()) if self.alive() else None)
                self.hit(t, q['dmg'])
            if q.get('atk'):
                self.atk_buff += q['atk']                       # v0.49 매 턴 공격 증폭
            if q.get('aoe'):
                for e in self.alive():
                    self.hit(e, q['aoe'])
            if q.get('block'):
                self.block += q['block']
            if q.get('draw'):
                self.draw(q['draw'])
            if q.get('mana'):
                self.energy += q['mana']
            if q.get('heal'):
                self.hp = min(self.maxhp, self.hp + q['heal'])
            if q.get('poison'):
                t = enemy if (enemy and enemy.hp > 0) else (self.rng.choice(self.alive()) if self.alive() else None)
                if t:
                    t.poison += q['poison']
            # v0.50 성좌 패시브 어휘
            if q.get('weakAll'):
                for e in self.alive():
                    e.weak = max(e.weak, q['weakAll'])
            if q.get('vulnAll'):
                for e in self.alive():
                    e.vuln = max(e.vuln or 0, q['vulnAll'])
            if q.get('burnRand'):
                t = self.rng.choice(self.alive()) if self.alive() else None
                if t:
                    t.burn += q['burnRand']; t.burn_t = 2
            if q.get('dmgLow'):
                al = sorted(self.alive(), key=lambda e: e.hp)
                if al:
                    self.hit(al[0], q['dmgLow'])
            if q.get('vulnHigh'):
                al = sorted(self.alive(), key=lambda e: -e.hp)
                if al:
                    al[0].vuln = max(al[0].vuln or 0, q['vulnHigh'])
            if q.get('costDown'):
                self.cost_down += q['costDown']
            if q.get('copy') and self.hand:
                self.hand.append(dict(norm(self.rng.choice(self.hand))))

    def fv(self, f, d):
        """v0.36 공명(reso — 이번 턴 같은 별자리를 먼저 냈다면 +) · 잔광(glow — 이번 턴 완성했다면 +)"""
        v = f.get('v', f.get('n', 0)) or 0
        if f.get('reso') and self.turn_counts[d['con']] >= (d.get('countAs', 1) + 1):
            v += f['reso']
        if f.get('glow') and self.completed:
            v += f['glow']
        return v

    def play(self, idx, target=None):
        card = self.hand[idx]
        d = cdata(card)
        cost = self.eff_cost(d)
        if cost > self.energy:
            return False
        if cost < d['cost']:
            self.cost_down -= 1
        self.energy -= cost
        self.hand.pop(idx)
        self.disc.append(card)
        self.played_turn += 1
        con, n = d['con'], d.get('countAs', 1)
        _noc = any(f['t'] == 'noCount' for f in d['fx'])       # v0.46 대가 — 성좌 계산 제외
        if not _noc:
            self.turn_counts[con] += n
            self.battle_counts[con] += n
            if d.get('alsoCon'):
                self.turn_counts[d['alsoCon']] += 1
                self.battle_counts[d['alsoCon']] += 1
        self.check_cons()
        ss = CONS[con]['season']
        cd = self.cond_scan(d, target)                                  # v0.47 조건 리더
        grow = self.grown.get(d.get('_id') or card_id(card), 0) + self.expose.get(id(card), 0) \
            + (self.rise.get('dmgPlus', 0) if d['type'] == '공격' else 0)   # v0.50 오리온 패시브
        sA = lambda v: max(0, round(self.sadj(v, ss) * cd['mult']) + grow)
        comp = con in self.completed
        if target is None or target.hp <= 0:
            target = self.alive()[0] if self.alive() else None
        for f in d['fx']:
            t = f['t']
            if t == 'dmg':
                v = sA(self.fv(f, d))
                if comp and d.get('comp', {}).get('dmgPlus'):
                    v += d['comp']['dmgPlus']
                if d.get('ursaEver') and 'ursa' in self.ever:
                    v += d['ursaEver']
                if d.get('everCon') and d['everCon'] in self.ever:
                    v += d['everPlus']
                if f.get('if3') and self.played_turn >= 3:
                    v += f['if3']
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                self.hit(target, v, f.get('pierce'))
            elif t == 'dmgPerCon':
                v = sA(f['v']) + max(0, self.battle_counts[con] - n)
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                self.hit(target, v)
            elif t == 'blockPerCon':
                v = sA(f['v']) + max(0, self.battle_counts[con] - n)
                self.block += v
            elif t == 'dmgMulti':
                total = sA(f['v'] * f['n'] + f.get('plus', 0))
                if comp and d.get('comp', {}).get('multiPlus'):     # v0.44 각성
                    total += d['comp']['multiPlus'] * f['n']
                if d['type'] == '공격' and self.atk_buff:
                    total += self.atk_buff; self.atk_buff = 0
                per, rem = total // f['n'], total - (total // f['n']) * f['n']
                for i in range(f['n']):
                    tt = target if (target and target.hp > 0) else (self.alive()[0] if self.alive() else None)
                    self.hit(tt, per + (1 if i < rem else 0), f.get('pierce'))
            elif t == 'aoe':
                v = sA(f['v'])
                if comp and d.get('comp', {}).get('aoePlus'):       # v0.44 각성
                    v += d['comp']['aoePlus']
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                for e in self.alive():
                    self.hit(e, v)
            elif t == 'aoeBurn':
                v = sA(f['v'])
                for e in self.alive():
                    e.burn += v; e.burn_t = 2
            elif t == 'block':
                v = sA(self.fv(f, d))
                if comp and d.get('comp', {}).get('blockPlus'):
                    v += d['comp']['blockPlus']
                if d['type'] == '수비' and self.def_buff:
                    v += self.def_buff; self.def_buff = 0
                self.block += v
            elif t == 'varBlock':
                self.block += sA(self.rng.choice(f['opts']))
            elif t == 'varDmg':
                v = sA(self.rng.choice(f['opts']))
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                self.hit(target, v)
            elif t == 'halfBlockDmg':
                v = self.block // 2 + f.get('bonus', 0)
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                if v > 0:
                    self.hit(target, v)
            elif t == 'dmgExec':
                v = sA(f['v'])
                if target and target.hp * 2 <= target.maxhp:
                    v += sA(f['plus'])
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                self.hit(target, v)
            elif t == 'dmgKill':
                v = sA(f['v'])
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                alv = target and target.hp > 0
                self.hit(target, v)
                if alv and target.hp <= 0:
                    self.energy += f['mana']
            elif t == 'dmgRand':
                t2 = self.rng.choice(self.alive()) if self.alive() else None
                self.hit(t2, sA(f['v']))
            elif t == 'poison':
                if target:
                    target.poison += sA(f['v'])
            elif t == 'burn':
                if target:
                    target.burn += sA(f['v']); target.burn_t = 2
            elif t == 'weak':
                if target:
                    w = f['n'] + (d.get('comp', {}).get('weakPlus', 0) if comp else 0)
                    target.weak = max(target.weak, w)
            elif t == 'vuln':
                if target:
                    target.vuln = max(target.vuln, f['n'])
            elif t == 'seal':
                a = target if (target and target.hp > 0) else (self.rng.choice(self.alive()) if self.alive() else None)
                if a:
                    a.sealed = True
            elif t == 'draw':
                self.draw(self.fv(f, d) + (d.get('comp', {}).get('drawPlus', 0) if comp else 0))   # v0.44 각성
            elif t == 'mana':
                self.energy += f['v']
            elif t == 'heal':
                _hv = f['v'] + (d.get('comp', {}).get('healPlus', 0) if comp else 0)   # v0.44 각성
                self.hp = min(self.maxhp, self.hp + _hv)
            elif t == 'thorns':
                self.thorns += f['v']
            elif t == 'buffAtk':
                self.atk_buff += f['v']
            elif t == 'buffDef':
                self.def_buff += f['v']
            elif t == 'costDown':
                self.cost_down += f['v']
            elif t == 'needDown':
                self.need_reduce += f['v']
            elif t == 'power':
                self.power_block += f['v']
            elif t == 'powerAtk':
                self.power_atk += f['v']
            elif t == 'delayDraw':
                self.delay_draw += f['n']
            elif t == 'crown':
                self.crown += 1
            elif t == 'weakAllFx':
                for e in self.alive():
                    e.weak = max(e.weak, f['n'])
            elif t == 'vulnAllFx':
                for e in self.alive():
                    e.vuln = max(e.vuln, f['n'])
            elif t == 'aoePoisonFx':
                for e in self.alive():
                    e.poison += sA(f['v'])
            elif t == 'copyRand':
                if self.hand:
                    self.hand.append(dict(norm(self.rng.choice(self.hand))))
            elif t in ('sacDmg', 'sacBlock', 'sacMana', 'sacDraw'):
                # AI 정책: 손패가 4장 이상이면 버린다 (가장 비싼 카드부터)
                if len(self.hand) >= 4:
                    j = max(range(len(self.hand)), key=lambda i: cdata(self.hand[i])['cost'])
                    _dc = self.hand.pop(j)
                    self.disc.append(_dc)
                    self.fire_on_discard(_dc)
                    if t == 'sacDmg':
                        self.hit(target, f['v'])
                    elif t == 'sacBlock':
                        self.block += f['v']
                    elif t == 'sacMana':
                        self.energy += f['v']
                    else:
                        self.draw(f['n'])
            elif t == 'discard1':
                if self.hand:
                    j = max(range(len(self.hand)), key=lambda i: cdata(self.hand[i])['cost'])
                    _dc = self.hand.pop(j)
                    self.disc.append(_dc)
                    self.fire_on_discard(_dc)
            elif t == 'copySelect' or t == 'copyRandom':
                if self.hand:
                    src = self.rng.choice(self.hand)
                    self.hand.append(src)
            elif t == 'toggle':
                if self.sheliak_atk:
                    self.hit(self.rng.choice(self.alive()) if self.alive() else None, sA(6))
                else:
                    self.block += sA(5)
                self.sheliak_atk = not self.sheliak_atk
            elif t == 'choice':
                if self.incoming() > self.block:
                    self.block += sA(5)
                else:
                    self.hit(self.rng.choice(self.alive()) if self.alive() else None, sA(6))
            elif t == 'hpCost':                                # v0.46 대가 — 하한 1
                self.hp = max(1, self.hp - f['v'])
            elif t == 'blockBurst':                            # v0.46 대가 — 성막 전부 소모
                b = self.block; self.block = 0
                v = int(b * f['mult'])
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                if v > 0:
                    self.hit(target, v)
            elif t == 'ifAtk':                                 # v0.46 요격 — 공격 예고 시 2배 (근사: 이번 턴 피해가 들어오면)
                v = sA(self.fv(f, d)) * (2 if self.incoming() > 0 else 1)
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                self.hit(target, v, f.get('pierce'))
            elif t == 'ifLast':                                # v0.46 막별 — 손패 마지막 장이면 2배
                v = sA(self.fv(f, d)) * (2 if not self.hand else 1)
                if d['type'] == '공격' and self.atk_buff:
                    v += self.atk_buff; self.atk_buff = 0
                self.hit(target, v, f.get('pierce'))
            elif t == 'ifConDone':                             # v0.50 정렬 — 떠오른 턴이면
                if self.rose_this_turn:
                    if f.get('draw'): self.draw(f['draw'])
                    if f.get('mana'): self.energy += f['mana']
                    if f.get('block'): self.block += f['block']
                    if f.get('heal'): self.hp = min(self.maxhp, self.hp + f['heal'])
            elif t == 'poisonDouble':                          # v0.46 맹독
                if f.get('all'):
                    for e in self.alive():
                        e.poison *= 2
                elif target and target.hp > 0:
                    target.poison *= 2
            elif t == 'addCard':                               # v0.46 강생 — 토큰 생성
                for _ in range(f.get('n', 1)):
                    self.hand.append({'id': f['id'], 'tok': True})
            elif t == 'addCopy':                               # v0.51 분신 (StS Anger)
                self.disc.append(dict(norm(card)))
            elif t == 'maxHpKill':                             # v0.51 포식 (StS Feed)
                self._maxhp_kill = f.get('v', 3)
            # onDiscard는 버려질 때 발동 — 여기서는 없음
            # ═══ v0.47 천문 메커니즘 ═══
            elif t == 'aura':                                  # 항성풍
                self.auras.append({'on': f['on'], 'do': f.get('do', {})})
            elif t == 'growth':                                # 강착
                cid = card_id(card)
                if f['on'] == 'play':
                    self.grown[cid] = self.grown.get(cid, 0) + f['v']
                else:
                    self._grow_kill = (cid, f['v'])
            elif t == 'returnKill':                            # 공전
                self._return_kill = card
            elif t == 'recall':                                # 회귀
                pool = [x for x in self.disc if x is not card and self._match(x, f)]
                if pool:
                    pk = self.rng.choice(pool)
                    self.disc.remove(pk); self.hand.append(pk)
            elif t == 'deckTop':                               # 남중
                pool = [x for x in self.disc if x is not card and (not f.get('con') or cdata(x)['con'] == f['con'])]
                if pool:
                    pk = self.rng.choice(pool)
                    self.disc.remove(pk); self.deck.append(pk)
            elif t == 'poisonBurst':                           # 붕괴
                if target and target.hp > 0 and target.poison > 0:
                    pz = target.poison
                    if not f.get('keep'):
                        target.poison = 0
                    self.hit(target, round(pz * f.get('mult', 1)), True)
            elif t == 'spreadDot':                             # 플레어
                src = next((e for e in self.alive() if e.poison > 0 or e.burn > 0), None)
                if src:
                    for e in self.alive():
                        if e is src:
                            continue
                        e.poison += src.poison
                        if src.burn > 0:
                            e.burn += src.burn; e.burn_t = max(getattr(e, 'burn_t', 0), 2)
            elif t == 'blockSteal':                            # 조석
                if target and target.hp > 0 and (target.block or 0) > 0:
                    bb = min(target.block, f.get('v', 99))
                    target.block -= bb; self.block += bb
            elif t == 'blockDouble':                           # v0.49 참호
                self.block += self.block
            # scry·noCount·vanish 등은 여기서 처리 없음
        a = cd.get('add')                                      # v0.47 조건 추가효과
        if a:
            if a.get('dmg') and target and target.hp > 0:
                self.hit(target, sA(a['dmg']), a.get('pierce'))
            if a.get('aoe'):
                for e in self.alive():
                    self.hit(e, sA(a['aoe']))
            if a.get('block'):
                self.block += sA(a['block'])
            if a.get('draw'):
                self.draw(a['draw'])
            if a.get('mana'):
                self.energy += a['mana']
            if a.get('heal'):
                self.hp = min(self.maxhp, self.hp + sA(a['heal']))
            if a.get('poison') and target and target.hp > 0:
                target.poison += sA(a['poison'])
            if a.get('vuln') and target and target.hp > 0:
                target.vuln = max(target.vuln or 0, a['vuln'])
            if a.get('weak') and target and target.hp > 0:
                target.weak = max(target.weak, a['weak'])
        self._grow_kill = None; self._return_kill = None; self._maxhp_kill = None
        if any(f['t'] == 'vanish' for f in d['fx']):           # v0.46 소멸 — 이번 전투에서 제거
            for _vi in range(len(self.disc) - 1, -1, -1):
                if self.disc[_vi] is card:
                    del self.disc[_vi]
                    break
        self.check_cons()
        return True

    def rise_apply(self, k, r):
        """v0.50 떠오름 — 전투 상시 패시브 등록"""
        if not r:
            return
        if r.get('on'):
            self.auras.append({'on': r['on'], 'do': r.get('do', {}), 'rise': k})
        for key, v in (r.get('static') or {}).items():
            if isinstance(v, (int, float)):
                self.rise[key] = self.rise.get(key, 0) + v
            else:
                self.rise[key] = v

    def check_cons(self):
        if self.con_seal_all:
            return
        for k in CONS:
            if k in self.completed or k == self.con_seal:
                continue
            if self.battle_counts[k] >= self.need(k):             # v0.50: 전투 누적 판정
                self.completed.add(k)
                self.ever.add(k)
                self.rose_this_turn.append(k)
                self.completed_log[k] += 1
                self.aura_fire('conDone')
                self.rise_apply(k, CONS[k].get('rise'))
                if self.rise.get('riseDraw') and len(self.completed) > 1:   # 왕관 패시브
                    self.draw(self.rise['riseDraw'])
                if len(self.completed) in (2, 3):                 # v0.50 연쇄 — 2·3번째 떠오름까지만
                    self.energy += 1
                    if len(self.completed) == 3:
                        self.draw(1)
                if self.crown:
                    self.draw(self.crown)

    def bonus(self, b):
        t = b['t']
        alive = self.alive()
        if t == 'aoeDmg':
            for e in alive:
                self.hit(e, b['v'], b.get('pierce'))
        elif t == 'aoeDmgBurn':
            for e in alive:
                self.hit(e, b['v'])
                if e.hp > 0:
                    e.burn += b['burn']; e.burn_t = 2
        elif t == 'aoeDmgWeak':
            for e in alive:
                self.hit(e, b['v'])
                if e.hp > 0:
                    e.weak = max(e.weak, b['weak'])
        elif t == 'aoePoison':
            for e in alive:
                e.poison += b['v']
        elif t == 'dmgLowestDraw':
            if alive:
                a = min(alive, key=lambda e: e.hp)
                self.hit(a, b['v'])
                if a.hp <= 0:
                    self.draw(1)
        elif t == 'dmgHighestVuln':
            if alive:
                a = max(alive, key=lambda e: e.hp)
                self.hit(a, b['v'])
                if a.hp > 0:
                    a.vuln = max(a.vuln, b['vuln'])
        elif t == 'manaHeal':
            self.energy += b['mana']; self.hp = min(self.maxhp, self.hp + b['heal'])
            if b.get('draw'):
                self.draw(b['draw'])
        elif t == 'manaDraw':
            self.energy += b['mana']; self.draw(b['draw'])
        elif t == 'buffAtkB':
            self.atk_buff += b['v']
        elif t == 'blockSeal':
            self.block += b['v']
            if alive:
                self.rng.choice(alive).sealed = True
        elif t == 'dmgRandom':
            if alive:
                self.hit(self.rng.choice(alive), b['v'], b.get('pierce'))
        elif t == 'copyRandom':
            for _ in range(b.get('n', 1)):
                if self.hand:
                    self.hand.append(dict(norm(self.rng.choice(self.hand))))
            if b.get('mana'):
                self.energy += b['mana']
        elif t == 'drawWeakAll':
            self.draw(b['draw'])
            for e in alive:
                e.weak = max(e.weak, b['weak'])
        elif t == 'blockDraw':
            self.block += b['block']; self.draw(b['draw'])
        elif t == 'block':
            self.block += b['v']
        elif t == 'blockHeal':   # v0.36 염소
            self.block += b['v']; self.hp = min(self.maxhp, self.hp + b['heal'])
        elif t == 'dmgRandBlock2':   # v0.36 천칭
            a2 = self.rng.choice(self.alive()) if self.alive() else None
            if a2: self.hit(a2, b['v'])
            self.block += b['block']
        elif t == 'blockThorns':
            self.block += b['v']; self.thorns += b['thorns']
        elif t == 'draw':
            self.draw(b['n'])
        elif t == 'squareBlock':
            self.block += b['v']; self.keep_block = True
        elif t == 'needDownB':
            self.need_reduce += b['v']
            if b.get('draw'):
                self.draw(b['draw'])
        elif t == 'drawDiscard':
            self.draw(b['draw'])
            if self.hand:
                j = max(range(len(self.hand)), key=lambda i: cdata(self.hand[i])['cost'])
                self.disc.append(self.hand.pop(j))
        elif t == 'vulnWeakAll':
            for e in alive:
                if b.get('v'):
                    self.hit(e, b['v'])
                if e.hp > 0:
                    e.vuln = max(e.vuln, b['vuln']); e.weak = max(e.weak, b['weak'])
        elif t == 'dmgRandBlock':
            if alive and self.block > 0:
                self.hit(self.rng.choice(alive), self.block)
        elif t == 'execLowest':
            if alive:
                a = min(alive, key=lambda e: e.hp)
                self.hit(a, b['v'])
                if a.hp <= 0:
                    self.energy += b['mana']; self.draw(b['draw'])
        elif t == 'dmgHeal':
            if alive:
                self.hit(self.rng.choice(alive), b['v'])
            self.hp = min(self.maxhp, self.hp + b['heal'])

    # ── 그리디 AI ──
    def card_score(self, idx):
        """카드 1장의 즉시 가치 (물질 환산). 성좌를 완성시키면 보너스 가치를 더한다."""
        card = self.hand[idx]
        d = cdata(card)
        cost = self.eff_cost(d)
        if cost > self.energy:
            return None
        ss = CONS[d['con']]['season']
        s = 0.0
        need_block = max(0, self.incoming() - self.block)
        for f in d['fx']:
            t = f['t']
            if t in ('dmg', 'dmgPerCon', 'dmgRand', 'dmgExec', 'dmgKill'):
                s += self.sadj(f['v'], ss) / 6.0 * (1.2 if f.get('pierce') else 1.0)
            elif t == 'varDmg':                                  # v0.45: 변광 — 기대값으로 평가 (안 세면 AI가 안 낸다)
                s += self.sadj(sum(f['opts']) / len(f['opts']), ss) / 6.0
            elif t == 'dmgMulti':
                s += self.sadj(f['v'] * f['n'], ss) / 6.0
            elif t == 'aoe':
                s += self.sadj(f['v'], ss) * max(1, len(self.alive())) / 6.0
            elif t == 'aoeBurn':
                s += self.sadj(f['v'], ss) * 2 * max(1, len(self.alive())) / 6.0
            elif t in ('block', 'varBlock', 'blockPerCon'):
                v = self.sadj(f.get('v', sum(f.get('opts', [0])) / max(1, len(f.get('opts', [1])))), ss)
                s += min(v, need_block) / 5.0 + max(0, v - need_block) / 15.0
            elif t == 'halfBlockDmg':
                s += (self.block // 2) / 6.0
            elif t == 'draw':
                s += 0.45 * f['n']
            elif t == 'mana':
                s += f['v']
            elif t == 'heal':
                s += f['v'] * 0.21 if self.hp < self.maxhp - 4 else 0.05
            elif t == 'poison':
                v = self.sadj(f['v'], ss)
                s += v * (v + 1) / 2 / 6.0
            elif t == 'burn':
                s += self.sadj(f['v'], ss) * 2 / 6.0
            elif t == 'weak':
                s += 0.45 * f['n']
            elif t == 'vuln':
                s += 0.6 * f['n']
            elif t == 'thorns':
                s += f['v'] * 0.15
            elif t in ('buffAtk', 'buffDef'):
                s += f['v'] / 8.0
            elif t == 'costDown':
                s += 0.7
            elif t == 'seal':
                s += 1.5
            elif t in ('power', 'powerAtk'):
                s += f['v'] * 0.5
            elif t == 'needDown':
                s += 0.8
            elif t == 'crown':
                s += 0.5
            elif t.startswith('sac'):
                s += 0.4
            elif t == 'hpCost':                                # v0.46 대가
                s -= f['v'] * 0.15
            elif t == 'blockBurst':
                s += self.block * f['mult'] / 6.0 - min(self.block, need_block) / 5.0
            elif t == 'ifAtk':
                s += self.sadj(f['v'], ss) * (2 if self.incoming() > 0 else 1) / 6.0
            elif t == 'ifLast':
                s += self.sadj(f['v'], ss) * (2 if len(self.hand) == 1 else 1) / 6.0
            elif t == 'ifConDone':
                if self.rose_this_turn:
                    s += 0.45 * f.get('draw', 0) + f.get('mana', 0) + f.get('block', 0) / 5.0 + f.get('heal', 0) * 0.2
            elif t == 'poisonDouble':
                mx = max((e.poison for e in self.alive()), default=0)
                s += mx * 0.3
            elif t == 'addCard':
                s += 0.5 * f.get('n', 1)
            elif t == 'vanish':
                s -= 0.3
            # ═══ v0.47 천문 메커니즘 채점 ═══
            elif t == 'cond':
                if f.get('when') == 'playedN':
                    s += f.get('per', 1) * max(0, self.played_turn) / 6.0
                elif self.cond_met(f['when'], self.enemies[0] if self.enemies else None):
                    a = f.get('add') or {}
                    if f.get('mult'):
                        s += 1.2                       # 뒤 효과가 배로 — 대략적 가산
                    s += (a.get('dmg', 0) + a.get('aoe', 0)) / 6.0 + a.get('block', 0) / 5.0 \
                        + 0.45 * a.get('draw', 0) + a.get('mana', 0) + a.get('heal', 0) * 0.2 \
                        + 0.6 * a.get('vuln', 0) + 0.45 * a.get('weak', 0) + a.get('poison', 0) * 0.4
            elif t == 'aura':
                q = f.get('do', {})
                s += (q.get('dmg', 0) + q.get('aoe', 0) + q.get('atk', 0)) / 6.0 * 2.5 + q.get('block', 0) / 5.0 * 2.5 \
                    + 0.9 * q.get('draw', 0) + 2.0 * q.get('mana', 0) + q.get('heal', 0) * 0.4 + q.get('poison', 0) * 0.5
            elif t == 'growth':
                s += f['v'] * 0.35
            elif t == 'retain':
                s += 0.2                               # 지금 내면 누적을 포기하는 셈
            elif t == 'recall' or t == 'deckTop':
                s += 0.5
            elif t == 'returnKill':
                s += 0.4
            elif t == 'poisonBurst':
                mx = max((e.poison for e in self.alive()), default=0)
                s += mx * f.get('mult', 1) / 6.0
            elif t == 'spreadDot':
                mx = max((e.poison + e.burn for e in self.alive()), default=0)
                s += mx * max(0, len(self.alive()) - 1) / 8.0
            elif t == 'blockSteal':
                mx = max((e.block or 0 for e in self.alive()), default=0)
                s += min(mx, f.get('v', 99)) / 5.0
            elif t == 'blockDouble':
                s += min(self.block, max(0, need_block)) / 5.0 + self.block / 12.0
            elif t == 'addCopy':
                s += 0.4
            elif t == 'onDiscard':
                s += 0.2
            elif t == 'maxHpKill':
                mx = min((e.hp for e in self.alive()), default=99)
                s += 1.2 if mx <= 12 else 0.3
        # v0.50 성좌 기여 — 전투 누적: 이 카드로 떠오르면 크게, 다가가면 조금
        con = d['con']
        _noc = any(f['t'] == 'noCount' for f in d['fx'])
        if _noc:
            con = None
        if con and con not in self.completed:
            after = self.battle_counts[con] + d.get('countAs', 1)
            nd = self.need(con)
            if after >= nd:
                s += 2.2 + nd * 0.7                    # 이번 카드로 떠오른다 (전투 내내 패시브)
            else:
                s += 0.35                              # 점등 전진
        return s - cost * 0.92

    def can_finish(self, con, exclude=-1):
        """지금 손패·물질로 이 별자리를 이번 턴에 완성할 수 있는가 (대략)"""
        nd = self.need(con) - self.turn_counts[con]
        if nd <= 0:
            return False
        cands = [(i, cdata(c)) for i, c in enumerate(self.hand)
                 if i != exclude and (cdata(c)['con'] == con or cdata(c).get('alsoCon') == con)]
        cands.sort(key=lambda p: p[1]['cost'])
        cnt, cost = 0, 0
        for i, d in cands:
            cnt += d.get('countAs', 1); cost += self.eff_cost(d)
            if cnt >= nd:
                return cost <= self.energy
        return False

    def pick_target(self, idx):
        """이번 카드로 잡을 수 있는 적이 있으면 그쪽, 없으면 위협이 큰 쪽(보스/엘리트)을 때린다.
        구 정책(항상 HP 최저)은 아기별만 잡다가 보스 격노를 키워 지는 문제가 있었다."""
        live = self.alive()
        if not live:
            return None
        d = cdata(self.hand[idx])
        dmg = 0
        for f in d['fx']:
            if f['t'] in ('dmg', 'dmgExec', 'dmgKill', 'dmgPerCon'):
                dmg += self.sadj(f['v'], CONS[d['con']]['season'])
            elif f['t'] == 'dmgMulti':
                dmg += self.sadj(f['v'] * f['n'], CONS[d['con']]['season'])
        killable = [e for e in live if e.hp <= dmg and (e.block == 0 or any(f.get('pierce') for f in d['fx']))]
        if killable:
            return max(killable, key=lambda e: (e.boss or e.sp.get('elite', False), e.hp))
        threat = [e for e in live if e.boss or e.sp.get('elite')]
        return (threat or live)[0] if threat else max(live, key=lambda e: e.sp.get('atk', 0))

    def take_turn(self):
        self.start_turn()
        guard = 0
        while guard < 40:
            guard += 1
            best, bs = None, 0.15
            for i in range(len(self.hand)):
                if i < self.sealed:
                    continue
                sc = self.card_score(i)
                if sc is not None and sc > bs:
                    best, bs = i, sc
            if best is None:
                break
            self.play(best, self.pick_target(best))
            if not self.alive():
                break
        self.enemy_turn()

    def run(self, max_turns=40):
        while self.turn < max_turns:
            if not [e for e in self.enemies if e.hp > 0]:
                return True
            self.take_turn()
            if self.hp <= 0:
                return False
            live = [e for e in self.enemies if e.hp > 0]
            boss = [e for e in self.enemies if e.boss]
            if boss and all(e.hp <= 0 for e in boss):
                return True
            if not live:
                return True
        return False


# ═════════════════ 런(막) 시뮬 ═════════════════
BIAS = 0.0          # 보상 3택1 중 "이미 덱에 있는 별자리"에서 뽑을 확률 (실험용)


def wpick_rank(pool, rng, exclude=()):
    """v0.25: 등급(rank) 가중 추첨 — 빌드의 wpick과 같은 규칙"""
    src = [i for i in pool if i not in exclude] or list(pool)
    tot = sum(GRADE_W.get(STARS[i].get('rank', 5), 1) for i in src)
    r = rng.random() * tot
    for i in src:
        r -= GRADE_W.get(STARS[i].get('rank', 5), 1)
        if r <= 0:
            return i
    return src[-1]


def roll_reward(rng, deck=None):
    pool = list(STARS)
    if deck and BIAS > 0 and rng.random() < BIAS:
        owned = {STARS[norm(c)['id']]['con'] for c in deck}   # 합성 카드(딕셔너리)도 센다
        sub = [i for i in pool if STARS[i]['con'] in owned]
        if sub:
            pool = sub
    return wpick_rank(pool, rng)


def pick_reward(deck, picks, rng):
    """AI 픽 정책: 덱에 이미 있는 별자리를 우선(성좌 완성 지향), 동률이면 등급 높은 쪽"""
    cnt = defaultdict(int)
    for c in deck:
        cnt[STARS[norm(c)['id']]['con']] += 1
    return max(picks, key=lambda i: (cnt[STARS[i]['con']], -STARS[i].get('rank', 5), rng.random()))


def try_forge(deck):
    """대장간: 같은 별자리 2장 → 합성 1장. 3성 별자리 · 보유 수 많은 쪽 우선. 못 하면 None"""
    groups = defaultdict(list)
    for i, c in enumerate(deck):
        c = norm(c)
        if not c.get('id2'):                       # 재합성 불가 (빌드 규칙)
            groups[STARS[c['id']]['con']].append(i)
    cand = [(CONS[k]['need'], len(g), k, g) for k, g in groups.items() if len(g) >= 2]
    if not cand:
        return None
    _, _, k, g = max(cand, key=lambda t: (t[0], t[1]))
    ia, ib = g[0], g[1]
    A, B = norm(deck[ia]), norm(deck[ib])
    out = [c for i, c in enumerate(deck) if i not in (ia, ib)]
    out.append({'id': A['id'], 'up': A.get('up', False), 'id2': B['id'], 'up2': B.get('up', False)})
    return out


def sim_act(act, deck, hp, relics, allies, rng, stats):
    """한 막 = 실제 맵 경로 재현: 3열×**10행**(v0.32~) 중 한 줄만 밟는다 + 보스 전 휴식 + 보스.
    genMap의 노드 분포(1~9행 27칸 = 전투 14 · 중간보스 3 · 휴식 4 · 이벤트 3 · 상점 2 · 대장간 1)를
    v0.43: 12행(1~11행 33칸 = 전투 18 · 중간보스 3 · 휴식 5 · 이벤트 4 · 상점 2 · 대장간 1)
    행 단위 확률: 전투 .545 / 중간보스 .091 / 휴식 .152 / 이벤트 .121 / 상점 .061 / 대장간 .030.
    조우 티어는 빌드와 동일하게 0~2행 쉬움 / 3~6행 보통 / 7행~ 강함. (v0.32에서 13행 → 10행 축소)
    """
    season_off = rng.randrange(4)                # v0.37: 전투마다 한 칸씩 넘어간다 (전투 동안 고정)
    dust = 0
    for r in range(12):
        if r == 0:
            kind = 'battle'
        else:
            x = rng.random()
            kind = ('battle' if x < .545 else 'elite' if x < .636 else 'rest' if x < .788
                    else 'event' if x < .909 else 'shop' if x < .970 else 'forge')
        if kind in ('battle', 'elite'):
            tier = 'easy' if r <= 3 else 'normal' if r <= 7 else 'hard'
            foes = [rng.choice(ELITES[act])] if kind == 'elite' else list(rng.choice(ENC[act][tier]))
            s = Sim(deck, foes, act=act, hp=hp, season_off=season_off, relics=relics, allies=allies, rng=rng)
            season_off += 1                          # v0.37: 활동(전투)당 한 계절
            won = s.run()
            merge_stats(stats, s, act)
            if not won:
                return None, hp
            hp = s.hp
            dust += (60 if kind == 'elite' else 25) * (2 if act == 3 else 1.5 if act == 2 else 1)
            if kind == 'elite':
                pool = [x for x in D['RELICS'] if x not in relics and not D['RELICS'][x].get('boss')]
                if pool:
                    relics.add(rng.choice(pool))
            picks = [roll_reward(rng, deck) for _ in range(3)]
            deck.append((pick_reward(deck, picks, rng), False))
        elif kind == 'forge':
            deck = try_forge(deck) or deck
        elif kind == 'rest':
            if hp < 50:
                hp = min(70, hp + 30 + (10 if 'waterjar' in relics else 0))   # v0.21: 휴식 회복 30
            else:
                cands = [j for j, c in enumerate(deck) if not norm(c).get('id2') and not norm(c).get('up')]
                if cands:
                    j = rng.choice(cands)
                    deck[j] = (norm(deck[j])['id'], True)
        elif kind == 'event':
            hp = min(70, hp + 10) if rng.random() < .5 else hp
            dust += 40
        else:                                        # 상점: 카드 1장 + 제거
            if dust >= 65:
                dust -= 65
                picks = [roll_reward(rng, deck) for _ in range(3)]
                deck.append((pick_reward(deck, picks, rng), False))
    hp = min(70, hp + 30 + (10 if 'waterjar' in relics else 0))   # 보스 전 고정 휴식 노드 (빌드: rest 30)
    s = Sim(deck, [BOSS[act]], act=act, hp=hp, season_off=season_off, relics=relics, allies=allies, rng=rng)
    won = s.run()
    merge_stats(stats, s, act)
    stats['boss_turns'][act].append(s.turn)
    return (deck, s.hp) if won else (None, s.hp)


def merge_stats(stats, s, act):
    for k, v in s.completed_log.items():
        stats['comp'][k] += v
    for k, v in s.had_cards.items():
        stats['had'][k] += v
    stats['turns'].append(s.turn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=0)
    ap.add_argument('--cons', type=int, default=0)
    ap.add_argument('--validate', action='store_true')
    ap.add_argument('--bias', type=float, default=0.0, help='보상이 보유 별자리에서 나올 확률')
    ap.add_argument('--needcut', action='store_true', help='3성 별자리를 2성으로 낮춰 실험')
    ap.add_argument('--seed', type=int, default=20260809)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    global BIAS
    BIAS = a.bias
    if a.needcut:
        for c in CONS.values():
            if c['need'] >= 3:
                c['need'] = 2

    if a.validate:
        validate(rng); return

    stats = {'comp': defaultdict(int), 'had': defaultdict(int), 'turns': [],
             'boss_turns': defaultdict(list)}
    if a.runs:
        act1 = act2 = act3 = 0
        for i in range(a.runs):
            deck = [(c, False) for c in D['POLAR_DECK']]
            allies = [rng.choice(list(D['COMPANIONS']))]
            relics = set()
            deck2, hp = sim_act(1, deck, 70, relics, allies, rng, stats)
            if deck2 is None:
                continue
            act1 += 1
            # 2막: 보스 유물 + 조력자 2인째 + 막 사이 회복 22 (빌드 v0.21)
            bosspool = [r for r in D['RELICS'] if D['RELICS'][r].get('boss')]
            if bosspool:
                relics.add(rng.choice(bosspool))
            pool2 = [c for c in D['COMPANIONS'] if c not in allies]
            if pool2:
                allies.append(rng.choice(pool2))
            hp = min(70, hp + 22)
            deck3, hp = sim_act(2, deck2, hp, relics, allies, rng, stats)
            if deck3 is None:
                continue
            act2 += 1
            # 3막: 보스 유물 + 조력자 3인째 (v0.21 신설 — 구 모델은 2막에서 끝났다)
            bosspool = [r for r in D['RELICS'] if D['RELICS'][r].get('boss') and r not in relics]
            if bosspool:
                relics.add(rng.choice(bosspool))
            pool3 = [c for c in D['COMPANIONS'] if c not in allies]
            if pool3:
                allies.append(rng.choice(pool3))
            hp = min(70, hp + 22)
            deck4, _ = sim_act(3, deck3, hp, relics, allies, rng, stats)
            if deck4 is not None:
                act3 += 1
        print(f'런 {a.runs}회 — 1막 클리어 {act1} ({act1/a.runs*100:.1f}%) · 2막 클리어 {act2} ({act2/a.runs*100:.1f}%)'
              f' · 완주 {act3} ({act3/a.runs*100:.1f}%)')
        print(f'평균 전투 턴수 {sum(stats["turns"])/max(1,len(stats["turns"])):.1f}')
        for act in (1, 2, 3):
            bt = stats['boss_turns'][act]
            if bt:
                print(f'  {act}막 보스전 평균 {sum(bt)/len(bt):.1f}턴')
        report_cons(stats)

    if a.cons:
        # 성좌 완성 난도만 — "그 별자리 카드를 손에 쥔 턴" 대비 완성 횟수
        for _ in range(a.cons):
            deck = [(c, False) for c in D['POLAR_DECK']]
            for _ in range(rng.randrange(4, 14)):    # 런 중후반 덱 규모
                deck.append((roll_reward(rng, deck), False))
            foes = list(rng.choice(ENC[1]['normal']))
            s = Sim(deck, foes, act=1, hp=70, rng=rng)
            s.run(max_turns=8)
            merge_stats(stats, s, 1)
        report_cons(stats)


def report_cons(stats):
    print('\n성좌 완성 난도 (완성 횟수 ÷ 그 별자리 카드를 손에 쥔 턴 수)')
    print(f'{"별자리":14s}{"필요":>4s}{"보유턴":>7s}{"완성":>6s}{"완성률":>8s}')
    rows = []
    for k, c in CONS.items():
        had, comp = stats['had'][k], stats['comp'][k]
        rate = comp / had if had else 0.0
        rows.append((rate, k, c, had, comp))
    for rate, k, c, had, comp in sorted(rows):
        print(f'{c["name"]:14s}{c["need"]:>4d}{had:>7d}{comp:>6d}{rate*100:>7.1f}%')


def validate(rng):
    print('— 규칙 검산 —')
    s = Sim([('caph', False)] * 4, ['jupiter'], act=1, rng=rng)
    s.start_turn()
    s.hand = [('caph', False)] * 4
    s.energy = 9
    s.play(0)
    print(f'  1장(1/2) — 떠오름={sorted(s.completed)} (기대 [])')
    s.enemy_turn(); s.start_turn()                                # v0.50: 턴을 넘겨도 점등 유지
    s.energy = 9; s.hand = [('caph', False)] * 3
    s.play(0)
    print(f'  다음 턴 2장째(2/2) — 떠오름={sorted(s.completed)} (기대 [cassiopeia] — 누적 점등)')
    s.play(0); s.play(0)
    print(f'  4장 냈을 때 떠오름 로그={dict(s.completed_log)} (기대 1회 — 전투당 1회)')
    s2 = Sim([('mizar', False), ('merak', False), ('polaris', False)], ['jupiter'], act=1, rng=rng)
    s2.start_turn(); s2.hand = [('mizar', False), ('merak', False), ('polaris', False)]; s2.energy = 9
    s2.play(0); s2.play(0)   # 미자르(2성)+메라크 → 큰곰 3성 완성
    print(f'  미자르 2성+메라크 → 큰곰 완성={"ursa" in s2.completed} (기대 True)')
    e0 = s2.energy
    s2.play(0)   # v0.46 북극성 — 비용 2 · 물질 +1 · 1장 뽑기 (needDown 폐지)
    print(f'  북극성(v0.46 개편): 물질 {e0}→{s2.energy} (기대 −1) · 손패 {len(s2.hand)}장 (기대 2 — 메라크 뽑기 포함)')
    s2b = Sim([('caph', False)], ['jupiter'], act=1, rng=rng)   # v0.46 물질 이월
    s2b.start_turn(); s2b.energy = 2; s2b.hand = []
    s2b.start_turn()
    print(f'  물질 이월: 잔여 2 → 다음 턴 {s2b.energy} (기대 5)')
    s3 = Sim([('wezen', False)], ['m42'], act=1, rng=rng)   # v0.25 축소로 nunki가 빠져 웨젠(관통 5)으로 교체
    s3.start_turn(); s3.hand = [('wezen', False)]; s3.energy = 9
    s3.enemies[0].block = 50
    hp0 = s3.enemies[0].hp
    s3.play(0)
    print(f'  관통이 아머 무시: 피해 {hp0-s3.enemies[0].hp} (기대 5) · 적 성막 {s3.enemies[0].block} (기대 50)')
    s4 = Sim([('menkar', False)], ['jupiter'], act=2, season_off=2, rng=rng)  # 가을 시작
    s4.start_turn()
    print(f'  2막 계절: turn1={s4.season()} (기대 가을) · 고래 제철 피해 {s4.sadj(9,"가을")} (기대 14 — v0.37 +50%)')
    s5 = Sim([('menkar', False)], ['jupiter'], act=1, rng=rng)
    s5.start_turn()
    print(f'  1막 계절: {s5.season()} (기대 None) · 보정 {s5.sadj(9,"가을")} (기대 9)')


if __name__ == '__main__':
    main()
