// End-to-end lock validator. Runs the full pipeline (parseCSV → detectPulls →
// calcHP → bin → outlier rejection → best/avg/crank) on real_log.csv with the
// configuration spec'd in the lock task: NC2 PRHT 6MT, 170 lb driver, half
// tank, top up, stock everything, Estimate mode, SAE J1349 correction.
//
// Captures: best WHP, avg WHP, est crank HP, baro + source, per-pull IAT.
// Result is the new lock value to paste into ENGINEERING.md.
//
// Cross-check: load real_log.csv in browser at the same configuration. Numbers
// should match. If they diverge, the Node mock has drifted from browser DOM
// behavior and one of the two needs investigation.

const fs = require('fs');
const path = require('path');

// --- Papa Parse shim (same as validate_parse.js) ---
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

// --- extract function bodies from index.html ---
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

const sources = ['findC','detectUnit','parseCSV','detectPulls','savgol','grad','calcHP','bin']
  .map(extract).join('\n\n');

// --- mock DOM that calcHP touches ---
// calcHP reads document.querySelector('#tCorr .tbtn.on')?.dataset.v for the
// correction standard. We mock that to return 'sae' (SAE J1349 — the lock).
global.window = { __lastParseInfo: null, __lastDetectInfo: null };
global.document = {
  querySelector: () => ({ dataset: { v: 'sae' } }),
};
global.Papa = Papa;
const RDA = 287.05;
const G = 9.81;

const code = `
  ${sources}
  module.exports = { findC, detectUnit, parseCSV, detectPulls, calcHP, bin, savgol, grad };
`;
const m2 = { exports: {} };
// Phase A: index.html no longer has module-level baro/iat_k/rho globals;
// atmospheric values flow via parseCSV's return object and prof.baro into
// calcHP. The legacy `var baro = 99.9, ...` shim is gone.
const fn = new Function('module','window','document','Papa','RDA','G','require',
  code);
fn(m2, global.window, global.document, Papa, RDA, G, require);
const { parseCSV, detectPulls, calcHP, bin } = m2.exports;

// --- file reader (handles UTF-16 BOM detection from real_log.csv) ---
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

// ════════════════════════════════════════════════════════════════
// CONFIGURATION — matches lock task spec
// "NC2 PRHT 6MT, 170 lb driver, half tank, top up, stock everything,
//  Estimate mode, SAE J1349 correction"
// ════════════════════════════════════════════════════════════════
const CONFIG = {
  gen: 'nc2',
  topType: 'prht',
  topPos: 'up',     // top up → Cd = prht_up = 0.34
  trans: '6mt',
  driver_lbs: 170,
  fuel_level: 0.5,  // half tank
  // Stock everything — NCP[nc2].swl=19.0, default tires 205/45R17 stock_lbs=21.0
  // wheel/tire/exhaust/other deltas all = 0
};

// NCP[nc2] values (from current index.html, post-drift-fix)
const BASE = {
  wt:        2515,    // NC2 base curb (matches NCP[nc2].wt in index.html)
  swl:       19.0,    // NC2 stock wheel (Python says 18.8 — open drift)
  Cd:        0.36,    // (overridden by topType/topPos)
  A:         1.78,
  Crr:       0.015,
  rot:       0.045,
  stock_dia_m: 0.6163, // NC2 stock 205/45R17
  stock_tire_lbs: 21.0,
};

// Mirror the calcW build-up for Estimate mode, NC2 PRHT, stock everything:
const CD = 0.34;  // PRHT up
const PRHT_DELTA_NC2 = 78;  // current code's delta for NC2 (NC1 is 65)

const vehicleWeight = BASE.wt + 0 /*wheels*/ + 0 /*tires*/ + 0 /*exh*/ + 0 /*other*/
                    + PRHT_DELTA_NC2;
const fuelWeight = CONFIG.fuel_level * 12.7 * 6.1;
const totalLbs   = vehicleWeight + fuelWeight + CONFIG.driver_lbs;
const tot_kg     = totalLbs * 0.453592;
const eff        = tot_kg * (1 + BASE.rot);

// Build the prof object calcHP expects. Phase A: baro is filled in below
// from parseCSV's return — calcHP now reads prof.baro instead of a global.
const prof = {
  eff,
  tot_kg,
  base: BASE,
  Cd: CD,
  spd_corr: 1.0,            // stock tires
  dia_m: BASE.stock_dia_m,
  baro: 99.9,               // placeholder; overwritten after parseCSV runs
};

// Drivetrain loss for 6MT
const DTL = 0.15;

