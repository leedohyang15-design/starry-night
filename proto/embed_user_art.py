# -*- coding: utf-8 -*-
"""사용자 제공 아트를 프로토타입에 임베드한다 (v0.8).

사용법:  python embed_user_art.py [빌드html]   (기본: starry-night-proto-v0.8.html)

- 조력자 초상: ../조력자/{galilei,copernicus,brahe}-talk-sheet.png (2048×512 = 512² 4프레임)
  → 프레임별 크롭 (88,0,424,512) → NEAREST 높이 132px → PNG base64 4프레임 배열
- 성좌 삽화: ../별자리 그림/plate-black.webp (1536×1024, **검은 배경** 판화 10종 + 한글 라벨)
  → 3행 고정 격자 → 셀별 밝기(루마) 기반 누끼로 알파 생성 → 라벨 밴드 제거
  → LANCZOS 최대 240px → WebP q80 base64
  ※ 검은 배경이라 루마를 그대로 알파로 쓰면 얇은 판화 획까지 살아남는다 (구 알파 누끼판보다 깨끗).

HTML의 /*UART-START*/~/*UART-END*/ 블록을 통째로 교체(멱등). 재실행해도 결과 동일.
검증용 콘택트 시트(uart_contact.png)를 같은 폴더에 남긴다.
"""
import base64, io, json, os, re, sys
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLATE = os.path.join(ROOT, '별자리 그림', 'plate-black.webp')

# 검은 배경 판 배치 (왼쪽 위부터, 행별) — 게임의 10개 별자리와 정확히 일치
PLATE_ROWS = [['sgr', 'lib', 'uma'],
              ['umi', 'cas', 'ori', 'gem'],
              ['cyg', 'leo', 'sco']]

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

# ── 성좌 삽화 (검은 배경 → 루마 누끼) ──
def bands(flags, gap):
    """True 구간 목록 — gap보다 짧은 틈은 이어붙인다"""
    out, start = [], None
    for i, v in enumerate(flags):
        if v and start is None: start = i
        if not v and start is not None:
            out.append([start, i]); start = None
    if start is not None: out.append([start, len(flags)])
    merged = []
    for b in out:
        if merged and b[0] - merged[-1][1] < gap: merged[-1][1] = b[1]
        else: merged.append(b)
    return merged

def luma_cut(cell, floor=26, ceil=120):
    """검은 배경 컷아웃 — 밝기를 알파로 (floor 이하 = 완전 투명, ceil 이상 = 불투명)"""
    rgb = cell.convert('RGB')
    lum = rgb.convert('L')
    a = lum.point(lambda v: 0 if v <= floor else (255 if v >= ceil else int((v - floor) * 255 / (ceil - floor))))
    a = a.filter(ImageFilter.MedianFilter(3))   # 배경의 압축 잡티 제거
    out = rgb.convert('RGBA')
    out.putalpha(a)
    return out

def strip_label(cell):
    """한글 라벨 글자만 지운다 — 연결 성분 필터.

    y띠로 잘라내면 그림이 라벨 높이까지 내려온 칸(오리온의 발·쌍둥이 다리)이 함께 잘린다.
    라벨 글자는 셀 하단에 있는 '작고 낮은' 성분들이므로, 크기와 위치로만 골라 지운다.
    """
    import numpy as np
    from scipy import ndimage
    a = np.array(cell.getchannel('A'))
    h, w = a.shape
    lab, n = ndimage.label(a > 60)
    if n == 0: return cell
    sizes = ndimage.sum(a > 60, lab, range(1, n + 1))
    biggest = sizes.max()
    objs = ndimage.find_objects(lab)
    kill = np.zeros_like(a, dtype=bool)
    for i, sl in enumerate(objs):
        if sl is None: continue
        ys, xs = sl
        oh, ow = ys.stop - ys.start, xs.stop - xs.start
        area = sizes[i]
        if lab[ys, xs].size == 0: continue
        # 글자 판정: 하단 28% 안에서 시작 · 낮고(≤h*0.14) 지나치게 넓지 않으며(≤w*0.62)
        #            면적이 글자 규모(≤h*w*0.02)이고 본체가 아니다
        is_label = (ys.start > h * 0.72 and oh <= h * 0.14
                    and ow <= w * 0.62 and area <= h * w * 0.02 and area < biggest * 0.5)
        # 배경 압축 잡티: 아주 작은 점 (어디에 있든)
        is_speck = area <= 12
        if is_label or is_speck:
            kill |= (lab == i + 1)
    # v0.12 추가 — ① 셀 위 가장자리에 걸린 이웃 행 잔재(납작한 조각) 제거
    for i, sl in enumerate(objs):
        if sl is None: continue
        ys, xs = sl
        oh, ow = ys.stop - ys.start, xs.stop - xs.start
        if ys.stop < h * 0.10 and oh <= h * 0.08 and sizes[i] < biggest * 0.5:
            kill |= (lab == i + 1)
    # ② 본체와 픽셀로 이어진 하단 낱글자("쌍" 사건) — 침식으로 연결을 끊어 분리 제거
    mask = a > 60
    er = ndimage.binary_erosion(mask, iterations=1)
    lab2, n2 = ndimage.label(er)
    if n2:
        sizes2 = ndimage.sum(er, lab2, range(1, n2 + 1))
        big2 = sizes2.max()
        for i, sl in enumerate(ndimage.find_objects(lab2)):
            if sl is None: continue
            ys, xs = sl
            oh, ow = ys.stop - ys.start, xs.stop - xs.start
            if (ys.start > h * 0.80 and oh <= h * 0.13 and ow <= w * 0.18
                    and sizes2[i] < big2 * 0.5):
                glyph = ndimage.binary_dilation(lab2 == i + 1, iterations=2) & mask
                kill |= glyph
    if kill.any():
        a[kill] = 0
        out = cell.copy()
        out.putalpha(Image.fromarray(a))
        return out
    return cell

def plate_cells(art, contact):
    im = Image.open(PLATE).convert('RGB')
    W, H = im.size
    rh = H / len(PLATE_ROWS)
    for ri, names in enumerate(PLATE_ROWS):
        y0, y1 = int(ri * rh), int((ri + 1) * rh)
        cw = W / len(names)
        for ci, name in enumerate(names):
            x0, x1 = int(ci * cw), int((ci + 1) * cw)
            cell = luma_cut(im.crop((x0, y0, x1, y1)))
            cell = strip_label(cell)
            bbox = cell.getbbox()
            if bbox: cell = cell.crop(bbox)
            cell.thumbnail((240, 240), Image.LANCZOS)
            art['con_' + name] = b64(cell, 'WEBP', quality=80, method=6)
            contact.append((name, cell))
            print(f'  삽화 {name}: {cell.size}')

def main(path):
    art, contact = {}, []
    print('조력자 talk-sheet →')
    portraits(art)
    print('성좌 삽화 (검은 배경 누끼) →')
    plate_cells(art, contact)
    assert len([k for k in art if k.startswith('con_')]) == 10, '삽화 10종이 아니다'
    # 콘택트 시트 (육안 검증용 — .gitignore 대상)
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
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'starry-night-proto-v0.8.html'))
