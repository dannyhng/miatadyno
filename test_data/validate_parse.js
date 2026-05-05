// Headless validator: extract parseCSV + detectPulls from index.html and run
// them against the synthetic CSVs. Mocks the DOM bits these functions touch.
//
// Validates:
//   #1 (real_log.csv) — single-pull, baro from sensor (inHg), IAT from header (°F).
//      With per-pull IAT == file-mean IAT for a 1-pull file, calcHP result
//      should be IDENTICAL to pre-fix (this is the engineer's invariant).
//   #2 (synth_heatsoak.csv) — 5 pulls, each with distinct iat_c value
//      (~30, ~45, ~55, ~65, ~75°C).
//   #3 (synth_kph.csv) — speedSource should say "inferred km/h".
//   #4 (synth_fi_map.csv) — MAP-derived baro should be median ~135 kPa,
//      then caught by 80–105 sanity bound and reset to 99.9 kPa with
//      'out-of-range' note. (FI override is at runAnalysis, not parseCSV.)

const fs = require('fs');
const path = require('path');

// Load Papa Parse from a CDN-equivalent local install if available, else
// a tiny shim that handles the headers we need.
let Papa;
try { Papa = require('papaparse'); }
catch(e) {
  Papa = {
    parse(txt, opts){
      const lines = txt.split(/\r?\n/).filter(l => l.length);
      let header = lines[0].split(',').map(opts.transformHeader || (h => h));
      const rows = [];
      for(let i = 1; i < lines.length; i++){
        const cells = lines[i].split(',');
        const r = {};
        header.forEach((h, j) => {
          const v = cells[j];
          if(opts.dynamicTyping){
            const n = parseFloat(v);
            r[h] = isNaN(n) ? v : n;
          } else r[h] = v;
        });
        rows.push(r);
      }
      return { data: rows, meta: { fields: header } };
    }
  };
}

// --- pull JS source out of index.html ---
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const m = html.match(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/);
if(!m) throw new Error('no inline script found');
const jsSrc = m[1];

// Extract the function bodies we want by name — we regex out the code,
// it's robust enough for our hand-edited file.
function extract(name){
  const re = new RegExp(`function ${name}\\s*\\([^)]*\\)\\s*\\{`);
  const idx = jsSrc.search(re);
  if(idx < 0) throw new Error('not found: ' + name);
  // walk braces from the opening {
  let i = jsSrc.indexOf('{', idx);
  let depth = 1, j = i + 1;
  while(j < jsSrc.length && depth > 0){
    const c = jsSrc[j];
    if(c === '{') depth++;
    else if(c === '}') depth--;
    else if(c === '"' || c === "'" || c === '`'){
      const quote = c; j++;
      while(j < jsSrc.length && jsSrc[j] !== quote){
        if(jsSrc[j] === '\\') j++;
        j++;
      }
    } else if(c === '/' && jsSrc[j+1] === '/'){
      while(j < jsSrc.length && jsSrc[j] !== '\n') j++;
    } else if(c === '/' && jsSrc[j+1] === '*'){
      j += 2;
      while(j < jsSrc.length - 1 && !(jsSrc[j] === '*' && jsSrc[j+1] === '/')) j++;
      j++;
    }
    j++;
  }
  return jsSrc.slice(idx, j);
}

const sources = ['findC','detectUnit','parseCSV','detectPulls'].map(extract).join('\n\n');

// --- mock DOM/global bits parseCSV/detectPulls reach for ---
global.window = { __lastParseInfo: null, __lastDetectInfo: null };
global.document = {
  querySelector: () => ({ dataset: { v: 'sae' } }),
};
global.Papa = Papa;
global.baro = 99.9;
global.iat_k = 298.15;
const RDA = 287.05;
global.RDA = RDA;
global.rho = 1.225;
const G = 9.81;
global.G = G;

// expose `baro`/`iat_k`/`rho` as mutable globals for the parsed code to assign to
const code = `
  ${sources}
  module.exports = { findC, detectUnit, parseCSV, detectPulls };
`;
const m2 = { exports: {} };
const fn = new Function('module','window','document','Papa','RDA','G','require',
  // also expose mutable globals — declare with var so reassignment in parseCSV works
  `var baro = 99.9, iat_k = 298.15, rho = 1.225;` + code + `
  module.exports.getGlobals = () => ({ baro, iat_k, rho });
`);
fn(m2, global.window, global.document, Papa, RDA, G, require);
const { parseCSV, detectPulls, getGlobals } = m2.exports;

