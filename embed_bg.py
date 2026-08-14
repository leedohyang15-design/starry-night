#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_bg.py — v0.41 사계절 픽셀 밤하늘 배경(배경/*.png, 1280×720) → SEASON_BG 주입.
픽셀 아트라 WebP 무손실. 그림 교체 시 png 갈아끼우고 재실행: python embed_bg.py <빌드html>"""
import base64, io, re, sys
from PIL import Image

MAP = {'봄': '배경/nightsky-spring.png', '여름': '배경/nightsky-summer.png',
       '가을': '배경/nightsky-autumn.png', '겨울': '배경/nightsky-winter.png'}

def main(html):
    vals = {}
    for k, path in MAP.items():
        im = Image.open(path).convert('RGB')   # 배경은 불투명 — 알파 불필요
        buf = io.BytesIO(); im.save(buf, 'WEBP', lossless=True)
        vals[k] = 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()
    s = open(html, encoding='utf-8').read()
    pat = re.compile(r'const SEASON_BG=\{.*?\};', re.S)
    assert len(pat.findall(s)) == 1
    obj = 'const SEASON_BG={' + ','.join(f"'{k}':'{v}'" for k, v in vals.items()) + '};'
    s = pat.sub(lambda m: obj, s, count=1)
    open(html, 'w', encoding='utf-8').write(s)
    print(f'배경 4계절 주입 — base64 총 {sum(map(len,vals.values()))//1024}KB')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'starry-night-v0.41.html')
