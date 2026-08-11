# -*- coding: utf-8 -*-
"""
embed_assets.py — 실사 에셋(조력자 초상 · 계절 배경)을 누끼/분할해 빌드 HTML에 base64로 임베드.

사용:
  python embed_assets.py [대상html]        # 기본: 가장 최신 전투프로토타입_v*.html
  python embed_assets.py --dump out/       # HTML 주입 없이 잘린 이미지만 저장(검수용)

입력
  조력자(입다뭄, 기본).png  기본 프레임(입 다뭄). 없으면 구 조력자.png를 대신 쓴다
  조력자2(입엶).png         입 연 프레임(v0.31 입 벙긋용, 선택) — 배치는 기본 시트와 같아야 한다
              두 시트 모두: 테두리 flood fill(이웃 대비 tol)로 배경 제거 → **전경 연결 성분 7개를 직접 검출**해 각자 크롭 → WebP(알파)
  배경.png    1661×947 · 2×2 · 흰 구분선 · 각 칸 금테
              → 구분선/금테 안쪽 크롭 → 가로 960 리사이즈 → WebP

플레이스홀더(대상 HTML)
  const PORTRAIT_IMG={};/*PORTRAIT_IMG*/
  const PORTRAIT_OPEN={};/*PORTRAIT_OPEN*/   (v0.31 — 입 연 시트가 있을 때만 주입)
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
def _find(*names):
    for nm in names:
        for ext in ('.png', '.webp', '.jpg', '.jpeg'):
            c = os.path.join(HERE, nm + ext)
            if os.path.exists(c):
                return c
        hits = glob.glob(os.path.join(HERE, nm + '*'))
        if hits:
            return hits[0]
    return None

PORTRAIT_SRC = _find('조력자(입다뭄, 기본)', '조력자(입다뭄,기본)') or os.path.join(HERE, '조력자.png')
PORTRAIT_OPEN_SRC = _find('조력자2(입엶)', '조력자2')                      # 선택 — 없으면 입 벙긋 비활성
BG_SRC = os.path.join(HERE, '배경.png')

# 그림의 라벨 순서 (1행 4인 / 2행 3인)
PORTRAIT_KEYS = [['galileo', 'brahe', 'herschel', 'kepler'],
                 ['copernicus', 'hubble', 'leavitt']]
BG_KEYS = [['봄', '여름'], ['가을', '겨울']]

PORT_MAX = 340      # 초상 긴 변
PORT_TOL = 3        # 배경 flood fill 허용오차 (이웃 대비). v0.32: 10 → 3 — 검정 배경 픽셀 시트에서 10이면 어두운 머리칼·외투까지 배경으로 먹는다 (tol 3 = 기본 시트가 정확히 7덩어리)
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


def _detect(a, min_frac):
    """flood fill 배경 제거 → 전경 연결 성분 목록"""
    bg = flood_bg(a, tol=PORT_TOL)
    return components(~bg, min_area=int(a.shape[0] * a.shape[1] * min_frac))


def _order_chars(comps, H, W):
    """성분 상위 7개를 행(y)→열(x) 순으로 키에 배정, 문자별 (마스크, 중심) 반환"""
    keys = [k for row in PORTRAIT_KEYS for k in row]
    comps = comps[:len(keys)]
    infos = []
    for n, idx in comps:
        infos.append(dict(idx=idx, cy=idx[:, 0].mean(), cx=idx[:, 1].mean()))
    infos.sort(key=lambda d: d['cy'])
    ordered, at = {}, 0
    for row in PORTRAIT_KEYS:
        chunk = sorted(infos[at:at + len(row)], key=lambda d: d['cx'])
        at += len(row)
        for k, info in zip(row, chunk):
            m = np.zeros((H, W), dtype=bool)
            m[info['idx'][:, 0], info['idx'][:, 1]] = True
            ib = info['idx']
            abox = (ib[:, 0].min(), ib[:, 0].max() + 1, ib[:, 1].min(), ib[:, 1].max() + 1)
            ordered[k] = dict(mask=m, cy=info['cy'], cx=info['cx'], abox=abox)   # abox = 인물 본체(앵커)의 상자
    return ordered


def _crop_rgba(a, mask, box):
    """같은 상자(box)로 자르고 자기 마스크로 알파 — 1px 침식 + 페더 (구현은 v0.22와 동일)"""
    y0, y1, x0, x1 = box
    sub = mask[y0:y1, x0:x1]
    alpha = sub.astype(np.float64)
    er = boxsum(alpha, 1) / 9.0
    alpha = np.where(er < 0.999, alpha * er, alpha)
    alpha = np.clip(boxsum(alpha, 1) / 9.0, 0, 1)
    rgb = a[y0:y1, x0:x1].astype(np.uint8)
    return np.dstack([rgb, (alpha * 255).astype(np.uint8)])


def _to_webp(rgba, scale):
    im = Image.fromarray(rgba, 'RGBA')
    if scale < 1.0:
        w, h = im.size
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'WEBP', quality=PORT_Q, method=6)
    return im, buf.getvalue()


def build_portraits(dump=None, src=None, tag='p'):
    """단일 시트 모드 (구 방식 그대로) — 입엶 시트가 없을 때의 폴백"""
    a = np.asarray(Image.open(src or PORTRAIT_SRC).convert('RGB')).astype(np.int16)
    H, W, _ = a.shape
    chars = _order_chars(_detect(a, 0.004), H, W)
    out = []
    for k, info in chars.items():
        idx = np.argwhere(info['mask'])
        box = (idx[:, 0].min(), idx[:, 0].max() + 1, idx[:, 1].min(), idx[:, 1].max() + 1)
        rgba = _crop_rgba(a, info['mask'], box)
        sc = min(1.0, PORT_MAX / max(rgba.shape[0], rgba.shape[1]))
        im, raw = _to_webp(rgba, sc)
        print(f'  초상 {k:11s} {box[3]-box[2]}x{box[1]-box[0]} → {im.size[0]}x{im.size[1]}  {len(raw)//1024}KB')
        if dump: im.save(os.path.join(dump, tag + '_' + k + '.webp'))
        out.append((k, 'data:image/webp;base64,' + base64.b64encode(raw).decode()))
    return out


def _char_sets(a, margin=0.4):
    """시트 하나에서 인물 7명 세트: 큰 성분 7개를 앵커로 잡고, 잔조각(0.05%~)을 가장 가까운 앵커에 귀속.
    단 앵커 상자를 40% 넓힌 범위 **밖**의 조각은 버린다 — 떠도는 부스러기가 캔버스를 부풀리면
    게임의 contain 스케일로 인물이 작아진다"""
    H, W, _ = a.shape
    anchors = _order_chars(_detect(a, 0.004), H, W)
    for n, idx in _detect(a, 0.0005):
        cy, cx = idx[:, 0].mean(), idx[:, 1].mean()
        k = min(anchors, key=lambda q: (anchors[q]['cy'] - cy) ** 2 + (anchors[q]['cx'] - cx) ** 2)
        y0, y1, x0, x1 = anchors[k]['abox']
        my, mx = (y1 - y0) * margin, (x1 - x0) * margin
        if y0 - my <= cy <= y1 + my and x0 - mx <= cx <= x1 + mx:
            anchors[k]['mask'][idx[:, 0], idx[:, 1]] = True
    return anchors


def _pad_bc(im, W, H):
    """바닥 중앙 정렬로 (W,H) 캔버스에 패딩 — 게임 스프라이트 anchor(50% 100%)와 일치"""
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    out.paste(im, ((W - im.size[0]) // 2, H - im.size[1]), im)
    return out


def build_portrait_pairs(dump=None):
    """v0.31: 기본(입다뭄)·입엶 두 시트를 짝지어 뽑는다. v0.32: 두 시트의 캔버스 크기가 달라도 된다 —
    시트별로 독립 검출·귀속한 뒤, **같은 배율**(기본 프레임 기준)로 줄이고 **바닥 중앙 정렬 패딩**으로
    두 프레임의 캔버스를 일치시킨다 (입 벙긋 때 몸이 튀지 않는 조건 = 배율·anchor 동일)."""
    A = np.asarray(Image.open(PORTRAIT_SRC).convert('RGB')).astype(np.int16)
    B = np.asarray(Image.open(PORTRAIT_OPEN_SRC).convert('RGB')).astype(np.int16)
    charsA = _char_sets(A)
    charsB = _char_sets(B)
    base_out, open_out = [], []
    for k in charsA:
        ia = np.argwhere(charsA[k]['mask']); ib = np.argwhere(charsB[k]['mask'])
        boxA = (ia[:, 0].min(), ia[:, 0].max() + 1, ia[:, 1].min(), ia[:, 1].max() + 1)
        boxB = (ib[:, 0].min(), ib[:, 0].max() + 1, ib[:, 1].min(), ib[:, 1].max() + 1)
        rgbaA = _crop_rgba(A, charsA[k]['mask'], boxA)
        rgbaB = _crop_rgba(B, charsB[k]['mask'], boxB)
        # v0.32: tol 3에서는 병합 마스크가 이미 온전하다 — 기준 = 전체 마스크 상자 (앵커 조각 오인 방지)
        aA, aB = boxA, boxB
        sc = min(1.0, PORT_MAX / max(rgbaA.shape[0], rgbaA.shape[1]))          # 기본 프레임 기준 배율
        scB = sc * (aA[1] - aA[0]) / max(1, (aB[1] - aB[0]))                    # 입엶은 키를 기본에 맞춘다
        imA = Image.fromarray(rgbaA, 'RGBA'); imB = Image.fromarray(rgbaB, 'RGBA')
        imA = imA.resize((max(1, round(imA.size[0] * sc)), max(1, round(imA.size[1] * sc))), Image.LANCZOS) if sc < 1.0 else imA
        imB = imB.resize((max(1, round(imB.size[0] * scB)), max(1, round(imB.size[1] * scB))), Image.LANCZOS)
        # 정렬 기준점 = 인물 본체의 바닥 중앙 (크롭 좌표계 → 배율 적용)
        pA = (((aA[2] + aA[3]) / 2 - boxA[2]) * sc, (aA[1] - boxA[0]) * sc)
        pB = (((aB[2] + aB[3]) / 2 - boxB[2]) * scB, (aB[1] - boxB[0]) * scB)
        # 두 프레임을 같은 캔버스에: B를 (pA-pB)만큼 이동시켜 기준점 일치 → 전체 경계로 캔버스 산출
        dx, dy = pA[0] - pB[0], pA[1] - pB[1]
        x0 = min(0, dx); y0 = min(0, dy)
        Wc = int(round(max(imA.size[0], dx + imB.size[0]) - x0))
        Hc = int(round(max(imA.size[1], dy + imB.size[1]) - y0))
        cA = Image.new('RGBA', (Wc, Hc), (0, 0, 0, 0)); cA.paste(imA, (int(round(-x0)), int(round(-y0))), imA)
        cB = Image.new('RGBA', (Wc, Hc), (0, 0, 0, 0)); cB.paste(imB, (int(round(dx - x0)), int(round(dy - y0))), imB)
        bufA = io.BytesIO(); cA.save(bufA, 'WEBP', quality=PORT_Q, method=6); rawA = bufA.getvalue()
        bufB = io.BytesIO(); cB.save(bufB, 'WEBP', quality=PORT_Q, method=6); rawB = bufB.getvalue()
        print(f'  짝 {k:11s} {Wc}x{Hc}  기본 {len(rawA)//1024}KB · 입엶 {len(rawB)//1024}KB')
        if dump:
            cA.save(os.path.join(dump, 'p_' + k + '.webp'))
            cB.save(os.path.join(dump, 'po_' + k + '.webp'))
        base_out.append((k, 'data:image/webp;base64,' + base64.b64encode(rawA).decode()))
        open_out.append((k, 'data:image/webp;base64,' + base64.b64encode(rawB).decode()))
    return base_out, open_out


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
    opens = None
    if PORTRAIT_OPEN_SRC:
        print('조력자 초상 짝(기본+입엶) —', os.path.basename(PORTRAIT_SRC), '+', os.path.basename(PORTRAIT_OPEN_SRC))
        ports, opens = build_portrait_pairs(dump)
    else:
        print('조력자 초상(기본만) —', os.path.basename(PORTRAIT_SRC), '· 입엶 시트 없음 — 입 벙긋 비활성')
        ports = build_portraits(dump, PORTRAIT_SRC, 'p')
    print('계절 배경 —')
    bgs = build_backgrounds(dump)
    if not target:
        print('덤프만 수행:', dump); return
    inject(target, 'PORTRAIT_IMG', ports)
    if opens:
        inject(target, 'PORTRAIT_OPEN', opens)
    inject(target, 'SEASON_BG', bgs)
    print('대상:', os.path.basename(target), os.path.getsize(target) // 1024, 'KB')


if __name__ == '__main__':
    main()