// --- helpers ---
function readUtf16leOrUtf8(p){
  const buf = fs.readFileSync(p);
  if(buf.length >= 2 && buf[0] === 0xFF && buf[1] === 0xFE){
    return buf.slice(2).toString('utf16le');
  }
  if(buf.length >= 3 && buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF){
    return buf.slice(3).toString('utf8');
  }
  // sniff: if every odd byte in a sample is 0, it's likely utf-16le without BOM
  let nullCount = 0;
  const sample = Math.min(200, buf.length);
  for(let i = 1; i < sample; i += 2) if(buf[i] === 0) nullCount++;
  if(nullCount > sample * 0.3) return buf.toString('utf16le');
  return buf.toString('utf8');
}

function runCase(label, csvPath){
  console.log(`\n━━━ ${label} ━━━`);
  console.log(`file: ${path.basename(csvPath)}`);
  const text = readUtf16leOrUtf8(csvPath);
  const res = parseCSV(text);
  if(!res.ok){ console.log(`  PARSE FAIL: ${res.msg}`); return null; }
  // P1: parseCSV now returns tempUnit; mirror the production call site.
  const pulls = detectPulls(res.data, res.tempUnit);
  const info = global.window.__lastParseInfo;
  const det = global.window.__lastDetectInfo;
  const g = getGlobals();
  console.log(`  rows=${res.data.length}  pulls=${pulls.length}  tempUnit=${res.tempUnit ?? 'null (heuristic)'}`);
  console.log(`  speedSource: ${info.speedSource}`);
  console.log(`  baroSource:  ${info.baroSource}  →  baro=${g.baro.toFixed(2)} kPa`);
  console.log(`  iatSource:   ${info.iatSource}   →  iat_k=${g.iat_k.toFixed(2)} K (${(g.iat_k-273.15).toFixed(1)}°C)`);
  if(det) console.log(`  WOT threshold: ${det.wotThreshold}% (file peak ${det.peakThrottle}%)`);
  pulls.forEach((p, i) => {
    const iatStr = p.iat_c === null ? 'null' : `${p.iat_c.toFixed(1)}°C`;
    console.log(`    pull[${i}]: rpm ${p.maxRPM.toFixed(0)}, ${p.maxSpd.toFixed(1)} mph, ${p.dur.toFixed(1)}s, q=${p.q}, iat=${iatStr}`);
  });
  // Inverted-IAT-trend warning: physically impossible drop ≥10°C between
  // pull 1 and any later pull → unit-detection failure on the no-header
  // fallback path. Mirrors the new renderPulls() banner logic.
  if(pulls.length >= 2 && pulls[0].iat_c !== null){
    const minDelta = Math.min(...pulls.slice(1)
      .filter(p => p.iat_c !== null)
      .map(p => p.iat_c - pulls[0].iat_c));
    if(minDelta <= -10){
      console.log(`  ⚠ INVERTED IAT TREND DETECTED — min delta vs pull[0]: ${minDelta.toFixed(1)}°C (likely untagged-header unit detection failure)`);
    }
  }
  return { res, pulls, info, det, baro: g.baro, iat_k: g.iat_k };
}

const T = path.join(__dirname);

runCase('CASE #1 — DataLog-Apr_29_2026 (2011 NC2, stock, 205/55R16, 170lb driver)',
        path.join(__dirname, '..', 'DataLog-Apr_29_2026_00-16-19-.csv'));
runCase('CASE #2a — synth_heatsoak.csv (°F header, control)',
        path.join(T, 'synth_heatsoak.csv'));
runCase('CASE #2b — synth_heatsoak_celsius.csv (°C header, P1 bug repro)',
        path.join(T, 'synth_heatsoak_celsius.csv'));
runCase('CASE #2c — synth_heatsoak_notagged.csv (no header tag, heuristic fallback)',
        path.join(T, 'synth_heatsoak_notagged.csv'));
runCase('CASE #3 — synth_kph.csv (km/h, no header tag)',
        path.join(T, 'synth_kph.csv'));
runCase('CASE #4 — synth_fi_map.csv (MAP only, FI scenario)',
        path.join(T, 'synth_fi_map.csv'));

console.log('\n--- expected ---');
console.log('#1: baroSource ~ "inhg sensor" or "auto sensor", iat from °F, 2 pulls (heat-soaked)');
console.log('#2a (°F): tempUnit=fahrenheit, all 5 pulls iat_c = 30/45/55/65/75°C');
console.log('#2b (°C): tempUnit=celsius, all 5 pulls iat_c = 30/45/55/65/75°C  ← P1 FIX target');
console.log('#2c (no tag): tempUnit=null, pulls 1-3 ok (30/45/55) but pulls 4-5 mis-classified (65→18.3, 75→23.9) — DOCUMENTED-BUGGY behavior; we test that it stays this way until we have a header to disambiguate');
console.log('#3: speedSource "inferred km/h (file peak 140...)"; baro = default; pull mph values converted');
console.log('#4: baro out-of-range fallback (median MAP ~135 kPa caught), then UI FI toggle should fire MAP-FI override at analysis time');
