# -*- coding: utf-8 -*-
"""
embed_assets.py — 실사 에셋(조력자 초상 · 계절 배경)을 누끼/분할해 빌드 HTML에 base64로 임베드.

사용:
  python embed_assets.py [대상html]        # 기본: 가장 최신 전투프로토타입_v*.html
  python embed_assets.py --dump out/       # HTML 주입 없이 잘린 이미지만 저장(검수용)

입력
  조력자.png  1536×1024 · 2행(4인/3인). v0.22부터 배경이 **갈색 그라디언트**(구 흰 배경·한글 라벨 폐지)
              → 테두리 flood fill(이웃 대비 tol)로 배경 제거 → **전경 연결 성분 7개를 직접 검출**해 각자 크롭 → WebP(알파)
  배경.png    1661×947 · 2×2 · 흰 구분선 · 각 칸 금테
              → 구분선/금테 안쪽 크롭 → 가로 960 리사이즈 → WebP

플레이스홀더(대상 HTML)
  const PORTRAIT_IMG={};/*PORTRAIT_IMG*/
  const SEASON_BG={};/*SEASON_BG*/
"""
import base64, io, os, re, sys, glob
from collections import deque
import numpy as np
from PIL import Image

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PORTRAIT_SRC = os.path.join(HERE, '조력자.png')
BG_SRC = os.path.join(HERE, '배경.png')

# 그림의 라벨 순서 (1행 4인 / 2행 3인)
PORTRAIT_KEYS = [['galileo', 'brahe', 'herschel', 'kepler'],
                 ['copernicus', 'hubble', 'leavitt']]
BG_KEYS = [['봄', '여름'], ['가을', '겨울']]

PORT_MAX = 340      # 초상 긴 변
PORT_TOL = 10       # 배경 flood fill 허용오차 (이웃 대비) — 그라디언트 배경을 따라간다
PORT_Q = 84
BG_W = 960          # 배경 가로
BG_Q = 78


def boxsum(m, r):
    p = np.pad(m.astype(np.float64), ((1, 0), (1, 0)))
    c = p.cumsum(0).cumsum(1)
    ys = np.arange(m.shape[0]); xs = np.arange(m.shape[1])
    y0 = np.clip(ys - r, 0, m.shape[0]); y1 = np.clip(ys + r + 1, 0, m.shape[0])
    x0 = np.clip(xs - r, 0, m.shape[1]); x1 = np.clip(xs + r + 1, 0, m.shape[1])
    return c[np.ix_(y1, x1)] - c[np.ix_(y0, x1)] - c[np.ix_(y1, x0)] + c[np.ix_(y0, x0)]


def flood_bg(a, tol=10):
    """테두리에서 번지는 flood fill → 배경 불리언 (embed_conart.py와 같은 방식)"""
    H, W, _ = a.shape
    bg = np.zeros((H, W), dtype=bool)
    dq = deque()
    for x in range(W):
        for y in (0, H - 1):
            if not bg[y, x]: bg[y, x] = True; dq.append((y, x))
    for y in range(H):
        for x in (0, W - 1):
            if not bg[y, x]: bg[y, x] = True; dq.append((y, x))
    while dq:
        y, x = dq.popleft(); c = a[y, x]
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and not bg[ny, nx]:
                d = a[ny, nx] - c
                if abs(d[0]) <= tol and abs(d[1]) <= tol and abs(d[2]) <= tol:
                    bg[ny, nx] = True; dq.append((ny, nx))
    return bg


