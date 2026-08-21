# -*- coding: utf-8 -*-
"""Starry Night 프로토타입 — 절차 생성 도트 아트 + 정식 별자리 형태 (v0.7)

사용법:  python gen_proto_art.py [빌드html]   (기본: starry-night-proto-v0.5.html)

그림을 고치려면 아래 레시피 함수만 수정하고 재실행한다 — HTML의 /*ART-START*/ ~ /*ART-END*/
블록을 통째로 교체 주입하므로 몇 번을 돌려도 결과가 같다(멱등).

외부 그림으로 교체하려면: PIXEL_ART[키]를 같은 격자 규격(몹 24×24/28×28, 초상 24×24,
아이콘 12×12~14×14)의 도트 데이터로 바꾸거나, HTML 쪽 pxArt() 호출부를 <img>로 바꾸면 된다.
"""
import json, math, re, sys

CH = '0123456789abcdefghijklmnopqrstuvwxyz'

class G:
    """도트 격자 — '.'=투명, 문자=팔레트 인덱스"""
    def __init__(self, w, h, pal):
        self.w, self.h, self.pal = w, h, pal
        self.g = [['.'] * w for _ in range(h)]
    def px(self, x, y, c):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.g[y][x] = CH[c]
    def disk(self, cx, cy, r, c):
        for y in range(self.h):
            for x in range(self.w):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.px(x, y, c)
    def shaded(self, cx, cy, r, light, mid, dark):
        """좌상단 광원 3톤 구체"""
        for y in range(self.h):
            for x in range(self.w):
                d2 = (x - cx) ** 2 + (y - cy) ** 2
                if d2 > r * r: continue
                hl = (x - (cx - r * 0.38)) ** 2 + (y - (cy - r * 0.38)) ** 2
                if hl < (r * 0.62) ** 2: self.px(x, y, light)
                elif d2 > (r * 0.72) ** 2 and (x > cx or y > cy): self.px(x, y, dark)
                else: self.px(x, y, mid)
    def ring(self, cx, cy, r, c, th=1.1):
        for y in range(self.h):
            for x in range(self.w):
                d = math.hypot(x - cx, y - cy)
                if abs(d - r) < th * 0.55: self.px(x, y, c)
    def line(self, x0, y0, x1, y1, c):
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(int(n) + 1):
            t = i / n
            self.px(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, c)
    def spark(self, x, y, c, arm=1):
        self.px(x, y, c)
        for a in range(1, arm + 1):
            for dx, dy in ((a, 0), (-a, 0), (0, a), (0, -a)): self.px(x + dx, y + dy, c)
    def rows(self): return [''.join(r) for r in self.g]
    def data(self): return {'w': self.w, 'h': self.h, 'pal': self.pal, 'px': self.rows()}

ART = {}

# ══════════════════ 몹 (쫄 24×24 · 정예/보스 28×28) ══════════════════

def en_shard():  # 오르트 파편 — 모난 암석 + 균열
    g = G(24, 24, ['#e8ecf4', '#a8b2c4', '#6a7488', '#3a4152', '#151a26'])
    pts = [(12, 3), (20, 9), (18, 19), (9, 21), (4, 13), (7, 6)]
    for y in range(24):  # 다각형 채우기(간단 스캔)
        xs = []
        for i in range(len(pts)):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            for x in range(int(xs[j]), int(xs[j + 1]) + 1):
                g.px(x, y, 1 if x + y < 22 else 2)
    for i in range(len(pts)):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
        g.line(x0, y0, x1, y1, 3)
    g.line(12, 5, 10, 12, 3); g.line(10, 12, 14, 18, 3)  # 균열
    g.px(8, 7, 0); g.px(9, 8, 0)
    ART['en_shard'] = g.data()