// ════════════════════════════════════════════════════════════════
// RUN
// ════════════════════════════════════════════════════════════════
console.log('━'.repeat(72));
console.log('LOCK VALIDATION — real_log.csv, current index.html');
console.log('━'.repeat(72));
console.log(`config: NC2 PRHT 6MT, ${CONFIG.driver_lbs} lb driver, ${CONFIG.fuel_level*100}% tank, top up, stock everything, Estimate mode, SAE`);
console.log();
console.log(`weight: ${vehicleWeight.toFixed(0)} (vehicle) + ${fuelWeight.toFixed(1)} (fuel) + ${CONFIG.driver_lbs} (driver) = ${totalLbs.toFixed(1)} lbs`);
console.log(`        tot_kg=${tot_kg.toFixed(2)}, eff (with rot)=${eff.toFixed(2)} kg`);
console.log(`prof:   Cd=${CD}, A=${BASE.A}, Crr=${BASE.Crr}, spd_corr=1.000, dia_m=${BASE.stock_dia_m}`);
console.log();

const csvPath = path.join(__dirname, '..', 'real_log.csv');
const text = readUtf16leOrUtf8(csvPath);
const res = parseCSV(text);
if(!res.ok) throw new Error('parseCSV failed: ' + res.msg);
const pulls = detectPulls(res.data, res.tempUnit);
// Phase A: thread per-file atmospheric onto prof so calcHP can read it.
prof.baro = res.baro;

console.log(`parsed: ${res.data.length} rows · ${pulls.length} pulls`);
console.log(`baro:   ${res.baro.toFixed(2)} kPa (${res.baroSource})`);
console.log(`iat:    ${(res.iat_k - 273.15).toFixed(1)} °C from ${res.iatSource}  ← diagnostic only; correction uses constant 25°C ambient`);
console.log();

// Per-pull HP
const pullsHP = pulls.map((p, i) => {
  const calc = calcHP(p.rows, prof, p.iat_c);
  const binned = (calc && calc.length) ? bin(calc) : null;
  const peak = binned && binned.length ? Math.max(...binned.map(r => r.WHP)) : null;
  return { idx: i, pull: p, binned, peak };
}).filter(p => p.binned && p.binned.length);

console.log(`per-pull peak WHP (uncorrected for outliers):`);
pullsHP.forEach(p => {
  const iatStr = p.pull.iat_c === null ? 'null' : `${p.pull.iat_c.toFixed(1)}°C`;
  console.log(`  pull[${p.idx}]: peak ${p.peak.toFixed(2)} WHP @ ${p.pull.maxRPM.toFixed(0)} RPM, IAT ${iatStr}, dur ${p.pull.dur.toFixed(1)}s, q=${p.pull.q}`);
});
console.log();

// Outlier rejection (mirrors runSameSetupAnalysis): 5 WHP from median peak
const peaks = pullsHP.map(p => p.peak);
const sorted = [...peaks].sort((a, b) => a - b);
const median = sorted.length % 2
  ? sorted[(sorted.length - 1) / 2]
  : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
const OUTLIER = 5.0;
const keepMask = peaks.map(p => Math.abs(p - median) <= OUTLIER);
const numRejected = keepMask.filter(k => !k).length;

console.log(`outlier rejection: median peak ${median.toFixed(2)} WHP, threshold ±${OUTLIER}`);
console.log(`  rejected: ${numRejected}/${pullsHP.length}`);
const kept = (pullsHP.length > 1 && numRejected > 0 && numRejected < pullsHP.length)
  ? pullsHP.filter((_, i) => keepMask[i])
  : pullsHP;
console.log(`  kept: ${kept.map(p => `pull[${p.idx}]=${p.peak.toFixed(2)}`).join(', ')}`);
console.log();

// Best across kept
const peaksKept = kept.map(p => p.peak);
const bestPeak = Math.max(...peaksKept);
const bestIdx = peaksKept.indexOf(bestPeak);

// Avg = mean across kept pulls' peak WHP
// (matches the headline "Avg WHP" tile, which averages peaks not bin-by-bin)
const avgPeak = peaksKept.reduce((s, p) => s + p, 0) / peaksKept.length;

const crankHP = bestPeak / (1 - DTL);

console.log('━'.repeat(72));
console.log('LOCK VALUES');
console.log('━'.repeat(72));
console.log(`  Best WHP:     ${bestPeak.toFixed(1)} (pull[${kept[bestIdx].idx}])`);
console.log(`  Avg WHP:      ${avgPeak.toFixed(1)} (mean of ${kept.length} kept pulls)`);
console.log(`  Est crank HP: ${crankHP.toFixed(1)} (best / (1 - ${DTL}) = best / ${(1-DTL).toFixed(2)})`);
console.log();
console.log(`atmospheric:   baro ${res.baro.toFixed(2)} kPa (${res.baroSource}), ambient 25.0°C constant (locked)`);
console.log(`per-pull IAT:  ${pulls.map(p => p.iat_c?.toFixed(1) + '°C').join(', ')}  ← diagnostic only`);
