#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_conart2.py — v0.38 별자리 판화 시트 2장(별자리 그림/별자리그림1·2.png)을 32장으로 잘라 CON_IMG 주입.
검은 배경 판화 스타일이라 누끼 대신 **불투명 WebP + CSS mix-blend-mode:screen**(검정=투명과 동일)을 쓴다
— 알파 평면이 빠져 파일이 절반 이하가 된다. 빌드 CSS의 .cfig/.stagefig/.conimg에 blend가 걸려 있어야 한다.
각 칸 아래의 별자리 이름 라벨은 잘라낸다(라벨 = 칸 하단의 낮은 텍스트 띠).
사용: python embed_conart2.py <빌드html>  ·  --dump out/ 로 검수용 저장
"""
import base64, io, os, re, sys
import numpy as np
from PIL import Image

# 행 밴드는 수동 확정(라벨 띠 제외한 그림 영역) — 자동 행 검출은 행이 서로 붙어 실패했다
SHEETS = [
    ('별자리 그림/별자리그림1.png', [
        ((22, 263),  ['canis','orion','gemini','taurus','scorpius']),
        ((308, 518), ['leo','virgo','bootes','lyra','cygnus','aquila']),
        ((552, 751), ['pegasus','ursa','ursaminor','cassiopeia','andromeda']),
        ((809, 976), ['piscis','pisces']),
    ]),
    ('별자리 그림/별자리그림2.png', [
        ((32, 309),  ['aries','libra','capricornus','aquarius','canisminor']),
        ((365, 616), ['auriga','corvus','cancer','sagittarius','corona']),
        ((682, 951), ['perseus','cetus','cepheus','draco']),
    ]),
]
LUM_T = 28        # 배경 판정 밝기
MAXSIDE = 380
QUALITY = 70

def bands(on, min_gap, min_len):
    """불리언 프로파일의 참 구간들 — min_gap 미만 틈은 이어붙이고 min_len 미만은 버린다"""
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

def main():
    dump = '--dump' in sys.argv
    outdir = sys.argv[sys.argv.index('--dump')+1] if dump else None
    html = next((a for a in sys.argv[1:] if a.endswith('.html')), None)
    arts = {}
    for path, layout in SHEETS:
        im = np.asarray(Image.open(path).convert('RGB')).astype(np.uint16)
        mask = im.max(2) > LUM_T
        for (y0, y1), keys in layout:
            cols = bands(mask[y0:y1].sum(0) > 8, 16, 40)
            assert len(cols) == len(keys), (path, y0, len(cols), len(keys))
            for (x0, x1), key in zip(cols, keys):
                sub = im[y0:y1, x0:x1]
                m2 = mask[y0:y1, x0:x1]
                yb = bands(m2.sum(1) > 2, 6, 4)   # 칸 하단에 삐져 들어온 라벨 글자 조각 제거
                if len(yb) >= 2 and (yb[-1][1] - yb[-1][0]) <= 40:
                    yc = yb[-2][1]
                    sub, m2 = sub[:yc], m2[:yc]
                ys, xs = np.where(m2)
                sub = sub[ys.min():ys.max()+1, xs.min():xs.max()+1]
                pic = Image.fromarray(sub.astype(np.uint8), 'RGB')   # 불투명 — 표시 시 screen 블렌드
                sc = MAXSIDE / max(pic.size)
                if sc < 1: pic = pic.resize((round(pic.width*sc), round(pic.height*sc)), Image.LANCZOS)
                if dump:
                    os.makedirs(outdir, exist_ok=True); pic.save(os.path.join(outdir, key+'.png'))

                buf = io.BytesIO(); pic.save(buf, 'WEBP', quality=QUALITY)
                arts[key] = 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()
    print('잘라낸 별자리:', len(arts))
    if html:
        s = open(html, encoding='utf-8').read()
        pat = re.compile(r'const CON_IMG=\{.*?\};/\*CON_IMG_DATA\*/', re.S)
        assert len(pat.findall(s)) == 1
        obj = 'const CON_IMG={' + ','.join(f"{k}:'{v}'" for k, v in arts.items()) + '};/*CON_IMG_DATA*/'
        s = pat.sub(lambda m: obj, s, count=1)
        open(html, 'w', encoding='utf-8').write(s)
        print(f'{html} 주입 완료 — base64 총 {sum(map(len,arts.values()))//1024}KB')

if __name__ == '__main__':
    main()
