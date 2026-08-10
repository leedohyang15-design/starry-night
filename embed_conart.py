# -*- coding: utf-8 -*-
"""
embed_conart.py v2 — 성좌 각인 시트(성좌각인.png)를 **누끼(배경 제거)** 후 17장으로 잘라
                     각각 WebP(알파) base64 데이터 URI로 빌드 HTML에 임베드.

사용:
  python embed_conart.py [대상html]       # 기본: 폴더에서 가장 최신 전투프로토타입_v*.html
  python embed_conart.py --dump out/      # HTML 주입 없이 잘린 이미지만 저장(검수용)

플레이스홀더(대상 HTML): const CON_IMG={};/*CON_IMG_DATA*/   ← 이 줄 전체를 생성 데이터로 교체
그림 교체 시: 성좌각인.png 갈아끼우고 이 스크립트 재실행.

배경 제거 원리
  ① 테두리에서 flood fill — 이웃 픽셀 대비 허용오차(TOL)로 번지므로 부드러운 그라데이션 배경을 따라간다
  ② 도형 안에 갇힌 배경 주머니(리라 현 사이·다리 사이 등)는 주변 배경색 추정치와 비교해 제거
  ③ 1px 침식 + 페더로 배경색 후광 제거
자르기: 알파 커버리지가 0인 가로 띠 → 3행, 각 행에서 넓은 세로 틈 순으로 6/6/5칸 분리 후 여백 트림
"""
import base64, io, os, re, sys, glob
from collections import deque
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, '성좌각인.png')
TOL = 9            # flood fill 허용오차(채널당)
MAXSIDE = 460      # 잘린 그림 긴 변 최대 픽셀
QUALITY = 80       # WebP 품질
# 시트 배치: 3행 × [6·6·5] — 라벨 순서 고정
LAYOUT = [
    ['canis', 'orion', 'gemini', 'taurus', 'scorpius', 'leo'],
    ['virgo', 'bootes', 'lyra', 'cygnus', 'aquila', 'pegasus'],
    ['ursa', 'ursaminor', 'cassiopeia', 'andromeda', 'piscis'],
]


def boxsum(m, r):
    """적분영상 박스합 (반지름 r)"""
    p = np.pad(m.astype(np.float64), ((1, 0), (1, 0)))
    c = p.cumsum(0).cumsum(1)
    ys = np.arange(m.shape[0]); xs = np.arange(m.shape[1])
    y0 = np.clip(ys - r, 0, m.shape[0]); y1 = np.clip(ys + r + 1, 0, m.shape[0])
    x0 = np.clip(xs - r, 0, m.shape[1]); x1 = np.clip(xs + r + 1, 0, m.shape[1])
    return c[np.ix_(y1, x1)] - c[np.ix_(y0, x1)] - c[np.ix_(y1, x0)] + c[np.ix_(y0, x0)]


def cutout(a):
    """RGB 배열 → 알파(0~1) 배열"""
    H, W, _ = a.shape
    bg = np.zeros((H, W), dtype=bool)
    dq = deque()
    for x in range(W):
        for y in (0, H - 1):
            if not bg[y, x]: bg[y, x] = True; dq.append((y, x))
    for y in range(H):
        for x in (0, W - 1):
            if not bg[y, x]: bg[y, x] = True; dq.append((y, x))
    while dq:  # ① 이웃 대비 허용오차 flood fill
        y, x = dq.popleft(); c = a[y, x]
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and not bg[ny, nx]:
                d = a[ny, nx] - c
                if abs(d[0]) <= TOL and abs(d[1]) <= TOL and abs(d[2]) <= TOL:
                    bg[ny, nx] = True; dq.append((ny, nx))
    cnt = boxsum(bg, 60)  # ② 갇힌 배경 주머니
    est = np.stack([boxsum(np.where(bg, a[:, :, i], 0), 60) / np.maximum(cnt, 1) for i in range(3)], -1)
    diff = np.abs(a - est).max(-1)
    grad = np.zeros((H, W))
    for dy, dx in ((1, 0), (0, 1)):
        grad = np.maximum(grad, np.abs(a - (np.roll(a, dy, 0) if dy else np.roll(a, dx, 1))).max(-1))
    bg = bg | ((~bg) & (cnt > 200) & (diff < 13) & (grad < 7))
    al = (~bg).astype(np.float64)
    er = boxsum(al, 1) / 9.0                      # ③ 1px 침식 + 페더
    al = np.where(er < 0.999, al * er, al)
    return np.clip(boxsum(al, 1) / 9.0, 0, 1)


