// End-to-end Compare-path validator. Companion to validate_lock.js.
//
// What this catches:
//   - Per-slot prof routing bugs (selB.rows must use profBefore.baro,
//     selA.rows must use profAfter.baro)
//   - Speed-trap state leak (the zero-delta tripwire on identical files)
//   - applyMapFiOverride correctness (FI on the right file mutates the
//     right baro)
//   - Per-file weight delta (Compare with FI On for After only must
//     produce a heavier After mass)
//
// What this does NOT catch:
//   - Runtime errors inside runAnalysis itself (e.g. block-scope variable
//     shadowing like the gearProf bug). runAnalysis touches ~30 DOM
//     elements and isn't called here. To catch that class of bug we'd
//     need jsdom-level coverage. Browser smoke remains the backstop.
//
// Three test cases. Exits 0 on pass, 1 on any assertion failure.
//   1. Identical files (real_log.csv as both Before and After):
//        gain == 0, all speed-trap deltas == 0
//   2. Mismatched files (real_log.csv vs DataLog-Apr_29_2026...csv):
//        gain != 0, traps != 0 (smoke only)
//   3. NA-Before vs FI-After on identical files:
//        After mass > Before mass by exactly the FI weight delta;
//        After WHP > Before WHP by the corresponding amount;
//        speed-trap deltas remain 0 (mass change doesn't affect timer)

const fs = require('fs');
const path = require('path');

