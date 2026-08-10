# -*- coding: utf-8 -*-
"""Starry Night — 적 도트(픽셀) 스프라이트 생성기  (v0.21)

사용자 지시 "몹들은 그냥 픽셀로 가자" + 아트가이드 원칙("카드 = 평면 일러스트, 게임플레이 화면 = 도트").

절차적으로 그린다 — 손으로 찍은 도트가 아니라 구(球) 셰이딩·크레이터·고리·성운 같은
프리미티브를 조합해 격자를 채우고, 같은 색이 이어지는 구간을 런렝스로 묶어 SVG <rect>로 그린다.
그래서 그림을 고치고 싶으면 이 파일의 레시피만 바꾸고 다시 돌리면 된다.

사용법:  python gen_pixel_art.py 전투프로토타입_v0.21.html
빌드의  const PIXEL_ART={};/*PIXEL_ART_DATA*/  자리에 데이터를 주입한다.
"""
import io, sys, math, json, random

CHARS = "123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ#$%&*+-=@"

class Spr:
    def __init__(self, w=24, h=24):
        self.w, self.h = w, h
        self.g = [['.'] * w for _ in range(h)]
        self.pal, self.rev, self.i = {}, {}, 0
    def ch(self, color):
        if color not in self.rev:
            c = CHARS[self.i]; self.i += 1
            self.rev[color] = c; self.pal[c] = color
        return self.rev[color]
    def set(self, x, y, color):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            self.g[y][x] = self.ch(color)
    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h: return self.g[y][x]
        return '.'
    def rows(self): return [''.join(r) for r in self.g]
    def data(self): return {'p': self.pal, 'r': self.rows()}

# ───────── 프리미티브 ─────────
def shade(dx, dy, r, trio):
    """좌상단 광원. trio = (밝음, 기본, 어둠)"""
    l = (-dx - dy) / (r * 1.42 + 1e-6)
    return trio[0] if l > 0.42 else (trio[1] if l > -0.18 else trio[2])

def disc(s, cx, cy, r, col):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            if math.hypot(x + .5 - cx, y + .5 - cy) <= r: s.set(x, y, col)

def sphere(s, cx, cy, r, trio, rim=None, bands=None):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            dx, dy = x + .5 - cx, y + .5 - cy
            d = math.hypot(dx, dy)
            if d > r: continue
            t = trio
            if bands:
                for (y0, y1, tri) in bands:
                    if y0 <= y <= y1: t = tri; break
            c = rim if (rim and d > r - .85) else shade(dx, dy, r, t)
            s.set(x, y, c)

def ering(s, cx, cy, rx, ry, col, th=.8, tilt=0.0, arc=None):
    """타원 고리 (tilt = 라디안 기울기). arc=(a0,a1) 이면 그 각도 구간만."""
    steps = int(max(rx, ry) * 26)
    for i in range(steps):
        a = 2 * math.pi * i / steps
        if arc and not (arc[0] <= a <= arc[1]): continue
        for k in (-th, 0, th):
            ex, ey = (rx + k) * math.cos(a), (ry + k) * math.sin(a)
            x = cx + ex * math.cos(tilt) - ey * math.sin(tilt)
            y = cy + ex * math.sin(tilt) + ey * math.cos(tilt)
            s.set(round(x - .5), round(y - .5), col)

def crater(s, cx, cy, r, dark, lite=None):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            d = math.hypot(x + .5 - cx, y + .5 - cy)
            if d <= r:
                if lite and d > r - .8 and (x + .5 - cx) + (y + .5 - cy) > 0: s.set(x, y, lite)
                elif s.get(x, y) != '.': s.set(x, y, dark)

def star4(s, cx, cy, r, ray, core):
    for k in range(1, int(r) + 1):
        s.set(cx + k, cy, ray); s.set(cx - k, cy, ray)
        s.set(cx, cy + k, ray); s.set(cx, cy - k, ray)
    disc(s, cx + .5, cy + .5, max(1.0, r * .45), core)

def dot(s, x, y, col): s.set(x, y, col)

def _inpoly(px, py, pts):
    inside = False; j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]; xj, yj = pts[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi + 1e-9) + xi:
            inside = not inside
        j = i
    return inside

