# P1 — `detectPulls` °C/°F unit detection bug

Follow-up to the P0 batch (per-file speed unit / baro bounds / IAT bounds /
MAP-FI override / per-pull IAT correction → reverted to ambient 25°C).

This bug was **exposed by validation but not addressed** by the engineer's
P0 plan. It is now reachable in normal usage and silently breaks the
heat-soak warning UI.

---

## Bug

`detectPulls` computes per-pull intake air temperature (`iat_c`) from raw
sample values. It uses a self-contained heuristic to guess °C vs °F:

```js
// index.html:1919 (current)
pullIAT_C = iat_avg > 60 ? (iat_avg - 32) * 5/9 : iat_avg;
```

This heuristic ignores `tempUnit`, which `parseCSV` already detected from
the column header (e.g. `"Intake Air Temperature(C)"` → `tempUnit = 'celsius'`,
already stored at [`window.__lastParseInfo.units.temp`](index.html#L1850)).

**Failure mode:** a heat-soaked pull in a Celsius-logged file with IAT
60–100°C gets misclassified as Fahrenheit and silently converted to a
cool 16–38°C value.

| Real IAT | Logged in column | Heuristic sees | Heuristic does | Result |
|---|---|---|---|---|
| 65 °C (heat soak) | °C column | `iat_avg=65 > 60` | "treat as °F" | `(65-32)×5/9 = 18.3 °C` ✗ |
| 75 °C (severe soak) | °C column | `iat_avg=75 > 60` | "treat as °F" | `(75-32)×5/9 = 23.9 °C` ✗ |

The engineer's Fix #2b bounds check (`-10 ≤ ic ≤ 100`) does **not** catch
this — 18.3 and 23.9 are both in-bounds.

## Why it matters now

After the option-2 revert (constant 25°C ambient in the J1349 correction),
`iat_c` no longer feeds the **math** — but it still drives:

1. **The heat-soak banner** ([index.html:2113](index.html#L2113)) — which
   compares each pull's `iat_c` to the first pull's. A heat-soaked pull
   reading falsely as cool will *not* trigger the banner.
2. **Per-pull IAT label in the UI** ([index.html:2122](index.html#L2122))
   — which displays the wrong value.
3. **Auto-deselect of heat-soaked pulls** in same-setup mode
   ([index.html:2148](index.html#L2148)) — which silently keeps bad pulls
   in the analysis.

So the user gets a heat-soaked log, sees no warning, and the tool blindly
averages cool + heat-soaked pulls together. This was the entire purpose
of the heat-soak detection feature, defeated by a unit-detection bug
inside the same code path.

## Reproduction

A Celsius-logged session with a hot-soak pull at IAT > 60°C is enough.
Synthetic file: `test_data/synth_heatsoak_celsius.csv` (will be generated
in this fix's verification step).

Today (broken): pull display shows `IAT 18.3°C` and no heat-soak banner.
After fix: pull display shows `IAT 65.0°C` and the heat-soak banner fires.

## Root cause

`detectPulls` was written to be self-contained and re-derives unit
detection from raw values, even though `parseCSV` has already authoritatively
identified the header unit a few lines earlier in the same parse pass.
The two functions don't share state about the column unit — `parseCSV`
keeps it local, and `detectPulls` re-guesses.

## Fix

Thread the file-level `tempUnit` from `parseCSV` into `detectPulls`. Use
the header-derived unit when available; fall back to the existing >60
heuristic only when the header was ambiguous.

This is **not a physics change.** The correction-factor math
([calcHP](index.html#L1497)) does not depend on `iat_c` at all post-revert
— it uses constant 298.15 K. The fix is purely about *correctly labeling*
the per-pull IAT for the warning UI.

### Diff (revised after engineer review)

**1.** Update `detectPulls` signature to accept `tempUnit`:

```js
// BEFORE (index.html:1862):
function detectPulls(data){

// AFTER:
function detectPulls(data, tempUnit){
```

**2.** Replace the per-pull IAT block to prefer header-derived unit. When
the unit is known and the value still lands out-of-bounds, that's a
sensor fault or wrong-unit-in-header — emit a `console.warn` so the
diagnostic trail survives, then null out the same way:

```js
// BEFORE (index.html:1915–1924):
let pullIAT_C = null;
if(iats.length){
  const iat_avg = iats.reduce((a,b) => a+b) / iats.length;
  // If avg is > 60, assume Fahrenheit; otherwise Celsius
  pullIAT_C = iat_avg > 60 ? (iat_avg - 32) * 5/9 : iat_avg;
  // FIX #2: same bounds as file-level IAT. Out-of-range almost certainly
  // means unit detection failed for this pull. Set null so calcHP falls back
  // to file-mean iat_k (which itself has been bounds-checked).
  if(pullIAT_C < -10 || pullIAT_C > 100) pullIAT_C = null;
}

// AFTER:
let pullIAT_C = null;
if(iats.length){
  const iat_avg = iats.reduce((a,b) => a+b) / iats.length;
  // P1 FIX: Use file-level tempUnit (detected from header) when known.
  // The standalone >60 heuristic mis-classified heat-soaked Celsius pulls
  // as Fahrenheit (e.g. 65°C → 18.3°C), which silently disabled the
  // heat-soak banner in the very scenarios it was designed for.
  if(tempUnit === 'fahrenheit'){
    pullIAT_C = (iat_avg - 32) * 5/9;
  } else if(tempUnit === 'celsius'){
    pullIAT_C = iat_avg;
  } else {
    // Header didn't specify; fall back to >60 heuristic.
    pullIAT_C = iat_avg > 60 ? (iat_avg - 32) * 5/9 : iat_avg;
  }
  // Bounds safety net. If the unit was KNOWN from the header and the
  // value is still OOB, that's not unit ambiguity — it's a sensor fault
  // or a wrong-unit header. Warn so the trail survives, then null.
  if(pullIAT_C < -10 || pullIAT_C > 100){
    if(tempUnit){
      console.warn(`[MiataDyno] IAT out of bounds: ${pullIAT_C.toFixed(1)}°C from ${tempUnit} header. Sensor fault or incorrect header.`);
    }
    pullIAT_C = null;
  }
}
```

**3.** Thread `tempUnit` through `parseCSV`'s return value (engineer
refinement: explicit coupling beats reading from the diagnostic stash).
The `__lastParseInfo` window variable stays as a console-debug stash —
not a control-flow channel.

```js
// BEFORE (parseCSV return, index.html:1859):
return {ok:true, data};

// AFTER:
return {ok:true, data, tempUnit};
```

```js
// BEFORE (handleFile, index.html:1996–1999):
const res = parseCSV(text);
if(!res.ok){ showSt(res.msg, 'err'); return; }
rows = res.data;
pulls = detectPulls(rows);

// AFTER:
const res = parseCSV(text);
if(!res.ok){ showSt(res.msg, 'err'); return; }
rows = res.data;
pulls = detectPulls(rows, res.tempUnit);
```

## Why not just fix the heuristic?

There is no robust unit-agnostic heuristic. The °C/°F overlap zone (20–60)
covers normal IAT during cruise (°C reading) and normal IAT during a pull
(°F reading). The header is the only authoritative source. When the
header is missing, the >60 heuristic is the best we have, and that
fallback is preserved.

## What's NOT changed

- `calcHP` correction math — unaffected (uses constant 25°C ambient).
- File-level `iat_k` — unaffected (parsed correctly via header in
  `parseCSV` already).
- Heat-soak banner / UI logic — unaffected at the consumer side; just
  receives correct `iat_c` values now.
- The `pullIatC` parameter on `calcHP` — kept; option 3 (real ambient)
  will still plug in there.

## Verification

Three synthetic CSVs covering the three branches of the new logic:

| File | Header tag | tempUnit | Tests |
|---|---|---|---|
| `synth_heatsoak.csv` (existing) | `(F)` | `'fahrenheit'` | regression — °F branch unchanged |
| `synth_heatsoak_celsius.csv` (NEW) | `(C)` | `'celsius'` | the bug repro — °C branch correctly used |
| `synth_heatsoak_notagged.csv` (NEW) | none | `null` | heuristic fallback path still behaves as documented (still buggy on the >60 branch — that's intentional, it's the only thing we can do without a header tag) |

Expected `iat_c` values per pull (engineer's verification finding —
the untagged case must continue to misbehave on the >60 readings,
because there's no robust way to disambiguate without the header):

| Case | Pull 1 IAT raw | Pull 5 IAT raw | Pull 1 `iat_c` | Pull 5 `iat_c` | Banner |
|---|---|---|---|---|---|
| °F header (control) | 86 | 167 | 30.0 °C | 75.0 °C | fires ✓ |
| °C header (bug repro, post-fix) | 30 | 75 | 30.0 °C | **75.0 °C ✓** | fires ✓ |
| °C header (bug repro, pre-fix) | 30 | 75 | 30.0 °C | **23.9 °C ✗** | does NOT fire ✗ |
| no tag (heuristic fallback, pre+post-fix) | 30 | 75 | 30.0 °C | **23.9 °C ✗ (documented)** | does NOT fire (documented) |

Run `node test_data/validate_parse.js` after applying the fix.

**Console-warn smoke test:** drop a CSV with a `(C)` header and an
artificially out-of-range IAT (e.g. a row with 250°C from a stuck sensor).
Pull's `iat_c` should be null AND the console should show
`[MiataDyno] IAT out of bounds: 250.0°C from celsius header...`. This
is the new diagnostic trail.

## Out of scope

- Python backport in `calculate_hp.py` — separate task.
- Option 3 (real ambient temperature) — separate task.