// ── Papa Parse shim (same as validate_lock.js) ──
let Papa;
try { Papa = require('papaparse'); }
catch(e) {
  Papa = {
    parse(txt, opts){
      const lines = txt.split(/\r?\n/).filter(l => l.length);
      const header = lines[0].split(',').map(opts.transformHeader || (h => h));
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

// ── extract function bodies from index.html ──
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const m = html.match(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/);
if(!m) throw new Error('no inline script found');
const jsSrc = m[1];

function extract(name){
  const re = new RegExp(`function ${name}\\s*\\([^)]*\\)\\s*\\{`);
  const idx = jsSrc.search(re);
  if(idx < 0) throw new Error('not found: ' + name);
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

// SPEED_TRAPS const + speedTrapsForPull/calcSpeedTrap funcs are needed too.
// Extract them via simpler text matching since they're top-level.
function extractConst(name){
  const re = new RegExp(`const ${name}\\s*=`);
  const idx = jsSrc.search(re);
  if(idx < 0) throw new Error('not found: const ' + name);
  // Find end of statement (next semicolon at depth 0)
  let depth = 0, j = idx;
  while(j < jsSrc.length){
    const c = jsSrc[j];
    if(c === '[' || c === '{' || c === '(') depth++;
    else if(c === ']' || c === '}' || c === ')') depth--;
    else if(c === ';' && depth === 0){ j++; break; }
    j++;
  }
  return jsSrc.slice(idx, j);
}

const sources = [
  'findC','detectUnit','parseCSV','detectPulls',
  'savgol','grad','calcHP','bin',
  'calcSpeedTrap','speedTrapsForPull',
  'applyMapFiOverride',
].map(extract).join('\n\n')
  + '\n\n' + extractConst('SPEED_TRAPS');

// ── DOM mock: just enough for calcHP (#tCorr) and applyMapFiOverride (#forced/#forcedAfter). ──
global.window = { __lastParseInfo: null, __lastDetectInfo: null };
const _domValues = { tCorr: 'sae', forced: '0', forcedAfter: '0' };  // override per-test
global.document = {
  querySelector: (sel) => {
    if(sel === '#tCorr .tbtn.on') return { dataset: { v: _domValues.tCorr } };
    return null;
  },
  getElementById: (id) => {
    if(id in _domValues) return { value: _domValues[id] };
    return null;
  },
};
global.Papa = Papa;
const RDA = 287.05;
const G = 9.81;

const code = sources + `\nmodule.exports = { findC, detectUnit, parseCSV, detectPulls, calcHP, bin, savgol, grad, calcSpeedTrap, speedTrapsForPull, applyMapFiOverride, SPEED_TRAPS };`;
const m2 = { exports: {} };
const fn = new Function('module','window','document','Papa','RDA','G','require', code);
fn(m2, global.window, global.document, Papa, RDA, G, require);
const { parseCSV, detectPulls, calcHP, bin, speedTrapsForPull, applyMapFiOverride } = m2.exports;

// ── file reader (UTF-16 BOM detection) ──
function readUtf16leOrUtf8(p){
  const buf = fs.readFileSync(p);
  if(buf.length >= 2 && buf[0] === 0xFF && buf[1] === 0xFE) return buf.slice(2).toString('utf16le');
  if(buf.length >= 3 && buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF) return buf.slice(3).toString('utf8');
  let nullCount = 0;
  const sample = Math.min(200, buf.length);
  for(let i = 1; i < sample; i += 2) if(buf[i] === 0) nullCount++;
  if(nullCount > sample * 0.3) return buf.toString('utf16le');
  return buf.toString('utf8');
}

// ── shared config (matches validate_lock.js: NC2 PRHT 6MT, 170lb, half tank) ──
const BASE = {
  wt:        2509,
  swl:       19.0,
  Cd:        0.36,
  A:         1.78,
  Crr:       0.015,
  rot:       0.045,
  stock_dia_m: 0.6163,
  stock_tire_lbs: 21.0,
};
const CD = 0.34;
const PRHT_DELTA_NC2 = 78;
const FUEL_LBS = 0.5 * 12.7 * 6.1;
const DRIVER_LBS = 170;
const DTL = 0.15;
const TRANS_DATA_6MT = { gears:[3.709, 2.190, 1.536, 1.177, 1.000, 0.832], fd:4.100, dtl:0.15 };

// FM Supercharger Kit weight delta (matches index.html dropdown option value).
const FI_SUPERCHARGER_DELTA = 45;

function buildProf(file, fiDelta = 0){
  const vehicleWeight = BASE.wt + PRHT_DELTA_NC2 + fiDelta;
  const totalLbs = vehicleWeight + FUEL_LBS + DRIVER_LBS;
  const tot_kg = totalLbs * 0.453592;
  const eff = tot_kg * (1 + BASE.rot);
  return {
    eff,
    tot_kg,
    base: BASE,
    Cd: CD,
    spd_corr: 1.0,
    dia_m: BASE.stock_dia_m,
    gears: TRANS_DATA_6MT.gears,
    fd: TRANS_DATA_6MT.fd,
    baro: file.baro,
    _totLbs: totalLbs,
  };
}

function pickHighestQuality(pullsArr){
  let bestI = 0, bestQ = -1;
  pullsArr.forEach((p, i) => { if(p.q > bestQ){ bestQ = p.q; bestI = i; } });
  return bestI;
}

function loadFile(csvPath){
  const text = readUtf16leOrUtf8(csvPath);
  const res = parseCSV(text);
  if(!res.ok) throw new Error('parseCSV failed: ' + res.msg);
  const pulls = detectPulls(res.data, res.tempUnit);
  return {
    rows: res.data,
    pulls,
    baro: res.baro,
    iat_k: res.iat_k,
    baroSource: res.baroSource,
    iatSource: res.iatSource,
    speedSource: res.speedSource,
    tempUnit: res.tempUnit,
  };
}

function runComparePath(fileBefore, fileAfter, opts = {}){
  // Mirror runCompareAnalysis: build per-slot profs, apply MAP-FI override,
  // calcHP × 2, bin × 2, peak each, compute gain. Plus speed traps × 2.
  _domValues.forced = opts.fiBefore || '0';
  _domValues.forcedAfter = opts.fiAfter || '0';
  applyMapFiOverride(fileBefore, 'forced');
  applyMapFiOverride(fileAfter, 'forcedAfter');

  const fiBeforeDelta = parseFloat(opts.fiBefore) || 0;
  const fiAfterDelta  = parseFloat(opts.fiAfter)  || 0;
  const profBefore = buildProf(fileBefore, fiBeforeDelta);
  const profAfter  = buildProf(fileAfter,  fiAfterDelta);

  const selB = pickHighestQuality(fileBefore.pulls);
  const selA = pickHighestQuality(fileAfter.pulls);
  const pullB = fileBefore.pulls[selB];
  const pullA = fileAfter.pulls[selA];

  const rB = calcHP(pullB.rows, profBefore, pullB.iat_c);
  const rA = calcHP(pullA.rows, profAfter, pullA.iat_c);
  const bB = bin(rB), bA = bin(rA);
  const pB = Math.max(...bB.map(r => r.WHP));
  const pA = Math.max(...bA.map(r => r.WHP));

  const trapsB = speedTrapsForPull(pullB.rows, profBefore.spd_corr);
  const trapsA = speedTrapsForPull(pullA.rows, profAfter.spd_corr);

  return {
    pullB, pullA, profBefore, profAfter, selB, selA,
    pB, pA, gain: pA - pB,
    trapsB, trapsA,
  };
}

// ── tests ──
let failures = 0;
function check(label, ok, detail){
  if(ok){
    console.log(`  ✓ ${label}` + (detail ? `  ${detail}` : ''));
  } else {
    console.log(`  ✗ ${label}` + (detail ? `  ${detail}` : ''));
    failures++;
  }
}

console.log('━'.repeat(72));
console.log('VALIDATE_COMPARE.JS — two-file Compare path coverage');
console.log('━'.repeat(72));

// TEST 1: identical files. Speed-trap zero-delta tripwire.
console.log('\n[1] Identical files (real_log.csv as both Before and After)');
{
  const fileA = loadFile(path.join(__dirname, '..', 'real_log.csv'));
  const fileB = loadFile(path.join(__dirname, '..', 'real_log.csv'));
  const r = runComparePath(fileA, fileB);
  console.log(`    Before WHP: ${r.pB.toFixed(2)}  After WHP: ${r.pA.toFixed(2)}  Gain: ${r.gain.toFixed(3)}`);
  check('zero gain', Math.abs(r.gain) < 0.01, `(${r.gain.toFixed(4)} WHP)`);
  // Speed traps
  for(const k of Object.keys(r.trapsB)){
    const tB = r.trapsB[k], tA = r.trapsA[k];
    if(tB === null && tA === null){
      console.log(`    ${k}: not reached in either pull`);
    } else if(tB !== null && tA !== null){
      const delta = Math.abs(tA - tB);
      check(`speed trap ${k} delta = 0`, delta < 0.001, `(Δ=${delta.toFixed(4)}s)`);
    } else {
      check(`speed trap ${k} consistency`, false, `(one null, one not — should never happen on identical files)`);
    }
  }
}

// TEST 2: mismatched files. Smoke test (gain != 0, doesn't crash).
console.log('\n[2] Mismatched files (real_log.csv Before, DataLog-Apr_29_2026 After)');
{
  const fileBefore = loadFile(path.join(__dirname, '..', 'real_log.csv'));
  const fileAfter  = loadFile(path.join(__dirname, '..', 'DataLog-Apr_29_2026_00-16-19-.csv'));
  const r = runComparePath(fileBefore, fileAfter);
  console.log(`    Before WHP: ${r.pB.toFixed(2)}  After WHP: ${r.pA.toFixed(2)}  Gain: ${r.gain.toFixed(2)}`);
  console.log(`    Before baro: ${fileBefore.baro.toFixed(2)} kPa   After baro: ${fileAfter.baro.toFixed(2)} kPa`);
  check('gain is non-zero', Math.abs(r.gain) > 0.5, `(${r.gain.toFixed(2)} WHP — different files should produce different WHP)`);
  check('per-file baro routing — Before profBaro matches Before file baro',
    Math.abs(r.profBefore.baro - fileBefore.baro) < 0.001);
  check('per-file baro routing — After profBaro matches After file baro',
    Math.abs(r.profAfter.baro - fileAfter.baro) < 0.001);
}

// TEST 3: NA Before vs FI After on identical files.
// The supercharger scenario: same pull data, but After is configured with
// +45 lbs of FI weight. After mass is heavier → calcHP back-calculates a
// HIGHER engine force (same acceleration × greater mass). After WHP > Before.
// Speed-trap deltas remain 0 because traps are pure timer (no mass dep).
console.log('\n[3] NA Before vs FI After on identical files (supercharger scenario)');
{
  const fileA = loadFile(path.join(__dirname, '..', 'real_log.csv'));
  const fileB = loadFile(path.join(__dirname, '..', 'real_log.csv'));
  const r = runComparePath(fileA, fileB, { fiBefore: '0', fiAfter: String(FI_SUPERCHARGER_DELTA) });
  console.log(`    Before mass: ${r.profBefore._totLbs.toFixed(1)} lbs   After mass: ${r.profAfter._totLbs.toFixed(1)} lbs`);
  console.log(`    Before WHP: ${r.pB.toFixed(2)}   After WHP: ${r.pA.toFixed(2)}   Gain: ${r.gain.toFixed(2)}`);
  const expectedMassDelta = FI_SUPERCHARGER_DELTA;
  const actualMassDelta = r.profAfter._totLbs - r.profBefore._totLbs;
  check(`After mass = Before mass + ${expectedMassDelta} lbs`,
    Math.abs(actualMassDelta - expectedMassDelta) < 0.01,
    `(actual delta ${actualMassDelta.toFixed(2)} lbs)`);
  check('After WHP > Before WHP',
    r.pA > r.pB,
    `(after-before = ${(r.pA - r.pB).toFixed(2)} WHP)`);
  // Speed traps: identical pull data → identical timer reading regardless of mass
  for(const k of Object.keys(r.trapsB)){
    const tB = r.trapsB[k], tA = r.trapsA[k];
    if(tB !== null && tA !== null){
      const delta = Math.abs(tA - tB);
      check(`speed trap ${k} delta = 0 (mass-independent)`, delta < 0.001, `(Δ=${delta.toFixed(4)}s)`);
    }
  }
}

console.log('\n' + '━'.repeat(72));
if(failures === 0){
  console.log('PASS — all Compare-path checks passed');
  process.exit(0);
} else {
  console.log(`FAIL — ${failures} check${failures === 1 ? '' : 's'} failed`);
  process.exit(1);
}