def cloud(s, rng, cx, cy, rx, ry, cols, n=90, hollow=0.0):
    """성운·은하 덩어리 — 가우시안 분포로 흩뿌린다"""
    for _ in range(n):
        a = rng.random() * 2 * math.pi
        u = rng.random() ** .55
        if hollow: u = hollow + (1 - hollow) * u
        x, y = cx + math.cos(a) * rx * u, cy + math.sin(a) * ry * u
        col = cols[min(len(cols) - 1, int(u * len(cols)))]
        s.set(round(x - .5), round(y - .5), col)

def spiral(s, cx, cy, r, col, arms=2, turns=1.15, tilt=0.0, squash=.42, spread=1):
    for a_i in range(arms):
        t = 0.0
        while t < 1.0:
            ang = a_i * 2 * math.pi / arms + t * turns * 2 * math.pi
            rr = r * (.18 + .82 * t)
            ex, ey = rr * math.cos(ang), rr * squash * math.sin(ang)
            x = cx + ex * math.cos(tilt) - ey * math.sin(tilt)
            y = cy + ex * math.sin(tilt) + ey * math.cos(tilt)
            for w in range(spread):
                s.set(round(x - .5), round(y - .5) + w, col)
            t += .012

# ───────── 스프라이트 레시피 ─────────
SPR = {}
def reg(key, w=24, h=24):
    def deco(fn):
        s = Spr(w, h); rng = random.Random(hash(key) & 0xffff)
        fn(s, rng, w / 2.0, h / 2.0, rng)
        SPR[key] = s.data()
        return fn
    return deco

# ── 1막 쫄몹 ──
@reg('mercury')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 9, ('#cdc6ba', '#948d84', '#4e4a45'))
    for (x, y, r) in [(9, 8, 2.4), (14, 13, 1.8), (11, 16, 1.3), (15, 8, 1.1), (7, 12, 1.4)]:
        crater(s, x, y, r, '#5f5a53', '#b4ada3')

@reg('venus')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 10, ('#f7e9b8', '#dcc78c', '#93804f'))
    for y, c in [(7, '#cbb377'), (10, '#e8d6a0'), (13, '#cbb377'), (16, '#bda368')]:
        for x in range(2, 22):
            if s.get(x, y) != '.' and rng.random() < .85: s.set(x, y, c)
    ering(s, cx, cy, 10.8, 10.8, '#f6e6b0', th=.4)

@reg('mars')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 9.5, ('#e2916f', '#c05a3c', '#7c3521'))
    for (x, y, r) in [(9, 13, 2.0), (15, 9, 1.4), (13, 15, 1.2)]:
        crater(s, x, y, r, '#8e3f27')
    for y in range(0, 24):       # 북극관 — 구면 위쪽을 덮는다
        for x in range(0, 24):
            dx, dy = x + .5 - cx, y + .5 - cy
            if math.hypot(dx, dy) <= 9.5 and dy < -6.4:
                s.set(x, y, '#f0e6dc' if dy < -7.4 else '#d8c8bc')

@reg('jupiter')
def _(s, rng, cx, cy, _r):
    B = [(0, 5, ('#eed2ac', '#c8a478', '#8a6c48')), (6, 8, ('#dfae80', '#b0805a', '#764f34')),
         (9, 11, ('#f0d6b0', '#cfa87c', '#8a6c48')), (12, 14, ('#dfae80', '#ac7c56', '#734c32')),
         (15, 24, ('#eed2ac', '#c8a478', '#8a6c48'))]
    sphere(s, cx, cy, 11, ('#eed2ac', '#c8a478', '#8a6c48'), bands=B)
    for y in range(12, 15):
        for x in range(14, 19):
            if s.get(x, y) != '.': s.set(x, y, '#c0523c')
    s.set(16, 13, '#d8785a'); s.set(15, 13, '#d8785a')

@reg('saturn')
def _(s, rng, cx, cy, _r):
    ering(s, cx, cy + .5, 11.5, 3.6, '#a89464', th=1.0, tilt=-0.30)
    sphere(s, cx, cy - .5, 7.5, ('#f0e2ba', '#cdb886', '#8d7c52'))
    for y, c in [(8, '#c3ad7c'), (11, '#dfcf9e'), (14, '#c3ad7c')]:
        for x in range(4, 20):
            if s.get(x, y) not in ('.',) and abs(x - cx) < 7.4: s.set(x, y, c)
    ering(s, cx, cy + .5, 11.5, 3.6, '#e2cf95', th=.35, tilt=-0.30,
          arc=(0, math.pi))

