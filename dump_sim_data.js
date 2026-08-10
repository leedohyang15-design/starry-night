// dump_sim_data.js — 빌드 HTML에서 밸런스 시뮬레이터용 데이터 객체를 추출해 JSON으로 저장
// 사용: node dump_sim_data.js [빌드html] [출력json]
// 빌드의 데이터 주도 원칙 덕에 수치가 전부 상단 객체 리터럴에 있어 그대로 떠낼 수 있다.
const fs = require('fs');

const file = process.argv[2] || '전투프로토타입_v0.21.html';
const out = process.argv[3] || 'sim_data_v021.json';
const html = fs.readFileSync(file, 'utf8');

const NAMES = ['STARS', 'CONSTELLATIONS', 'ENEMIES', 'ENC_EASY', 'ENC_NORMAL', 'ENC_HARD',
  'ENC2_EASY', 'ENC2_NORMAL', 'ENC2_HARD', 'ENC3_EASY', 'ENC3_NORMAL', 'ENC3_HARD',
  'ELITES', 'ELITES2', 'ELITES3', 'POLAR_DECK',
  'ITEMS', 'RELICS', 'COMPANIONS', 'UP_COST_ONLY', 'UP_NUM', 'SEASONS', 'OPP'];

function grab(name) {
  const key = 'const ' + name + '=';
  const i = html.indexOf(key);
  if (i < 0) throw new Error('찾지 못함: ' + name);
  let p = i + key.length;
  const open = html[p];
  if (open !== '{' && open !== '[') throw new Error(name + ' 은 객체/배열 리터럴이 아님');
  const close = open === '{' ? '}' : ']';
  let depth = 0, q = null, esc = false;
  for (let j = p; j < html.length; j++) {
    const c = html[j];
    if (esc) { esc = false; continue; }
    if (q) { if (c === '\\') esc = true; else if (c === q) q = null; continue; }
    if (c === "'" || c === '"' || c === '`') { q = c; continue; }
    if (c === open) depth++;
    else if (c === close) { depth--; if (depth === 0) return eval('(' + html.slice(p, j + 1) + ')'); }
  }
  throw new Error(name + ' 닫는 괄호를 찾지 못함');
}

const data = {};
for (const n of NAMES) data[n] = grab(n);
fs.writeFileSync(out, JSON.stringify(data, null, 1), 'utf8');
console.log('덤프 완료 →', out,
  '| 별', Object.keys(data.STARS).length,
  '· 별자리', Object.keys(data.CONSTELLATIONS).length,
  '· 적', Object.keys(data.ENEMIES).length);
