# -*- coding: utf-8 -*-
"""gen_fx_lines.py — 별자리 표시 기하를 **하나로 통일해** 빌드에 주입한다 (v0.23)

사용자 지적: "전투 중 성좌판에 뜨는 별자리와 성좌 발동 연출의 별자리가 다르다."
원인은 둘이 서로 다른 데이터를 그리고 있었기 때문. 이제 **모든 화면이 `const_lines.json` 하나**를 본다.

  const_lines.json (100×100, 카드 si의 기준)
        │
        ├── CONST_LINES  … 카드 앞면의 작은 별자리 그림 (그대로 주입)
        └── CONST_FX     … 성좌판·완성 연출용 320×300 배치 + 삽화 상자
                           (별 인덱스가 CONST_LINES와 **완전히 동일**하다)

배치 규칙은 사용자 레퍼런스 `Constellation Effect.dc.html`을 따른다 — 320×300 상자에 여백 34,
삽화 상자 = 별 경계 상자의 긴 변 × adj.s × 0.75, 중심 정렬 후 화면 안으로 클램프.
투영 자체(별자리 중심 입체 투영)는 `gen_const_lines.py`가 담당한다.

사용:  python gen_fx_lines.py <빌드html>
"""
import io, json, math, os, re, sys

try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, PAD, FIG_SCALE = 320, 300, 34, 0.75

# 삽화(각인 그림) 상자 배율 — 레퍼런스 파일의 adj 값. 없는 별자리는 기본값
ADJ = {'canis': (1.5, 0, -10), 'orion': (1.45, 0, 0), 'gemini': (1.35, 0, 0), 'taurus': (1.5, 0, 0),
       'scorpius': (1.3, 0, 0), 'leo': (1.45, 0, 0), 'virgo': (1.4, 0, 0), 'bootes': (1.4, 0, 0),
       'lyra': (1.6, 0, 0), 'cygnus': (1.3, 0, 0), 'aquila': (1.4, 0, 0), 'pegasus': (1.35, 0, 0),
       'ursa': (1.3, 0, 0), 'ursaminor': (1.5, 0, 0), 'cassiopeia': (1.7, 0, 0),
       'andromeda': (1.35, 0, 0), 'piscis': (1.35, 0, 0),
       # 각인 그림이 없어 SVG 폴백을 쓰는 9종 — 상자를 조금 작게
       'sagittarius': (1.25, 0, 0), 'corona': (1.5, 0, 0), 'corvus': (1.45, 0, 0), 'cancer': (1.4, 0, 0),
       'auriga': (1.3, 0, 0), 'perseus': (1.3, 0, 0), 'cepheus': (1.4, 0, 0), 'draco': (1.15, 0, 0),
       'cetus': (1.25, 0, 0)}
ALIAS = {'uma': 'ursa', 'umi': 'ursaminor', 'canismajor': 'canis', 'piscisaustrinus': 'piscis'}


def build(entry, adj):
    st = entry['stars']
    xs = [p[0] for p in st]; ys = [p[1] for p in st]
    minX, maxX, minY, maxY = min(xs), max(xs), min(ys), max(ys)
    s = min((W - PAD*2) / max(maxX-minX, 1e-6), (H - PAD*2) / max(maxY-minY, 1e-6))
    ox = (W - (maxX-minX)*s)/2 - minX*s
    oy = (H - (maxY-minY)*s)/2 - minY*s
    P = [(p[0]*s + ox, p[1]*s + oy) for p in st]
    px = [p[0] for p in P]; py = [p[1] for p in P]
    bx0, bx1, by0, by1 = min(px), max(px), min(py), max(py)
    box = min(max(bx1-bx0, by1-by0) * (adj[0] * FIG_SCALE), min(W, H) - 6)
    clamp = lambda v, lo, hi: max(lo, min(hi, v))
    cx = (bx0+bx1)/2 + adj[1]; cy = (by0+by1)/2 + adj[2]
    fx = clamp(cx - box/2, 3, W - box - 3); fy = clamp(cy - box/2, 3, H - box - 3)
    S = [[round(P[i][0], 1), round(P[i][1], 1),
          round(max(1.2, min(4.8, st[i][2] * 1.5)), 2)] for i in range(len(st))]
    L = []
    for a, b in entry['lines']:
        ax, ay = P[a]; bx, by = P[b]
        L.append([round(ax, 1), round(ay, 1), round(bx, 1), round(by, 1),
                  round(math.hypot(bx-ax, by-ay), 1)])
    return {'s': S, 'l': L, 'f': [round(fx, 1), round(fy, 1), round(box, 1), round(box, 1)]}


def replace_object(src, name, js_body):
    """const NAME={...}; 를 통째로 교체 (중괄호 짝 맞춰서)"""
    key = 'const ' + name + '={'
    i = src.index(key)
    p = i + len(key) - 1
    d = 0; q = None; esc = False
    for j in range(p, len(src)):
        c = src[j]
        if esc: esc = False; continue
        if q:
            if c == '\\': esc = True
            elif c == q: q = None
            continue
        if c in "'\"`": q = c; continue
        if c == '{': d += 1
        elif c == '}':
            d -= 1
            if d == 0:
                end = j + 1
                while end < len(src) and src[end] in ' ;':
                    end += 1
                return src[:i] + 'const ' + name + '=' + js_body + ';' + src[end:]
    raise SystemExit(name + ' 닫는 괄호를 찾지 못함')


def main():
    if len(sys.argv) < 2:
        print('사용법: python gen_fx_lines.py <빌드html>'); return
    target = sys.argv[1]
    cl = json.load(open(os.path.join(HERE, 'const_lines.json'), encoding='utf-8'))
    lines_js, fx = {}, {}
    for k, v in cl.items():
        key = ALIAS.get(k, k)
        lines_js[key] = {'stars': v['stars'], 'lines': v['lines'], 'names': v.get('names', [])}
        fx[key] = build(v, ADJ.get(key, (1.35, 0, 0)))
    src = io.open(target, encoding='utf-8').read()
    src = replace_object(src, 'CONST_LINES', json.dumps(lines_js, ensure_ascii=False, separators=(',', ':')))
    js = json.dumps(fx, separators=(',', ':')) + ';/*CONST_FX_DATA*/'
    src, n = re.subn(r'const CONST_FX=.*?;/\*CONST_FX_DATA\*/', lambda m: 'const CONST_FX=' + js, src, count=1, flags=re.S)
    if not n:
        print('주입 자리(/*CONST_FX_DATA*/)를 찾지 못했다.'); return
    io.open(target, 'w', encoding='utf-8').write(src)
    print('CONST_LINES %d개 · CONST_FX %d개 주입 (별 인덱스 공유)' % (len(lines_js), len(fx)))


if __name__ == '__main__':
    main()