@reg('moonlet')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 8, ('#ccd2e0', '#9aa0b4', '#5c6175'))
    for (x, y, r) in [(9, 9, 2.4), (14, 14, 1.8), (15, 8, 1.1), (10, 15, 1.2)]:
        crater(s, x, y, r, '#71778c', '#b4bacd')
    for x in range(0, 24, 3): s.set(x, 20, '#7f89a8'); s.set(x + 1, 20, '#7f89a8')

@reg('comet')
def _(s, rng, cx, cy, _r):
    for i in range(20):
        w = 1 + i // 7
        for k in range(w):
            s.set(1 + i, 2 + i // 2 + k, '#9fd0ff' if k == 0 else '#5f96cc')
        if i % 4 == 0: s.set(2 + i, i // 2, '#7fbcf0')
    sphere(s, 16.0, 15.0, 6.5, ('#f2fbff', '#bfe0ff', '#77a8d8'))
    disc(s, 15.5, 14.5, 2.6, '#ffffff')

@reg('shard')
def _(s, rng, cx, cy, _r):
    def cryst(x0, y0, hh, ww, c1, c2, c3):
        for k in range(hh):
            w = int(ww * (1 - abs(k - hh * .38) / (hh * .78)))
            for x in range(-max(0, w), max(0, w) + 1):
                s.set(x0 + x, y0 + k, c1 if x < 0 else (c2 if x else c3))
    cryst(11, 3, 14, 4, '#e8a0bc', '#ffd6e6', '#a05f78')
    cryst(6, 11, 9, 3, '#c98aa8', '#f0bcd2', '#8a4f68')
    cryst(18, 12, 8, 2, '#c98aa8', '#f0bcd2', '#8a4f68')

@reg('asteroid')
def _(s, rng, cx, cy, _r):
    pts = [(cx + math.cos(a) * (7.2 + rng.random() * 2.2), cy + math.sin(a) * (6.4 + rng.random() * 2.0))
           for a in [i * math.pi / 6 for i in range(12)]]
    for y in range(24):
        xs = [x for x in range(24) if _inpoly(x + .5, y + .5, pts)]
        for x in xs: s.set(x, y, shade(x + .5 - cx, y + .5 - cy, 8, ('#9aa0b0', '#6a6f80', '#42475a')))
    for (x, y, r) in [(9, 10, 2.2), (14, 13, 1.6), (11, 15, 1.1)]:
        crater(s, x, y, r, '#4a4f60', '#868ba0')

@reg('babystar')
def _(s, rng, cx, cy, _r):
    star4(s, 12, 12, 7, '#ffe9a8', '#fff8dd')
    for (x, y) in [(9, 9), (15, 9), (9, 15), (15, 15)]: s.set(x, y, '#ffd98a')
    disc(s, 12.5, 12.5, 2.2, '#fffdf0')

# ── 1막 딥스카이 ──
@reg('m42', 28, 28)
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 12.5, 11.0, ['#f0a8d0', '#c45a96', '#8a3a6a', '#5a2448'], n=340)
    cloud(s, rng, cx - 1, cy - 1, 6.5, 6.0, ['#ffd8ec', '#e88ac0', '#b8548e'], n=120)
    for (x, y) in [(13, 12), (15, 13), (14, 15), (12, 14)]:
        star4(s, x, y, 2, '#ffe9f6', '#ffffff')
    for _ in range(16):
        s.set(rng.randrange(28), rng.randrange(28), '#ffd8ec')

@reg('pleiades', 28, 28)
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 12.0, 10.0, ['#5f86c8', '#3f5f9a', '#2a3f6a'], n=200)
    P = [(9, 8, 3), (16, 6, 2), (20, 11, 2), (13, 13, 3), (7, 15, 2), (11, 20, 2), (18, 18, 2)]
    for (x, y, r) in P:
        disc(s, x, y, r + 1.6, '#7fa8e8'); star4(s, x, y, r + 1, '#cfe4ff', '#ffffff')

@reg('hyades', 28, 28)
def _(s, rng, cx, cy, _r):
    for i in range(11):
        s.set(6 + i, 5 + i * 1.6, '#6a5f45'); s.set(21 - i, 5 + i * 1.6, '#6a5f45')
    for (x, y, r) in [(6, 5, 2), (10, 11, 2), (14, 20, 3), (18, 11, 2), (22, 5, 2), (12, 15, 1), (17, 16, 1)]:
        disc(s, x, y, r + 1.4, '#8a6a3a'); star4(s, x, y, r + 1, '#ffd9a0', '#fff4e0')