def en_comet():  # 혜성 — 핵 + 왼쪽으로 흐르는 꼬리
    g = G(24, 24, ['#ffffff', '#c8f4ff', '#7fd8e8', '#2e7a9a', '#173a5a'])
    for i in range(16):  # 꼬리 (밀도 감쇠)
        x = 15 - i
        for dy in range(-1 - i // 5, 2 + i // 5):
            if (x * 7 + dy * 13 + i * 3) % (2 + i // 3) == 0:
                g.px(x, 12 + dy + (i % 3 - 1), 3 if i > 7 else 2)
    g.shaded(17, 12, 4.2, 0, 1, 2)
    g.spark(15, 9, 0)
    ART['en_comet'] = g.data()

def en_moonlet():  # 미아 위성 — 크레이터 달
    g = G(24, 24, ['#f4eedd', '#cfc5a5', '#a89c7c', '#6e6350', '#3a3428'])
    g.shaded(12, 12, 9, 0, 1, 2)
    for cx, cy, r in ((8, 9, 2.2), (15, 15, 2.8), (16, 7, 1.4), (7, 16, 1.4)):
        g.disk(cx, cy, r, 3); g.disk(cx - 0.5, cy - 0.5, r * 0.55, 2)
    ART['en_moonlet'] = g.data()

def en_mars():  # 화성 — 붉은 행성 + 극관
    g = G(24, 24, ['#ffb27a', '#e06a3a', '#a83a1c', '#5e1d0e', '#fff4e8'])
    g.shaded(12, 12, 9.5, 0, 1, 2)
    for x in range(8, 17):  # 극관
        if (x + 1) % 2: g.px(x, 12 - int(math.sqrt(max(0, 9.5**2 - (x - 12)**2))) + 1, 4)
    g.px(11, 3, 4); g.px(12, 3, 4); g.px(13, 3, 4)
    g.disk(9, 14, 1.6, 3); g.disk(16, 10, 1.2, 3)  # 협곡 얼룩
    g.line(6, 17, 12, 18, 3)
    ART['en_mars'] = g.data()

def en_titan():  # 타이탄 — 얼음빛 + 고리
    g = G(24, 24, ['#fff2c8', '#f0c878', '#c8963e', '#7a5a1c', '#dff4ff', '#8fc8e8'])
    g.shaded(12, 11, 7.5, 0, 1, 2)
    for t in range(0, 360, 2):  # 고리(타원)
        a = math.radians(t)
        x, y = 12 + 11 * math.cos(a), 14 + 3.2 * math.sin(a)
        if math.sin(a) > -0.25 or math.hypot(x - 12, y - 11) > 7.5:
            g.px(x, y, 4 if math.sin(a) > 0.4 else 5)
    ART['en_titan'] = g.data()

def en_rogue():  # 떠돌이 행성 — 어두운 구체 + 소용돌이
    g = G(24, 24, ['#b8c4ff', '#6a7ad0', '#3a468f', '#1c2260', '#0c1030'])
    g.shaded(12, 12, 9, 1, 2, 3)
    for t in range(0, 540, 6):  # 나선 팔
        a = math.radians(t); r = 1.2 + t / 90
        if r < 8.4: g.px(12 + r * math.cos(a), 12 + r * 0.8 * math.sin(a), 0 if t % 36 < 8 else 4)
    ART['en_rogue'] = g.data()

def en_pleiades():  # 플레이아데스 — 일곱 자매 + 푸른 안개 (정예 28)
    g = G(28, 28, ['#ffffff', '#cfe8ff', '#8fb8ef', '#3a5a9f', '#1c2f5f'])
    for y in range(28):  # 성운 안개
        for x in range(28):
            d = math.hypot(x - 14, y - 14)
            if d < 11 and (x * 13 + y * 7) % 4 == 0: g.px(x, y, 4)
            if d < 8 and (x * 7 + y * 11) % 5 == 0: g.px(x, y, 3)
    seven = [(9, 8), (14, 6), (19, 9), (11, 13), (17, 14), (9, 19), (16, 20)]
    for i, (x, y) in enumerate(seven):
        g.spark(x, y, 0, 2 if i < 3 else 1); g.px(x + 1, y + 1, 2)
    ART['en_pleiades'] = g.data()

def en_hyades():  # 히아데스 — V자 성단 + 붉은 눈(알데바란) (정예 28)
    g = G(28, 28, ['#ffffff', '#ffd8b0', '#e8a86f', '#8f5a2c', '#ff6a4a', '#a82a1c', '#3a2418'])
    for y in range(28):
        for x in range(28):
            d = math.hypot(x - 14, y - 15)
            if d < 10 and (x * 11 + y * 5) % 5 == 0: g.px(x, y, 6)
    v = [(6, 6), (9, 10), (12, 14), (14, 18), (17, 13), (20, 8)]  # V자
    for i in range(len(v) - 1):
        pass  # 성단이라 선은 긋지 않는다
    for x, y in v: g.spark(x, y, 1, 1)
    g.disk(21, 19, 2.4, 5); g.disk(20.4, 18.4, 1.4, 4); g.spark(20, 18, 0)  # 알데바란
    ART['en_hyades'] = g.data()

def en_m1():  # 게 성운 M1 — 펄서 광선 (정예 28)
    g = G(28, 28, ['#ffffff', '#c8fff2', '#6fe8c8', '#2a9f7f', '#14503f', '#dfb0ff'])
    for y in range(28):  # 필라멘트
        for x in range(28):
            d = math.hypot(x - 14, y - 14)
            if 4 < d < 11 and (x * 5 + y * 9 + int(d * 3)) % 4 == 0: g.px(x, y, 3 if d > 8 else 2)
    for s in (1, -1):  # 펄서 제트(대각 광선)
        for i in range(2, 12):
            g.px(14 + s * i, 14 - s * i, 5 if i % 2 else 1)
    g.shaded(14, 14, 2.6, 0, 1, 2)
    ART['en_m1'] = g.data()

def en_m42():  # 오리온 대성운 — 두 날개 + 트라페지움 (보스 28)
    g = G(28, 28, ['#ffffff', '#ffd7f0', '#e89fd8', '#b76bff', '#6a3aa8', '#2a1650'])
    for y in range(28):
        for x in range(28):
            dx, dy = x - 14, y - 15
            w = (dx / 12) ** 2 + (dy / 8) ** 2   # 가로로 퍼진 날개
            if w < 1:
                if w < 0.18: g.px(x, y, 2)
                elif (x * 7 + y * 13) % 3 == 0: g.px(x, y, 3)
                elif (x * 5 + y * 3) % 4 == 0: g.px(x, y, 4)
                elif w > 0.7 and (x + y) % 3 == 0: g.px(x, y, 5)
    for x, y in ((13, 13), (15, 13), (13, 15), (16, 16)):  # 트라페지움 4중성
        g.spark(x, y, 0)
    g.px(14, 14, 1)
    ART['en_m42'] = g.data()

# ══════════════════ 조력자 초상 (24×24 — 실루엣 + 상징물) ══════════════════
# ※ 외부 그림 교체: 24×24 투명 PNG를 준비해 PIXEL_ART['al_*'] 대신 <img>로 갈면 된다

def al_galileo():  # 흰 수염 + 망원경
    g = G(24, 24, ['#f4e8d0', '#d9b98c', '#8a6a4a', '#5a4632', '#e8e8e8', '#b8a888', '#3a2f22', '#c8a04a'])
    g.disk(11, 9, 5.5, 1)                       # 얼굴
    for y in range(4, 8):                       # 이마·머리
        for x in range(7, 16):
            if math.hypot(x - 11, y - 9) < 6: g.px(x, y, 5)
    for y in range(12, 20):                     # 수염(흰 삼각)
        for x in range(11 - (19 - y) // 2, 12 + (19 - y) // 2):
            g.px(x, y, 4)
    g.px(9, 8, 6); g.px(13, 8, 6)               # 눈
    for y in range(15, 24):                     # 로브
        for x in range(4, 20):
            if abs(x - 11.5) < (y - 13) * 0.9: g.px(x, y, 2 if x < 12 else 3)
    g.line(15, 14, 22, 5, 7); g.line(16, 15, 23, 6, 7)  # 망원경(금빛 관)
    g.px(22, 4, 0)
    ART['al_galileo'] = g.data()

def al_brahe():  # 콧수염 + 금빛 코(!) + 사슬
    g = G(24, 24, ['#f4e0c8', '#d9b98c', '#3a3f5f', '#23273f', '#ffd76a', '#8a5a2c', '#3a2f22', '#c85a3a'])
    g.disk(12, 9, 5.5, 1)
    for y in range(3, 8):                       # 모자(베레)
        for x in range(6, 19):
            if math.hypot(x - 12, y - 7) < 6.5: g.px(x, y, 3)
    g.px(12, 10, 4)                             # 금빛 코
    g.px(9, 8, 6); g.px(15, 8, 6)
    g.line(9, 12, 15, 12, 5); g.px(8, 13, 5); g.px(16, 13, 5)  # 팔자 콧수염
    for y in range(15, 24):                     # 로브(감청)
        for x in range(4, 21):
            if abs(x - 12) < (y - 13) * 0.95: g.px(x, y, 2 if x < 13 else 3)
    for x in range(8, 17, 2): g.px(x, 17 + (x % 4) // 2, 4)     # 금 사슬
    ART['al_brahe'] = g.data()

def al_copernicus():  # 월계관 + 두루마리 (폴백 도트 초상)
    g = G(24, 24, ['#f0d8b8', '#cfa87a', '#7a3a8f', '#4a2358', '#7fd87f', '#3a8f3a', '#3a2f22', '#f4eedd'])
    g.disk(12, 9, 5.5, 1)
    for y in range(4, 7):                       # 곱슬머리
        for x in range(7, 18):
            if math.hypot(x - 12, y - 9) < 6.2 and (x + y) % 2: g.px(x, y, 6)
    for i, x in enumerate(range(6, 19, 2)):     # 월계관
        g.px(x, 5 - (i % 2), 4); g.px(x + 1, 6 - (i % 2), 5)
    g.px(9, 9, 6); g.px(15, 9, 6)
    for y in range(15, 24):                     # 로브(보라)
        for x in range(4, 21):
            if abs(x - 12) < (y - 13) * 0.95: g.px(x, y, 2 if x < 13 else 3)
    g.line(16, 18, 21, 18, 7); g.line(16, 19, 21, 19, 7); g.px(15, 18, 1); g.px(22, 19, 1)  # 두루마리
    ART['al_copernicus'] = g.data()

# ══════════════════ 아이템(12×12) · 유물(12×12) · 맵 노드(14×14) ══════════════════

def it_potion():
    g = G(12, 12, ['#dff4ff', '#7fd8e8', '#2e9ad0', '#173a5a', '#c8a04a'])
    g.line(5, 1, 6, 1, 4); g.line(5, 2, 6, 2, 3)
    for y in range(3, 10):
        w = min(y - 1, 4)
        for x in range(6 - w, 6 + w): g.px(x, y, 2 if y > 5 else 0)
    g.line(3, 10, 8, 10, 3); g.px(4, 6, 0)
    ART['it_potion'] = g.data()

def it_meteorite():
    g = G(12, 12, ['#ffd76a', '#e06a3a', '#8a5a3c', '#4a3222', '#fff4c8'])
    g.disk(7, 7, 3.2, 2); g.disk(6.5, 6.5, 2, 1)
    g.line(1, 1, 4, 4, 0); g.line(2, 0, 5, 3, 4); g.px(3, 2, 0)
    g.px(8, 6, 3); g.px(6, 8, 3)
    ART['it_meteorite'] = g.data()

def it_flask():
    g = G(12, 12, ['#e8f4ff', '#9fd8ff', '#2f6fd0', '#16336e', '#c8ccd6'])
    g.line(5, 1, 7, 1, 4)
    for y in range(2, 10):
        w = 1 if y < 5 else min(y - 3, 4)
        for x in range(6 - w, 6 + w + 1): g.px(x, y, 2 if y > 6 else (1 if y > 4 else 0))
    g.line(3, 10, 9, 10, 3)
    ART['it_flask'] = g.data()

def rl_generic(key, main, accent, draw):
    g = G(12, 12, ['#ffe9b0', main, accent, '#3a2f22'])
    draw(g)
    ART[key] = g.data()

def gen_relics():
    rl_generic('rl_armillary', '#c8a04a', '#8fd3ff', lambda g: (g.ring(6, 6, 4.5, 1), g.line(2, 6, 10, 6, 2), g.line(6, 2, 6, 10, 1), g.px(6, 6, 0)))
    rl_generic('rl_telescope', '#c8a04a', '#8a6a4a', lambda g: (g.line(2, 9, 9, 2, 1), g.line(3, 10, 10, 3, 1), g.px(10, 2, 0), g.line(4, 10, 3, 11, 2), g.line(7, 10, 8, 11, 2)))
    rl_generic('rl_messier', '#f4eedd', '#c8a04a', lambda g: ([g.line(3, y, 9, y, 1) for y in range(2, 10)], g.line(3, 2, 3, 9, 2), g.line(9, 2, 9, 9, 2), g.px(5, 4, 3), g.px(7, 6, 3)))
    rl_generic('rl_pendulum', '#c8a04a', '#8fd3ff', lambda g: (g.line(6, 1, 6, 7, 1), g.line(3, 1, 9, 1, 1), g.disk(6, 9, 1.8, 2), g.px(6, 9, 0)))
    rl_generic('rl_vanallen', '#6a7ad0', '#7fd87f', lambda g: (g.disk(6, 6, 2.4, 1), g.ring(6, 6, 4.4, 2), g.ring(6, 6, 5.4, 2)))
    rl_generic('rl_corona', '#ffd76a', '#ff9a3a', lambda g: (g.disk(6, 6, 2.4, 1), [g.line(6 + 3.4 * math.cos(math.radians(a)), 6 + 3.4 * math.sin(math.radians(a)), 6 + 5.2 * math.cos(math.radians(a)), 6 + 5.2 * math.sin(math.radians(a)), 2) for a in range(0, 360, 45)]))

def nd(key, pal, draw):
    g = G(14, 14, pal)
    draw(g)
    ART[key] = g.data()

def gen_nodes():
    nd('nd_battle', ['#e8ecf4', '#8fb8ef', '#c8a04a', '#5a4632'], lambda g: (g.line(3, 10, 10, 3, 0), g.line(4, 11, 11, 4, 1), g.line(2, 9, 5, 12, 2), g.px(3, 12, 3), g.px(11, 2, 0)))
    nd('nd_elite', ['#f4eedd', '#c8ccd6', '#3a4152', '#a82a1c'], lambda g: (g.disk(7, 6, 4, 0), g.px(5, 5, 2), g.px(9, 5, 2), g.line(5, 9, 9, 9, 1), g.px(6, 10, 1), g.px(8, 10, 1), g.px(7, 7, 2)))
    nd('nd_shop', ['#ffd76a', '#c8a04a', '#8a5a2c', '#ffe9b0'], lambda g: (g.disk(7, 8, 3.6, 1), g.line(5, 3, 9, 3, 2), g.line(5, 3, 4, 6, 2), g.line(9, 3, 10, 6, 2), g.px(7, 8, 3), g.px(6, 7, 0)))
    nd('nd_rest', ['#ff9a3a', '#ffd76a', '#8a5a2c', '#5a3a1c'], lambda g: (g.line(3, 11, 11, 11, 2), g.line(4, 12, 10, 12, 3), g.px(7, 5, 1), g.disk(7, 8, 2, 0), g.px(6, 6, 1), g.px(8, 7, 1)))
    nd('nd_forge', ['#c8ccd6', '#6a7488', '#3a4152', '#ff9a3a'], lambda g: (g.line(3, 6, 11, 6, 0), g.line(4, 7, 10, 7, 1), g.line(6, 8, 8, 10, 1), g.line(4, 11, 10, 11, 2), g.px(11, 5, 3)))
    nd('nd_event', ['#c9a4ff', '#8fd3ff', '#4a2358'], lambda g: (g.line(5, 3, 8, 3, 0), g.px(9, 4, 0), g.px(9, 5, 0), g.px(8, 6, 0), g.px(7, 7, 0), g.px(7, 8, 1), g.px(7, 11, 1)))
    nd('nd_boss', ['#ffd76a', '#c8a04a', '#a82a1c'], lambda g: (g.line(3, 10, 11, 10, 1), g.line(3, 5, 3, 10, 0), g.line(11, 5, 11, 10, 0), g.line(7, 3, 7, 10, 0), g.px(5, 7, 0), g.px(9, 7, 0), g.px(3, 4, 2), g.px(7, 2, 2), g.px(11, 4, 2)))

# ══════════════════ 별자리 형태 — 정식 성도 (../const_lines.json, 실제 J2000 좌표) ══════════════════
# 형식: stars=[[x,y,크기]..] (중심 0,0 · ±11 정규화) · segs=[[i,j]..] 선분 목록
# 사용자 확정 (2026-08-20): 별자리 선은 constellation line 차트(=const_lines.json)와 동일해야 한다

CONST_KEY_MAP = {'ori': 'orion', 'uma': 'uma', 'umi': 'umi', 'cas': 'cassiopeia',
                 'cyg': 'cygnus', 'gem': 'gemini', 'sco': 'scorpius', 'leo': 'leo',
                 'lib': 'libra', 'sgr': 'sagittarius'}

def build_const_shapes():
    import os
    src = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'const_lines.json'), encoding='utf-8'))
    out = {}
    for k, sk in CONST_KEY_MAP.items():
        d = src[sk]
        xs = [s[0] for s in d['stars']]; ys = [s[1] for s in d['stars']]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1
        f = 22.0 / span
        out[k] = {'stars': [[round((s[0] - cx) * f, 2), round((s[1] - cy) * f, 2), s[2]] for s in d['stars']],
                  'segs': d['lines']}
    return out

CONST_SHAPES = build_const_shapes()

# ══════════════════ 생성 & 주입 ══════════════════

def build():
    en_shard(); en_comet(); en_moonlet(); en_mars(); en_titan(); en_rogue()
    en_pleiades(); en_hyades(); en_m1(); en_m42()
    al_galileo(); al_brahe(); al_copernicus()
    it_potion(); it_meteorite(); it_flask()
    gen_relics(); gen_nodes()

def inject(path):
    src = open(path, encoding='utf-8').read()
    block = ('/*ART-START*/\n'
             'const PIXEL_ART=' + json.dumps(ART, ensure_ascii=False, separators=(',', ':')) + ';\n'
             'const CONST_SHAPES=' + json.dumps(CONST_SHAPES, ensure_ascii=False, separators=(',', ':')) + ';\n'
             '/*ART-END*/')
    out, n = re.subn(r'/\*ART-START\*/.*?/\*ART-END\*/', lambda m: block, src, flags=re.S)
    assert n == 1, 'ART 마커를 찾지 못했다'
    open(path, 'w', encoding='utf-8').write(out)
    print(f'주입 완료: 스프라이트 {len(ART)}종 · 별자리 형태 {len(CONST_SHAPES)}종 → {path}')

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'starry-night-proto-v0.5.html'
    build()
    inject(target)