def split_runs(cov, thr):
    """커버리지가 thr 이하인 구간(틈) 목록 [(start,end,len)]"""
    runs, s = [], None
    for i, v in enumerate(cov):
        if v <= thr and s is None: s = i
        elif v > thr and s is not None:
            runs.append((s, i, i - s)); s = None
    if s is not None: runs.append((s, len(cov), len(cov) - s))
    return runs


def slice_cells(al):
    """알파 → 3행 × [6·6·5] 셀 bbox 목록 (키 순서대로)"""
    H, W = al.shape
    rowcov = (al > 0.15).sum(1)
    bands = [r for r in split_runs(rowcov, 0) if r[2] >= 8]
    # 띠(글씨 없는 가로 여백)로 나눠진 덩어리 = 행
    segs, prev = [], 0
    for s, e, _ in bands:
        if s > prev: segs.append((prev, s))
        prev = e
    if prev < H: segs.append((prev, H))
    segs = [s for s in segs if s[1] - s[0] >= H * 0.08]
    if len(segs) != len(LAYOUT):
        raise SystemExit(f'행 분리 실패: {len(segs)}개 (기대 {len(LAYOUT)}) — {segs}')
    out = []
    for (y0, y1), keys in zip(segs, LAYOUT):
        band = al[y0:y1]
        colcov = (band > 0.15).sum(0)
        gaps = [g for g in split_runs(colcov, 0) if g[0] > 0 and g[1] < W]
        gaps.sort(key=lambda g: -g[2])
        cuts = sorted([(g[0] + g[1]) // 2 for g in gaps[:len(keys) - 1]])
        if len(cuts) != len(keys) - 1:
            raise SystemExit(f'열 분리 실패: {len(cuts)+1}칸 (기대 {len(keys)})')
        xs = [0] + cuts + [W]
        for i, k in enumerate(keys):
            sub = al[y0:y1, xs[i]:xs[i + 1]]
            ys_, xs_ = np.where(sub > 0.06)
            out.append((k, y0 + ys_.min(), y0 + ys_.max() + 1, xs[i] + xs_.min(), xs[i] + xs_.max() + 1))
    return out


def main():
    args = [a for a in sys.argv[1:]]
    dump = None
    if args and args[0] == '--dump':
        dump = args[1]; os.makedirs(dump, exist_ok=True); args = args[2:]
    target = args[0] if args else None
    if target is None and dump is None:
        cands = sorted(glob.glob(os.path.join(HERE, '전투프로토타입_v*.html')))
        if not cands: print('대상 HTML 없음'); sys.exit(1)
        target = max(cands, key=os.path.getmtime)
    if not os.path.exists(IMG):
        print('이미지 없음:', IMG); sys.exit(1)

    a = np.asarray(Image.open(IMG).convert('RGB')).astype(np.int16)
    al = cutout(a)
    print('배경 제거 —', round((1 - al.mean()) * 100, 1), '% 투명')
    cells = slice_cells(al)
    rgba = np.dstack([a.astype(np.uint8), (al * 255).astype(np.uint8)])
    entries, total = [], 0
    for k, y0, y1, x0, x1 in cells:
        im = Image.fromarray(rgba[y0:y1, x0:x1], 'RGBA')
        w, h = im.size
        sc = min(1.0, MAXSIDE / max(w, h))
        if sc < 1.0:
            im = im.resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, 'WEBP', quality=QUALITY, method=6)
        raw = buf.getvalue(); total += len(raw)
        print(f'  {k:11s} {w}x{h} → {im.size[0]}x{im.size[1]}  {len(raw)//1024}KB')
        if dump: im.save(os.path.join(dump, k + '.webp'))
        entries.append((k, 'data:image/webp;base64,' + base64.b64encode(raw).decode()))
    print('합계', total // 1024, 'KB (base64', total * 4 // 3 // 1024, 'KB)')
    if dump and not target:
        print('덤프만 수행:', dump); return

    js = 'const CON_IMG={' + ','.join(f"{k}:'{u}'" for k, u in entries) + '};/*CON_IMG_DATA*/'  # 한 줄 유지(재주입 정규식)
    html = open(target, encoding='utf-8').read()
    pat = re.compile(r"const CON_IMG=\{[^\n]*\};/\*CON_IMG_DATA\*/", re.S)
    if not pat.search(html):
        print('플레이스홀더(/*CON_IMG_DATA*/)를 찾지 못함:', target); sys.exit(1)
    html = pat.sub(lambda m: js, html, count=1)
    open(target, 'w', encoding='utf-8').write(html)
    print('임베드 완료 →', os.path.basename(target))


if __name__ == '__main__':
    main()