# ── 2막 ──
@reg('uranus')
def _(s, rng, cx, cy, _r):
    ering(s, cx, cy, 12.0, 4.4, '#5fa4b8', th=.5, tilt=math.pi / 2)
    sphere(s, cx, cy, 7.5, ('#b6ecf2', '#7fd0d8', '#4b8f99'))
    for y in [9, 13]:
        for x in range(4, 20):
            if s.get(x, y) != '.' and abs(x - cx) < 7.2: s.set(x, y, '#6ab8c4')
    ering(s, cx, cy, 12.0, 4.4, '#bff0fa', th=.5, tilt=math.pi / 2, arc=(math.pi * .55, math.pi * 1.45))

@reg('neptune')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 9.5, ('#7fa4f0', '#4a72d8', '#26386e'))
    for y in [8, 12, 16]:
        for x in range(2, 22):
            if s.get(x, y) != '.' and abs(x - cx) < 9: s.set(x, y, '#3a5cb0')
    for y in range(8, 11):
        for x in range(14, 18):
            if s.get(x, y) != '.': s.set(x, y, '#1d2b56')
    ering(s, cx, cy, 12.5, 3.0, '#8fa8e8', th=.35, tilt=-0.22)

@reg('pluto')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 7.5, ('#e4d8c2', '#c8b49a', '#867760'))
    for y in range(11, 17):
        for x in range(8, 17):
            if s.get(x, y) != '.' and (abs(x - 12) + abs(y - 13) * 1.1) < 5.2: s.set(x, y, '#f2ead8')
    crater(s, 9, 8, 1.6, '#9d8b72'); crater(s, 15, 7, 1.2, '#9d8b72')
    disc(s, 20.5, 4.5, 2.6, '#9aa0b4'); disc(s, 20.0, 4.0, 1.2, '#c3c8d6')

@reg('titan')
def _(s, rng, cx, cy, _r):
    disc(s, cx, cy, 10.5, '#a87a30')
    sphere(s, cx, cy, 9, ('#f6c983', '#e0a24a', '#96661f'))
    for y in [9, 13, 17]:
        for x in range(3, 21):
            if s.get(x, y) != '.' and abs(x - cx) < 8.4: s.set(x, y, '#c68a38')
    for x in range(8, 17):
        if s.get(x, 16) != '.': s.set(x, 16, '#5f8fa0')
    for x in range(9, 15):
        if s.get(x, 17) != '.': s.set(x, 17, '#4f7f92')

@reg('io')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 9, ('#f8ee9a', '#e8d466', '#a89a30'))
    for (x, y, r) in [(9, 10, 2.2), (15, 14, 1.8), (14, 8, 1.2), (10, 15, 1.4)]:
        crater(s, x, y, r, '#c4482e', '#e8724a')
    for k in range(4): s.set(9 - k // 2, 3 - k, '#ffcf8a')
    s.set(9, 1, '#ffe9b8'); s.set(8, 0, '#ffe9b8')

@reg('rogue')
def _(s, rng, cx, cy, _r):
    sphere(s, cx, cy, 9.5, ('#6a6284', '#413a58', '#221f30'), rim='#8f8fc0')
    for (x, y, r) in [(9, 9, 2.4), (15, 14, 1.8)]: crater(s, x, y, r, '#2c2740')
    for (x, y) in [(1, 4), (22, 3), (2, 20), (21, 19), (12, 0), (0, 12)]: s.set(x, y, '#9aa4d0')

@reg('oort')
def _(s, rng, cx, cy, _r):
    def ice(x0, y0, hh, ww):
        for k in range(hh):
            w = int(ww * (1 - abs(k - hh * .4) / (hh * .8)))
            for x in range(-max(0, w), max(0, w) + 1):
                s.set(x0 + x, y0 + k, '#7fa8d8' if x > 0 else ('#eaf6ff' if x < 0 else '#bfe0ff'))
    ice(9, 4, 12, 3); ice(17, 10, 8, 2); ice(5, 12, 7, 2)
    for (x, y) in [(2, 3), (21, 5), (20, 20), (3, 21)]: s.set(x, y, '#cfe4ff')

@reg('m1', 28, 28)
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 13.0, 10.5, ['#ffb489', '#c4523c', '#7a2f22'], n=300)
    for a in [0.2, 1.1, 2.0, 2.9, 3.8, 4.7, 5.6]:
        for t in range(4, 14):
            s.set(cx + math.cos(a) * t - .5, cy + math.sin(a) * t * .8 - .5, '#ff9a6a')
    disc(s, cx, cy, 2.2, '#fff6e0')
    for k in range(5, 11):
        s.set(cx - .5, cy - k, '#bfe0ff'); s.set(cx - .5, cy + k - 1, '#bfe0ff')

