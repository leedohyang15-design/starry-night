# -*- coding: utf-8 -*-
"""이벤트 삽화를 프로토타입에 임베드한다 (v0.13).

사용법:  python embed_event_art.py [빌드html]
- ../이벤트그림/<이벤트id>.png (또는 .jpg/.webp)를 찾아 EVENT_ART로 주입한다.
- 이벤트 id: supernova · blackhole · meteorshow · binarydance · darknebula ·
             observatory · timedilation · wish
- 권장 크기 = 가로형 2:1 (예: 1200×600). 자동으로 720px 폭 WebP q84로 줄인다.
- /*EVART-START*/~/*EVART-END*/ 블록을 통째로 교체(멱등).
"""
import base64, io, json, os, re, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), '이벤트그림')
IDS = ['supernova', 'blackhole', 'meteorshow', 'binarydance', 'darknebula',
       'observatory', 'timedilation', 'wish']

def main(path):
    art = {}
    for eid in IDS:
        for ext in ('png', 'jpg', 'jpeg', 'webp'):
            p = os.path.join(SRC, f'{eid}.{ext}')
            if not os.path.exists(p): continue
            im = Image.open(p).convert('RGB')
            if im.width > 720:
                im = im.resize((720, round(im.height * 720 / im.width)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, 'WEBP', quality=84, method=6)
            art[eid] = 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()
            print(f'  {eid}: {im.size} {buf.tell()//1024}KB')
            break
    if not art:
        print('이벤트그림/ 폴더에 그림이 없습니다 — id 이름으로 넣어 주세요:', ', '.join(IDS))
        return
    src = open(path, encoding='utf-8').read()
    block = ('/*EVART-START*/\nconst EVENT_ART=' +
             json.dumps(art, separators=(',', ':')) + ';\n/*EVART-END*/')
    out, n = re.subn(r'/\*EVART-START\*/.*?/\*EVART-END\*/', lambda m: block, src, flags=re.S)
    assert n == 1, 'EVART 마커를 찾지 못했다'
    open(path, 'w', encoding='utf-8').write(out)
    print(f'주입 완료 → {path}')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'starry-night-proto-v0.13.html'))