def largest_component(mask):
    """True 영역 중 가장 큰 4-연결 성분만 남긴다 (라벨 글자·부스러기 제거)"""
    H, W = mask.shape
    seen = np.zeros((H, W), dtype=bool)
    best, best_n = None, 0
    ys, xs = np.where(mask)
    for sy, sx in zip(ys, xs):
        if seen[sy, sx]:
            continue
        comp = []
        dq = deque([(sy, sx)]); seen[sy, sx] = True
        while dq:
            y, x = dq.popleft(); comp.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; dq.append((ny, nx))
        if len(comp) > best_n:
            best_n, best = len(comp), comp
    out = np.zeros((H, W), dtype=bool)
    if best:
        idx = np.array(best)
        out[idx[:, 0], idx[:, 1]] = True
    return out


def split_runs(cov, thr=0):
    runs, s = [], None
    for i, v in enumerate(cov):
        if v <= thr and s is None: s = i
        elif v > thr and s is not None: runs.append((s, i, i - s)); s = None
    if s is not None: runs.append((s, len(cov), len(cov) - s))
    return runs


# ═════════════════ 조력자 초상 ═════════════════
def components(mask, min_area):
    """True 영역의 4-연결 성분을 모두 찾아 (넓이, 마스크인덱스) 목록으로"""
    H, W = mask.shape
    lab = np.zeros((H, W), dtype=np.int32)
    out = []
    ys, xs = np.where(mask)
    cur = 0
    for sy, sx in zip(ys, xs):
        if lab[sy, sx]:
            continue
        cur += 1
        comp = []
        dq = deque([(sy, sx)]); lab[sy, sx] = cur
        while dq:
            y, x = dq.popleft(); comp.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = cur; dq.append((ny, nx))
        if len(comp) >= min_area:
            out.append((len(comp), np.array(comp)))
    out.sort(key=lambda t: -t[0])
    return out


def build_portraits(dump=None):
    """v0.22: 배경이 흰색에서 **갈색 그라디언트**로 바뀌어 행/열 분리 방식을 폐기.
    전경 연결 성분 7개를 직접 찾아 각자의 경계 상자로 자른다 (배치에 의존하지 않는다)."""
    a = np.asarray(Image.open(PORTRAIT_SRC).convert('RGB')).astype(np.int16)
    H, W, _ = a.shape
    bg = flood_bg(a, tol=PORT_TOL)
    fg = ~bg
    keys = [k for row in PORTRAIT_KEYS for k in row]
    comps = components(fg, min_area=int(H * W * 0.004))
    if len(comps) < len(keys):
        raise SystemExit(f'초상 덩어리 {len(comps)}개만 검출 (기대 {len(keys)}) — tol 조정 필요')
    comps = comps[:len(keys)]
    # 행/열 정렬: y 중심으로 행을 나누고 각 행에서 x 순
    infos = []
    for n, idx in comps:
        cy = idx[:, 0].mean(); cx = idx[:, 1].mean()
        infos.append(dict(n=n, idx=idx, cy=cy, cx=cx))
    infos.sort(key=lambda d: d['cy'])
    ordered, at = [], 0
    for row in PORTRAIT_KEYS:
        chunk = sorted(infos[at:at + len(row)], key=lambda d: d['cx'])
        at += len(row)
        ordered.extend(zip(row, chunk))
    out = []
    for k, info in ordered:
        idx = info['idx']
        m = np.zeros((H, W), dtype=bool)
        m[idx[:, 0], idx[:, 1]] = True
        cy0, cy1 = idx[:, 0].min(), idx[:, 0].max() + 1
        cx0, cx1 = idx[:, 1].min(), idx[:, 1].max() + 1
        sub = m[cy0:cy1, cx0:cx1]
        alpha = sub.astype(np.float64)
        er = boxsum(alpha, 1) / 9.0                      # 1px 침식 + 페더
        alpha = np.where(er < 0.999, alpha * er, alpha)
        alpha = np.clip(boxsum(alpha, 1) / 9.0, 0, 1)
        rgb = a[cy0:cy1, cx0:cx1].astype(np.uint8)
        rgba = np.dstack([rgb, (alpha * 255).astype(np.uint8)])
        im = Image.fromarray(rgba, 'RGBA')
        w, h = im.size
        sc = min(1.0, PORT_MAX / max(w, h))
        if sc < 1.0:
            im = im.resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.LANCZOS)
        buf = io.BytesIO(); im.save(buf, 'WEBP', quality=PORT_Q, method=6)
        raw = buf.getvalue()
        print(f'  초상 {k:11s} {w}x{h} → {im.size[0]}x{im.size[1]}  {len(raw)//1024}KB')
        if dump: im.save(os.path.join(dump, 'p_' + k + '.webp'))
        out.append((k, 'data:image/webp;base64,' + base64.b64encode(raw).decode()))
    return out


