#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_conart2.py — v0.40 별자리 판화 시트 2장(별자리 그림/plate1·2-cutout.png, **사용자 누끼 = 진짜 알파**)을
32장으로 잘라 CON_IMG 주입. 알파를 그대로 쓰고 WebP(알파)로 내보낸다 — v0.38의 screen 블렌드 우회는 폐기
(빌드 CSS의 .cfig/.stagefig/.conimg mix-blend-mode:screen도 함께 제거할 것).
각 칸 아래의 별자리 이름 라벨은 잘라낸다(라벨 = 칸 하단의 낮은 텍스트 띠).
사용: python embed_conart2.py <빌드html>  ·  --dump out/ 로 검수용 저장
"""
import base64, io, os, re, sys
import numpy as np
from PIL import Image

# 행 밴드는 수동 확정(라벨 띠 제외한 그림 영역) — 자동 행 검출은 행이 서로 붙어 실패했다
SHEETS = [
    ('별자리 그림/plate1-cutout.png', [
        ((19, 264),  ['canis','orion','gemini','taurus','scorpius']),
        ((306, 521), ['leo','virgo','bootes','lyra','cygnus','aquila']),
        ((548, 753), ['pegasus','ursa','ursaminor','cassiopeia','andromeda']),
        ((804, 977), ['piscis','pisces']),
    ]),
    ('별자리 그림/plate2-cutout.png', [
        ((32, 310),  ['aries','libra','capricornus','aquarius','canisminor']),
        ((364, 617), ['auriga','corvus','cancer','sagittarius','corona']),
        ((678, 951), ['perseus','cetus','cepheus','draco']),
    ]),
]
LUM_T = 28   # (알파 모드에선 미사용)        # 배경 판정 밝기
MAXSIDE = 330
QUALITY = 62

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
        rgba = np.asarray(Image.open(path).convert('RGBA'))
        im = rgba[:, :, :3].astype(np.uint16)
        mask = rgba[:, :, 3] > 8
        for (y0, y1), keys in layout:
            cols = bands(mask[y0:y1].sum(0) > 8, 16, 40)
            assert len(cols) == len(keys), (path, y0, len(cols), len(keys))
            for (x0, x1), key in zip(cols, keys):
                cell = rgba[y0:y1, x0:x1]
                m2 = mask[y0:y1, x0:x1]
                yb = bands(m2.sum(1) > 2, 6, 4)   # 칸 하단에 삐져 들어온 라벨 글자 조각 제거
                if len(yb) >= 2 and (yb[-1][1] - yb[-1][0]) <= 40:
                    yc = yb[-2][1]
                    cell, m2 = cell[:yc], m2[:yc]
                yb = bands(m2.sum(1) > 2, 6, 4)   # v0.41: 칸 **상단**에 붙은 윗행 라벨 조각도 제거
                if len(yb) >= 2 and (yb[0][1] - yb[0][0]) <= 40:
                    yc = yb[1][0]
                    cell, m2 = cell[yc:], m2[yc:]
                ys, xs = np.where(m2)
                cell = cell[ys.min():ys.max()+1, xs.min():xs.max()+1]
                pic = Image.fromarray(cell, 'RGBA')
                sc = MAXSIDE / max(pic.size)
                if sc < 1: pic = pic.resize((round(pic.width*sc), round(pic.height*sc)), Image.LANCZOS)
                # 알파 4단계 양자화 — 페더의 미세 계조가 WebP 알파 평면을 크게 만든다 (시각 차이는 미미)
                a2 = pic.getchannel('A').point(lambda v: 0 if v < 40 else 96 if v < 128 else 192 if v < 208 else 255)
                pic.putalpha(a2)
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
