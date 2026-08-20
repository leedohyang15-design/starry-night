# -*- coding: utf-8 -*-
"""사용자 제공 아트를 프로토타입에 임베드한다 (v0.6).

사용법:  python embed_user_art.py [빌드html]   (기본: starry-night-proto-v0.6.html)

- 조력자 초상: ../조력자/{galilei,copernicus,brahe}-talk-sheet.png (2048×512 = 512² 4프레임)
  → 프레임별 크롭 (88,0,424,512) → NEAREST 높이 132px → PNG base64 4프레임 배열
- 성좌 삽화: ../별자리 그림/plate1·2-cutout.png (1536×1024, 알파 누끼 + 칸 아래 한글 라벨)
  → 알파 투영으로 행/열 분할 → 라벨 밴드 제거 → LANCZOS 최대 240px → WebP q80 base64

HTML의 /*UART-START*/~/*UART-END*/ 블록을 통째로 교체(멱등). 재실행해도 결과 동일.
검증용 콘택트 시트(uart_contact.png)를 같은 폴더에 남긴다.
"""
import base64, io, json, os, re, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 판 배치 (왼쪽 위부터, 행별) — 고정 격자와 이 순서를 짝지어 이름을 붙인다
PLATE1_ROWS = [['cma', 'ori', 'gem', 'tau', 'sco'],
               ['leo', 'vir', 'boo', 'lyr', 'cyg', 'aql'],
               ['peg', 'uma', 'umi', 'cas', 'and'],
               ['psa', 'psc']]
PLATE2_ROWS = [['aries', 'lib', 'cap', 'aqr', 'cmi'],
               ['aur', 'crv', 'cnc', 'sgr', 'crb'],
               ['per', 'cet', 'cep', 'dra']]
NEED = {'lib', 'sgr', 'ori', 'gem', 'sco', 'leo', 'cyg', 'uma', 'umi', 'cas'}  # 이번 빌드 10종

def b64(im, fmt='PNG', **kw):
    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    mime = 'image/webp' if fmt == 'WEBP' else 'image/png'
    return f'data:{mime};base64,' + base64.b64encode(buf.getvalue()).decode()

# ── 조력자 초상 ──
def portraits(art):
    for key, fname in (('galileo', 'galilei'), ('copernicus', 'copernicus'), ('brahe', 'brahe')):
        sheet = Image.open(os.path.join(ROOT, '조력자', f'{fname}-talk-sheet.png')).convert('RGBA')
        frames = []
        for f in range(4):
            fr = sheet.crop((512 * f + 88, 0, 512 * f + 424, 512))
            fr = fr.resize((87, 132), Image.NEAREST)
            frames.append(b64(fr.quantize(64).convert('RGBA'), 'PNG', optimize=True))
        art['al_' + key] = frames
        print(f'  초상 {key}: 4프레임')

# ── 성좌 삽화 — 알파 투영 분할 ──
def bands(profile, gap):
    """0이 아닌 구간(밴드) 목록 — gap보다 짧은 틈은 무시하고 이어붙인다"""
    out, start = [], None
    for i, v in enumerate(profile):
        if v and start is None: start = i
        if not v and start is not None:
            out.append([start, i]); start = None
    if start is not None: out.append([start, len(profile)])
    merged = []
    for b in out:
        if merged and b[0] - merged[-1][1] < gap: merged[-1][1] = b[1]
        else: merged.append(b)
    return merged

def plate_cells(im, rows_layout, art, contact):
    W, H = im.size
    apx = im.getchannel('A').load()
    # 행은 고정 격자 (라벨 텍스트가 행 사이 여백에 걸쳐 있어 투영 분할이 안 된다)
    rh = H / len(rows_layout)
    row_bands = [(int(i * rh), int((i + 1) * rh)) for i in range(len(rows_layout))]
    for ri, ((y0, y1), names) in enumerate(zip(row_bands, rows_layout)):
        # 열도 고정 격자 — 시트는 행마다 균등 배치돼 있다 (스케치 잔점이 셀 사이까지 퍼져 투영 분할 불가)
        cw_row = W / len(names)
        # 라벨이 행 경계에 걸친다: 2행부터 위 36px = 윗행 라벨 넘침, 아래 12px = 자기 라벨 슬리버
        cy0 = y0 + (36 if ri > 0 else 0)
        cy1 = y1 - 12
        for ci, name in enumerate(names):
            if name not in NEED: continue
            x0, x1 = int(ci * cw_row), int((ci + 1) * cw_row)
            cell = im.crop((x0, cy0, x1, cy1)).copy()
            cw, ch = cell.size
            # 옆 칸에서 넘어온 잔재 차단: 좌우 가장자리 8px 알파 제거
            a_ch = cell.getchannel('A')
            ap = a_ch.load()
            for y in range(ch):
                for x in list(range(0, 8)) + list(range(cw - 8, cw)):
                    ap[x, y] = 0
            cell.putalpha(a_ch)
            # 텍스트 밴드 제거: 짧고(높이<45px) 좁은(피크 밀도<60%) 밴드 = 라벨 (위·아래 모두)
            cys = [sum(1 for x in range(0, cw, 2) if ap[x, y] > 24) for y in range(ch)]
            cell_bands = bands([v > 0 for v in cys], 4)
            peaks = [max(cys[b[0]:b[1]]) for b in cell_bands]
            top = max(peaks) if peaks else 1
            keep = [b for b, p in zip(cell_bands, peaks) if not ((b[1] - b[0]) < 45 and p < top * 0.6)]
            if keep:
                cell = cell.crop((0, keep[0][0], cw, keep[-1][1]))
            bbox = cell.getbbox()
            if bbox: cell = cell.crop(bbox)
            cell.thumbnail((240, 240), Image.LANCZOS)
            art['con_' + name] = b64(cell, 'WEBP', quality=80, method=6)
            contact.append((name, cell))
            print(f'  삽화 {name}: {cell.size}')

def main(path):
    art = {}
    contact = []
    print('조력자 talk-sheet →')
    portraits(art)
    print('성좌 삽화 →')
    plate_cells(Image.open(os.path.join(ROOT, '별자리 그림', 'plate1-cutout.png')).convert('RGBA'), PLATE1_ROWS, art, contact)
    plate_cells(Image.open(os.path.join(ROOT, '별자리 그림', 'plate2-cutout.png')).convert('RGBA'), PLATE2_ROWS, art, contact)
    assert len([k for k in art if k.startswith('con_')]) == len(NEED), '삽화 수 불일치'
    # 콘택트 시트 (육안 검증용 — 저장소 커밋 대상 아님)
    sheet = Image.new('RGBA', (250 * 5, 260 * 2), (16, 20, 40, 255))
    for i, (name, cell) in enumerate(contact):
        sheet.paste(cell, (250 * (i % 5) + 5, 260 * (i // 5) + 10), cell)
    sheet.save(os.path.join(HERE, 'uart_contact.png'))
    # 주입
    src = open(path, encoding='utf-8').read()
    block = ('/*UART-START*/\nconst USER_ART=' +
             json.dumps(art, ensure_ascii=False, separators=(',', ':')) + ';\n/*UART-END*/')
    out, n = re.subn(r'/\*UART-START\*/.*?/\*UART-END\*/', lambda m: block, src, flags=re.S)
    assert n == 1, 'UART 마커를 찾지 못했다'
    open(path, 'w', encoding='utf-8').write(out)
    print(f'주입 완료 → {path} ({os.path.getsize(path)//1024}KB)')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'starry-night-proto-v0.6.html'))
