#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_font.py — v0.39 픽셀 폰트(갈무리 Galmuri11, OFL) 내장.
빌드 HTML에 실제로 등장하는 글자만 서브셋해 WOFF2 base64로 @font-face 주입 — 오프라인 단일 파일 유지.
※ 새 한글 문구를 추가한 뒤에는 반드시 재실행할 것 (서브셋에 없는 글자는 시스템 폰트로 빠진다).
사용: python embed_font.py <빌드html>
"""
import base64, io, re, subprocess, sys, tempfile, os

FONTS = [('Galmuri11', '폰트/Galmuri11.woff2', 'normal'),
         ('Galmuri11', '폰트/Galmuri11-Bold.woff2', 'bold')]
MARK = '/*PIXEL_FONT*/'

def used_chars(html):
    s = open(html, encoding='utf-8').read()
    # base64 데이터 URI는 제외하고 셈 (ASCII만이라 영향 없지만 크기 절약 목적 아님 — 그대로 둬도 무방)
    chars = set(s)
    chars |= set('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
    chars |= set('×÷±−↑↓←→↔↕≥≤≠≈™°·※∙…‥「」『』【】〈〉《》○●◎◇◆□■△▲▽▼☆★♪♩♭♯✦✧✶✷✸✹✺❋⏳🛡')
    chars |= set(chr(c) for c in range(0x20, 0x7F))
    return ''.join(sorted(c for c in chars if ord(c) >= 0x20))

def subset(src, text):
    out = tempfile.mktemp(suffix='.woff2')
    subprocess.run([sys.executable, '-m', 'fontTools.subset', src,
                    '--text-file=/dev/stdin', '--flavor=woff2', f'--output-file={out}',
                    '--layout-features=*', '--no-hinting'],
                   input=text.encode(), check=True, capture_output=True)
    data = open(out, 'rb').read(); os.unlink(out)
    return base64.b64encode(data).decode()

def main(html):
    text = used_chars(html)
    faces = []
    total = 0
    for fam, path, weight in FONTS:
        b64 = subset(path, text)
        total += len(b64)
        faces.append(f"@font-face{{font-family:'{fam}';font-weight:{weight};font-display:swap;"
                     f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    block = MARK + '\n' + '\n'.join(faces) + '\n' + MARK
    s = open(html, encoding='utf-8').read()
    pat = re.compile(re.escape(MARK) + '.*?' + re.escape(MARK), re.S)
    if pat.search(s):
        s = pat.sub(lambda m: block, s, count=1)
    else:
        s = s.replace('<style>', '<style>\n' + block + '\n', 1)
    open(html, 'w', encoding='utf-8').write(s)
    print(f'폰트 주입 — 글자 {len(text)}종, base64 총 {total//1024}KB')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'starry-night-v0.39.html')
