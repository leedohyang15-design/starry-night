#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_conart5.py — v0.16: 본편 성좌 각인 판(별자리 그림/plate1·2-cutout.png)에서
v0.24 신규 별자리 2종(dra·aur)의 판화를 잘라 USER_ART에 추가한다.
칸 절단 로직은 저장소 embed_conart2.py(v0.42 연결 성분 라벨 제거)를 그대로 따른다.
사용: python embed_conart5.py <프로토html>   (멱등 — con_per 등 기존 키는 갈아끼움)
"""
import base64, io, os, re, sys
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
# embed_conart2.py의 시트 밴드 정의에서 필요한 5종만
SHEETS = [
    ('별자리 그림/plate2-cutout.png', [
        ((364, 617), ['auriga', 'corvus', 'cancer', 'sagittarius', 'corona']),
        ((678, 951), ['perseus', 'cetus', 'cepheus', 'draco']),
    ]),
]
WANT = {'draco': 'dra', 'auriga': 'aur'}
MAXSIDE, QUALITY = 330, 62

def bands(on, min_gap, min_len):
    segs, s = [], None
    for i, v in enumerate(list(on) + [False]):
        if v and s is None: s = i
        if not v and s is not None:
            segs.append([s, i]); s = None
    merged = [segs[0]]
    for a, b in segs[1:]:
        if a - merged[-1][1] < min_gap: merged[-1][1] = b
        else: merged.append([a, b])
    return [x for x in merged if x[1] - x[0] >= min_len]

arts = {}
for path, layout in SHEETS:
    rgba = np.asarray(Image.open(os.path.join(ROOT, path)).convert('RGBA'))
    mask = rgba[:, :, 3] > 8
    for (y0, y1), keys in layout:
        cols = bands(mask[y0:y1].sum(0) > 8, 16, 40)
        if len(cols) != len(keys):
            cols = bands(mask[y0+60:y1].sum(0) > 8, 16, 40)
        assert len(cols) == len(keys), (path, y0, len(cols), len(keys))
        for (x0, x1), key in zip(cols, keys):
            if key not in WANT: continue
            cell = rgba[y0:y1, x0:x1]
            m2 = mask[y0:y1, x0:x1]
            yb = bands(m2.sum(1) > 2, 6, 4)
            if len(yb) >= 2 and (yb[-1][1] - yb[-1][0]) <= 40:
                yc = yb[-2][1]
                cell, m2 = cell[:yc], m2[:yc]
            lab_arr, n = ndimage.label(m2)
            if n > 1:
                sizes = ndimage.sum(m2, lab_arr, range(1, n + 1))
                keep = np.ones(n + 1, bool)
                for ci, sl in enumerate(ndimage.find_objects(lab_arr)):
                    h_ = sl[0].stop - sl[0].start
                    if sizes[ci] < 1400 and h_ <= 48 and sl[0].start < 70:
                        keep[ci + 1] = False
                m2 = keep[lab_arr] & m2
                cell = cell.copy(); cell[~m2] = 0
            ys, xs = np.where(m2)
            cell = cell[ys.min():ys.max()+1, xs.min():xs.max()+1]
            pic = Image.fromarray(cell, 'RGBA')
            sc = MAXSIDE / max(pic.size)
            if sc < 1: pic = pic.resize((round(pic.width*sc), round(pic.height*sc)), Image.LANCZOS)
            a2 = pic.getchannel('A').point(lambda v: 0 if v < 40 else 96 if v < 128 else 192 if v < 208 else 255)
            pic.putalpha(a2)
            buf = io.BytesIO(); pic.save(buf, 'WEBP', quality=QUALITY)
            arts['con_' + WANT[key]] = 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()

print('잘라낸 각인:', sorted(arts), '총', sum(map(len, arts.values()))//1024, 'KB')
html = sys.argv[1]
s = open(html, encoding='utf-8').read()
m = re.search(r'const USER_ART=\{([\s\S]*?)\};', s)
assert m, 'USER_ART 블록을 찾지 못함'
body = m.group(1)
for k, v in arts.items():
    body = re.sub(r',?"%s":"data:image/webp;base64,[^"]*"' % k, '', body)  # 멱등
    body += f',"{k}":"{v}"'
s = s[:m.start()] + 'const USER_ART={' + body + '};' + s[m.end():]
open(html, 'w', encoding='utf-8').write(s)
print(html, '주입 완료')