@reg('m13', 28, 28)
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 13, 13, ['#6a5f3f', '#4a4230', '#332d20'], n=150)
    for i in range(150):
        a = rng.random() * 2 * math.pi
        u = rng.random() ** 2.1
        x, y = cx + math.cos(a) * 13 * u, cy + math.sin(a) * 13 * u
        s.set(round(x - .5), round(y - .5), '#fff4d8' if u < .45 else '#e8dcb0')
    disc(s, cx, cy, 2.4, '#fffdf0')

@reg('blackhole', 28, 28)
def _(s, rng, cx, cy, _r):
    ering(s, cx, cy, 13.0, 4.2, '#7a5ac8', th=1.4, tilt=-0.32)
    ering(s, cx, cy, 12.0, 3.8, '#ffbe6e', th=1.0, tilt=-0.32)
    ering(s, cx, cy, 10.0, 3.0, '#ffe1aa', th=.7, tilt=-0.32)
    disc(s, cx, cy, 6.4, '#05060c')
    ering(s, cx, cy, 6.6, 6.6, '#ffd28c', th=.5)
    for a in [0.6, 2.4, 4.1]:
        for t in range(8, 13):
            s.set(cx + math.cos(a) * t - .5, cy + math.sin(a) * t * .45 - .5, '#ffeccb')

# ── 3막 (v0.21 신설) ──
@reg('whitedwarf')
def _(s, rng, cx, cy, _r):
    disc(s, cx, cy, 8.5, '#2a4a7a'); disc(s, cx, cy, 6.0, '#5f8fd0')
    disc(s, cx, cy, 4.0, '#bfe0ff'); disc(s, cx, cy, 2.4, '#ffffff')
    star4(s, 12, 12, 11, '#8fc4f0', '#ffffff')
    for (x, y) in [(3, 4), (20, 5), (5, 19), (19, 18)]: s.set(x, y, '#cfe4ff')

@reg('neutron')
def _(s, rng, cx, cy, _r):
    for k in range(12):
        w = 1 + k // 4
        for j in range(w):
            s.set(cx - .5 + j, cy - .5 - k, '#9fd6ff'); s.set(cx - .5 - j, cy - .5 + k, '#9fd6ff')
    ering(s, cx, cy, 7.5, 3.0, '#3f6faa', th=.6, tilt=0.35)
    disc(s, cx, cy, 2.6, '#eaf6ff'); disc(s, cx, cy, 1.4, '#ffffff')

@reg('magnetar')
def _(s, rng, cx, cy, _r):
    for rr in (5.5, 8.0, 10.5):
        ering(s, cx, cy, rr * .5, rr, '#7a3fc0' if rr > 8 else '#b070e8', th=.5, tilt=0.5)
    disc(s, cx, cy, 3.2, '#ffe9ff'); disc(s, cx, cy, 1.8, '#ffffff')
    for (x, y) in [(4, 6), (19, 7), (6, 18), (18, 17)]: s.set(x, y, '#d8a8ff')

@reg('darkneb')
def _(s, rng, cx, cy, _r):
    for _ in range(120):
        x, y = rng.randrange(24), rng.randrange(24)
        s.set(x, y, rng.choice(['#ffffff', '#cfd8ef', '#9fb0d8', '#cfd8ef']))
    cloud(s, rng, cx, cy, 10.5, 9.5, ['#2c2340', '#171029', '#080512'], n=380)
    cloud(s, rng, cx + 3, cy - 3, 4.5, 3.6, ['#3d3254'], n=55)

@reg('snr')
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 11.0, 10.0, ['#5a2a20', '#8a3f2c', '#c4603c', '#ffb08a'], n=260, hollow=.42)
    ering(s, cx, cy, 10.0, 9.0, '#ffd0a8', th=.5)
    for _ in range(14):
        a = rng.random() * 2 * math.pi
        s.set(cx + math.cos(a) * 11.5 - .5, cy + math.sin(a) * 10.5 - .5, '#fff0d0')
    disc(s, cx, cy, 1.6, '#ffe9c8')

