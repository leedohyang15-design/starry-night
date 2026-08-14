#!/usr/bin/env python3
"""v0.38 조력자 4프레임 임베드 + v0.42 계절 의상 — 
기본: 조력자/<이름>-talk-sheet.png (2048×512 = 512²×4: 기본·입엶·입활짝·눈감음, 투명 배경)
계절: 조력자/{spring,summer,autumn,winter}.png (2048×3584 = 4프레임(열)×7인(행), 같은 규격)
  행 순서 = 코페르니쿠스·브라헤·갈릴레오·케플러·허셜·리비트·허블 (얼굴 유사도로 확정)
공통 크롭 (88,0,424,512) → 1/2 NEAREST(도트 보존) → WebP 무손실 → PORTRAIT_* 4표 + PORTRAIT_SZN 주입.
사용: python embed_talk_sheets.py <빌드html>
"""
import base64, io, re, sys
from PIL import Image

FILES = {  # 파일명 → 게임 키
    'galilei': 'galileo', 'brahe': 'brahe', 'herschel': 'herschel', 'kepler': 'kepler',
    'copernicus': 'copernicus', 'hubble': 'hubble', 'leavitt': 'leavitt',
}
CROP = (88, 0, 424, 512)   # x 96~416 사용 — 좌우 8px 여유
SZN_SHEETS = {'봄': 'spring', '여름': 'summer', '가을': 'autumn', '겨울': 'winter'}
SZN_ROWS = ['copernicus', 'brahe', 'galileo', 'kepler', 'herschel', 'leavitt', 'hubble']
OUT_W, OUT_H = 168, 256

def frame_uri(sheet, i, row=0):
    fr = sheet.crop((i*512, row*512, (i+1)*512, (row+1)*512)).crop(CROP)
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
    szn = {}
    for kname, fname in SZN_SHEETS.items():
        sheet = Image.open(f'조력자/{fname}.png').convert('RGBA')
        assert sheet.size == (2048, 3584), (fname, sheet.size)
        szn[kname] = {who: [frame_uri(sheet, i, r) for i in range(4)] for r, who in enumerate(SZN_ROWS)}
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
    # v0.42: 계절 의상 — PORTRAIT_SZN[계절][인물] = [기본,입엶,입활짝,눈감음]
    sznjs = 'const PORTRAIT_SZN={' + ','.join(
        "'" + k + "':{" + ','.join(f"{w}:[{','.join(chr(39)+u+chr(39) for u in us)}]" for w, us in d.items()) + '}'
        for k, d in szn.items()) + '};'
    pat = re.compile(r'const PORTRAIT_SZN=\{.*?\};', re.S)
    if pat.search(s):
        s = pat.sub(lambda m: sznjs, s, count=1)
    else:
        anchor = re.search(r'const PORTRAIT_BLINK=\{.*?\};', s, re.S).group(0)
        s = s.replace(anchor, anchor + '\n' + sznjs)
    open(html, 'w', encoding='utf-8').write(s)
    kb = sum(len(v) for t in tabs.values() for v in t.values()) // 1024
    kb2 = sum(len(u) for d in szn.values() for us in d.values() for u in us) // 1024
    print(f'주입 완료 — 기본 28프레임 {kb}KB + 계절 의상 112프레임 {kb2}KB')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'starry-night-v0.38.html')