# ═════════════════ 계절 배경 ═════════════════
def build_backgrounds(dump=None):
    im0 = Image.open(BG_SRC).convert('RGB')
    a = np.asarray(im0).astype(np.int16)
    H, W, _ = a.shape
    lum = a.mean(-1)
    # 흰 구분선 = 밝기가 240 이상인 행/열
    def divider(profile, center):
        cand = [i for i in range(center - 12, center + 13) if profile[i] > 230]
        return (min(cand), max(cand) + 1) if cand else (center, center)
    vx0, vx1 = divider(lum.mean(0), W // 2)
    hy0, hy1 = divider(lum.mean(1), H // 2)
    cells = [[(0, hy0, 0, vx0), (0, hy0, vx1, W)],
             [(hy1, H, 0, vx0), (hy1, H, vx1, W)]]
    out = []
    for r, row in enumerate(BG_KEYS):
        for c, key in enumerate(row):
            y0, y1, x0, x1 = cells[r][c]
            # 금테 안쪽으로 살짝 더 크롭 (칸 폭의 2%)
            pad = max(6, int((x1 - x0) * 0.022))
            im = im0.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))
            w, h = im.size
            if w > BG_W:
                im = im.resize((BG_W, round(h * BG_W / w)), Image.LANCZOS)
            buf = io.BytesIO(); im.save(buf, 'WEBP', quality=BG_Q, method=6)
            raw = buf.getvalue()
            print(f'  배경 {key:3s} {w}x{h} → {im.size[0]}x{im.size[1]}  {len(raw)//1024}KB')
            if dump: im.save(os.path.join(dump, 'bg_' + key + '.webp'))
            out.append((key, 'data:image/webp;base64,' + base64.b64encode(raw).decode()))
    return out


def inject(target, name, entries):
    html = open(target, encoding='utf-8').read()
    js = f'const {name}={{' + ','.join(f"'{k}':'{u}'" for k, u in entries) + f'}};/*{name}*/'
    pat = re.compile(r'const ' + name + r'=\{[^\n]*\};/\*' + name + r'\*/')
    if not pat.search(html):
        print(f'플레이스홀더(/*{name}*/)를 찾지 못함:', os.path.basename(target)); sys.exit(1)
    html = pat.sub(lambda m: js, html, count=1)
    open(target, 'w', encoding='utf-8').write(html)
    print(f'{name} 주입 완료 — {len(js)//1024}KB')


def main():
    args = sys.argv[1:]
    dump = None
    if args and args[0] == '--dump':
        dump = args[1]; os.makedirs(dump, exist_ok=True); args = args[2:]
    target = args[0] if args else None
    if target is None and dump is None:
        cands = sorted(glob.glob(os.path.join(HERE, '전투프로토타입_v*.html')))
        target = max(cands, key=os.path.getmtime) if cands else None
    print('조력자 초상 —')
    ports = build_portraits(dump)
    print('계절 배경 —')
    bgs = build_backgrounds(dump)
    if not target:
        print('덤프만 수행:', dump); return
    inject(target, 'PORTRAIT_IMG', ports)
    inject(target, 'SEASON_BG', bgs)
    print('대상:', os.path.basename(target), os.path.getsize(target) // 1024, 'KB')


if __name__ == '__main__':
    main()