@reg('ghost')
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 10.0, 5.2, ['#cfd8ef', '#8f9fc0', '#5a6a8a'], n=200)
    spiral(s, cx, cy, 10.0, '#e8eeff', arms=2, turns=1.0, tilt=-0.35, squash=.44, spread=2)
    disc(s, cx, cy, 2.4, '#ffffff')

@reg('lmc')
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx - 1, cy, 8.5, 6.0, ['#dfe6ff', '#98a4cc', '#5f6a90'], n=190)
    cloud(s, rng, cx + 5, cy + 4, 3.5, 2.8, ['#cfd8ef', '#8f9ac0'], n=45)
    for _ in range(10): s.set(rng.randrange(24), rng.randrange(24), '#ffffff')

@reg('satgal')
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 7.0, 4.2, ['#efe8ff', '#b0a4dc', '#6f6498'], n=95)
    disc(s, cx, cy, 1.6, '#fff8e8')

@reg('m31', 28, 28)
def _(s, rng, cx, cy, _r):
    cloud(s, rng, cx, cy, 13.0, 6.2, ['#8f84c0', '#5f568c', '#3c3560'], n=240)
    spiral(s, cx, cy, 13.0, '#c8bff0', arms=2, turns=1.15, tilt=-0.42, squash=.40, spread=2)
    spiral(s, cx, cy, 10.0, '#e6dfff', arms=2, turns=1.05, tilt=-0.42, squash=.40)
    disc(s, cx, cy, 3.0, '#fff2c0'); disc(s, cx, cy, 1.6, '#ffffff')
    for _ in range(18): s.set(rng.randrange(28), rng.randrange(28), '#d8d0f0')

@reg('quasar', 28, 28)
def _(s, rng, cx, cy, _r):
    ering(s, cx, cy, 11.0, 3.4, '#a86a2a', th=1.0, tilt=-0.25)
    ering(s, cx, cy, 8.5, 2.6, '#e8a44a', th=.6, tilt=-0.25)
    for k in range(1, 14):
        w = 1 + k // 5
        for j in range(w):
            s.set(cx - .5 + j, cy - .5 - k, '#9fd6ff'); s.set(cx - .5 - j, cy - .5 + k, '#5f9ad8')
    disc(s, cx, cy, 3.6, '#ffe9a8'); disc(s, cx, cy, 2.0, '#ffffff')
    star4(s, int(cx), int(cy), 12, '#ffe9a8', '#ffffff')

@reg('darkmatter', 28, 28)
def _(s, rng, cx, cy, _r):
    for _ in range(60): s.set(rng.randrange(28), rng.randrange(28), '#cfd8ef')
    cloud(s, rng, cx, cy, 12.0, 12.0, ['#0d0a18', '#0a0812', '#07050e'], n=380)
    for rr, col in ((12.5, '#6f5fb0'), (10.5, '#b9a6ff')):
        for a in (0.5, 2.6, 3.9, 5.6):
            for t in range(-9, 10):
                aa = a + t * .035
                s.set(cx + math.cos(aa) * rr - .5, cy + math.sin(aa) * rr - .5, col)
    for _ in range(9):
        a = rng.random() * 2 * math.pi
        s.set(cx + math.cos(a) * 13.0 - .5, cy + math.sin(a) * 13.0 - .5, '#ffffff')

# ───────── 주입 ─────────
def main():
    if len(sys.argv) < 2:
        print("사용법: python gen_pixel_art.py <빌드html>"); return
    path = sys.argv[1]
    js = 'const PIXEL_ART=' + json.dumps(SPR, ensure_ascii=False, separators=(',', ':')) + ';/*PIXEL_ART_DATA*/'
    src = io.open(path, encoding='utf-8').read()
    import re
    new, cnt = re.subn(r'const PIXEL_ART=.*?;/\*PIXEL_ART_DATA\*/', lambda m: js, src, count=1, flags=re.S)
    if not cnt:
        print("주입 자리(/*PIXEL_ART_DATA*/)를 찾지 못했다."); return
    io.open(path, 'w', encoding='utf-8').write(new)
    print("스프라이트 %d종 주입 (%.1fKB)" % (len(SPR), len(js) / 1024))
    print(" ".join(sorted(SPR)))

if __name__ == '__main__':
    main()
