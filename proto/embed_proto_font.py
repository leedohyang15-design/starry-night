# -*- coding: utf-8 -*-
"""Galmuri11(OFL) 픽셀 폰트를 빌드에 등장하는 글자만 서브셋해 base64로 임베드한다.

사용법:  python embed_proto_font.py [빌드html]   (기본: starry-night-proto-v0.5.html)
요구:    pip install fonttools brotli  ·  Galmuri11.woff2 (같은 폴더, 없으면 GitHub에서 받는다)

한글 문구를 추가·수정한 버전을 낼 때마다 재실행할 것 — 서브셋에 없는 글자는
시스템 폰트로 빠져 픽셀풍이 깨진다. /*FONT-START*/~/*FONT-END*/ 블록을 교체(멱등).
"""
import base64, io, os, re, subprocess, sys, urllib.request

FONT_URL = 'https://raw.githubusercontent.com/quiple/galmuri/main/dist/Galmuri11.woff2'

def main(path):
    here = os.path.dirname(os.path.abspath(__file__))
    src_font = os.path.join(here, 'Galmuri11.woff2')
    if not os.path.exists(src_font):
        print('폰트 내려받는 중…')
        urllib.request.urlretrieve(FONT_URL, src_font)
    html = open(path, encoding='utf-8').read()
    body = re.sub(r'/\*FONT-START\*/.*?/\*FONT-END\*/', '', html, flags=re.S)
    chars = ''.join(sorted(set(body))) + '0123456789+×∞·—♥♨⚔⚒★✧✦?🌙'
    from fontTools.subset import Subsetter, load_font, save_font, Options
    opt = Options(flavor='woff2', hinting=False, desubroutinize=True)
    font = load_font(src_font, opt)
    sub = Subsetter(opt)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    save_font(font, buf, opt)
    b64 = base64.b64encode(buf.getvalue()).decode()
    block = ('/*FONT-START*/\n'
             "@font-face{font-family:'Galmuri11';src:url(data:font/woff2;base64," + b64 + ") format('woff2')}\n"
             "body{font-family:'Galmuri11',system-ui,'Apple SD Gothic Neo','Malgun Gothic',sans-serif}\n"
             '/*FONT-END*/\n')
    if '/*FONT-START*/' in html:
        html = re.sub(r'/\*FONT-START\*/.*?/\*FONT-END\*/\n?', lambda m: block, html, flags=re.S)
    else:
        html = html.replace('<style>', '<style>\n' + block, 1)
    open(path, 'w', encoding='utf-8').write(html)
    print(f'폰트 임베드 완료 — 서브셋 {len(chars)}자, base64 {len(b64)//1024}KB → {path}')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'starry-night-proto-v0.5.html'))
