#!/usr/bin/env python3
"""v0.38 조력자 4프레임 임베드 — 조력자/<이름>-talk-sheet.png (2048×512, 512×512×4, 투명 배경)
프레임: 0 기본(입다뭄) · 1 입엶 · 2 입활짝 · 3 눈감음
공통 크롭 (88,0,424,512) — 7인 전원 같은 512 격자에 그려져 있어 키 정규화가 자동으로 맞는다.
1/2 NEAREST 축소(8px 블록 → 4px, 도트 보존) → WebP 무손실(알파) → base64 주입.
사용: python embed_talk_sheets.py <빌드html>
"""
import base64, io, re, sys
from PIL import Image

FILES = {  # 파일명 → 게임 키
    'galilei': 'galileo', 'brahe': 'brahe', 'herschel': 'herschel', 'kepler': 'kepler',
    'copernicus': 'copernicus', 'hubble': 'hubble', 'leavitt': 'leavitt',
}
CROP = (88, 0, 424, 512)   # x 96~416 사용 — 좌우 8px 여유
OUT_W, OUT_H = 168, 256

def frame_uri(sheet, i):
    fr = sheet.crop((i*512, 0, (i+1)*512, 512)).crop(CROP)
    fr = fr.resize((OUT_W, OUT_H), Image.NEAREST)
    buf = io.BytesIO()
    fr.save(buf, 'WEBP', lossless=True)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()

def main(html):
    tabs = {0: {}, 1: {}, 2: {}, 3: {}}
    for fn, key in FILES.items():
        sheet = Image.open(f'조력자/{fn}-talk-sheet.png').convert('RGBA')
        assert sheet.size == (2048, 512), (fn, sheet.size)
        for i in range(4):
            tabs[i][key] = frame_uri(sheet, i)
    s = open(html, encoding='utf-8').read()
    def obj(d):
        return '{' + ','.join(f"'{k}':'{v}'" for k, v in d.items()) + '};'
    names = {0: 'PORTRAIT_IMG', 1: 'PORTRAIT_OPEN', 2: 'PORTRAIT_WIDE', 3: 'PORTRAIT_BLINK'}
    for i in (0, 1):
        pat = re.compile('const ' + names[i] + r'=\{.*?\};', re.S)
        assert len(pat.findall(s)) == 1, names[i]
        s = pat.sub(lambda m: 'const ' + names[i] + '=' + obj(tabs[i]), s, count=1)
    for i in (2, 3):   # 신규 표는 OPEN 뒤에 삽입 (이미 있으면 교체)
        pat = re.compile('const ' + names[i] + r'=\{.*?\};', re.S)
        if pat.search(s):
            s = pat.sub(lambda m: 'const ' + names[i] + '=' + obj(tabs[i]), s, count=1)
        else:
            anchor = re.search(r'const PORTRAIT_OPEN=\{.*?\};', s, re.S).group(0)
            s = s.replace(anchor, anchor + '\nconst ' + names[i] + '=' + obj(tabs[i]))
    open(html, 'w', encoding='utf-8').write(s)
    kb = sum(len(v) for t in tabs.values() for v in t.values()) // 1024
    print(f'주입 완료 — 7인 × 4프레임 ({OUT_W}×{OUT_H}, base64 총 {kb}KB)')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'starry-night-v0.38.html')
