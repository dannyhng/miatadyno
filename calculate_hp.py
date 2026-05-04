# calculate_hp.py — v2.3
# New in v2.3:
#   FEATURE 3: Speed trap timing (per Petrol_Head72 feedback)
#     - Direct measurement of elapsed time between speed thresholds
#     - 30-50, 40-60, 50-70 MPH brackets
#     - No physics model required — pure measurement
#     - Most trustworthy metric in the entire tool
#     - Run-to-run repeatability shown alongside times
#
# Carried over from v2.2:
#   - Multi-run averaging with outlier rejection + quality weighting
#   - Open-Meteo weather API for baro + ambient temp
#   - Heat-soak detection
#   - Block 4 aero double-counting fix (RHO_STD in F_aero)
#   - Auto encoding detection (UTF-8 vs UTF-16)
#
# Run:                    python calculate_hp.py
# With weather API:       python calculate_hp.py --lat 45.52 --lon -122.68
# With real BlueDriver:   python calculate_hp.py --csv real_log.csv --lat 45.52 --lon -122.68

import sys
import json
import urllib.request
import urllib.error
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
from vehicle_profiles import build_vehicle_profile

# ── CLI ARGUMENTS ─────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description='MiataDyno HP Calculator v2.3')
parser.add_argument('--lat', type=float, default=None, help='Latitude for weather API')
parser.add_argument('--lon', type=float, default=None, help='Longitude for weather API')
parser.add_argument('--csv', type=str,   default=None, help='Override CSV file')
args = parser.parse_args()

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

CSV_FILE     = args.csv or 'real_log.csv'
CSV_ENCODING = 'utf-8'   # new file is UTF-8, not UTF-16

# Auto-detect encoding (UTF-16 for real BlueDriver, UTF-8 for synthetic)
def detect_encoding(filepath):
    with open(filepath, 'rb') as f:
        raw = f.read(4)
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return 'utf-16'
    return 'utf-8'

CSV_ENCODING = detect_encoding(CSV_FILE)

VEHICLE_CONFIG = {
    'generation':        'nc23',
    'top_type':          'prht',
    'transmission':      '6mt',
    'top_position':      'up',
    'tire_width':        205,
    'tire_aspect':       55,      # was 45
    'wheel_dia_inches':  16,      # was 17
    'wheel_weight_lbs':  12.0,    # was 18.8
    'exhaust_delta_lbs': -12.0,   # race muffler
    'other_delta_lbs':   0,
    'fuel_level':        0.5,
    'driver_weight_lbs': 170,     # was 165
    'passenger':         False,    # adds 150 lbs
}

IAT_UNITS          = 'F'
ROAD_GRADE_PCT     = 0.0
THROTTLE_THRESHOLD = 85
MIN_PULL_SECONDS   = 3.0
RPM_BIN_SIZE       = 500

# Multi-run averaging
OUTLIER_THRESHOLD_WHP = 5.0
MIN_PULLS_TO_AVERAGE  = 2
RPM_GRID = np.arange(2500, 7250, 250)

# FEATURE 3: Speed trap brackets (start_mph, end_mph)
SPEED_TRAPS = [
    (30, 50),
    (40, 60),
    (50, 70),
    (60, 80),
]

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

G       = 9.81
R_DRY   = 287.058
RHO_STD = 1.225

# ── WEATHER API ───────────────────────────────────────────────────────────────

def get_weather(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           f"&current=surface_pressure,temperature_2m")
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        c = data['current']
        return {'baro_kpa': c['surface_pressure']/10.0,
                'ambient_c': c['temperature_2m'],
                'source': 'Open-Meteo API'}
    except Exception as e:
        print(f"  ⚠  Weather API failed ({e}). Using OBD baro.")
        return None

# ── LOAD FILE ─────────────────────────────────────────────────────────────────

print("=" * 60)
print("MiataDyno — HP Calculator v2.3")
print("=" * 60)

df = pd.read_csv(CSV_FILE, skiprows=2, encoding=CSV_ENCODING)
df.columns = [c.strip() for c in df.columns]
print(f"\nLoaded: {CSV_FILE} ({len(df)} rows, {CSV_ENCODING})")

# ── COLUMNS ───────────────────────────────────────────────────────────────────

def find_col(df, kws):
    for col in df.columns:
        if any(k.lower() in col.lower() for k in kws):
            return col
    return None

time_col     = find_col(df, ['time'])
rpm_col      = find_col(df, ['rpm'])
speed_col    = find_col(df, ['speed'])
throttle_col = find_col(df, ['throttle', 'load'])
baro_col     = find_col(df, ['baro', 'barometric'])
iat_col      = find_col(df, ['intake air'])

print(f"Columns: time={time_col} | rpm={rpm_col} | speed={speed_col} | throttle={throttle_col}")

missing = [n for n,c in [('time',time_col),('rpm',rpm_col),('speed',speed_col),('throttle',throttle_col)] if c is None]
if missing:
    print(f"\n❌ Missing columns: {missing}")
    print(f"   Found: {list(df.columns)}")
    sys.exit(1)

# ── PROFILE ───────────────────────────────────────────────────────────────────

profile = build_vehicle_profile(**VEHICLE_CONFIG)
profile['road_grade'] = ROAD_GRADE_PCT

# Stock tire rolling diameter for spd_corr — must match JS NCP[gen].stock_dia_m.
# Source: 195/50R16 (NC1) and 205/45R17 (NC2/3) computed via
# calc_tire_diameter_m(width, aspect, wheel_in). Backport ticket: lift these
# into vehicle_profiles.py once SSoT lands so JS and Python share the constant.
STOCK_TIRE_DIA_M = {
    'nc1':  0.6014,   # 195/50R16
    'nc23': 0.6163,   # 205/45R17
}
profile['spd_corr'] = profile['tire_dia_m'] / STOCK_TIRE_DIA_M[profile['generation']]

vehicle_name = (
    f"{'NC1' if profile['generation']=='nc1' else 'NC2/3'} MX-5 "
    f"{'Soft Top' if profile['top_type']=='soft' else 'PRHT'} "
    f"{profile['transmission'].upper()}"
)

print(f"\nVehicle: {vehicle_name}")
print(f"  Total weight: {profile['total_lbs']:.0f} lbs ({profile['total_kg']:.0f} kg)")
print(f"  Eff. mass:    {profile['eff_mass_kg']:.0f} kg")
print(f"  Cd: {profile['Cd']} | A: {profile['A']} m² | DTL: {profile['dtl']*100:.0f}%")

# ── UNITS ─────────────────────────────────────────────────────────────────────

df['rpm_num']      = pd.to_numeric(df[rpm_col],      errors='coerce')
df['speed_num']    = pd.to_numeric(df[speed_col],    errors='coerce')
df['throttle_num'] = pd.to_numeric(df[throttle_col], errors='coerce')
df['time_num']     = pd.to_numeric(df[time_col],     errors='coerce')

# ── ATMOSPHERIC ───────────────────────────────────────────────────────────────

print(f"\nAtmospheric conditions:")

weather = None
if args.lat is not None and args.lon is not None:
    print(f"  Fetching weather ({args.lat:.4f}, {args.lon:.4f})...")
    weather = get_weather(args.lat, args.lon)

if weather:
    baro_kpa  = weather['baro_kpa']
    ambient_c = weather['ambient_c']
    source    = weather['source']
else:
    if baro_col:
        b_raw = pd.to_numeric(df[baro_col], errors='coerce').mean()
        baro_kpa = b_raw * 3.38639 if b_raw < 50 else b_raw
    else:
        baro_kpa = 101.3
    if baro_kpa < 85 or baro_kpa > 105:
        baro_kpa = 101.3
    ambient_c = 25.0
    source    = 'OBD sensor / standard'

ambient_k = ambient_c + 273.15

obd_iat_c = None
if iat_col:
    iat_raw = pd.to_numeric(df[iat_col], errors='coerce').mean()
    if not np.isnan(iat_raw):
        obd_iat_c = (iat_raw-32)*5/9 if IAT_UNITS=='F' else iat_raw

SAE_CORRECTION = (99.0 / baro_kpa) * np.sqrt(ambient_k / 298.15)
rho_actual = (baro_kpa * 1000) / (R_DRY * ambient_k)

print(f"  Source:       {source}")
print(f"  Baro:         {baro_kpa:.2f} kPa")
print(f"  Ambient:      {ambient_c:.1f}°C → SAE reference")
if obd_iat_c is not None:
    print(f"  OBD IAT:      {obd_iat_c:.1f}°C → heat-soak detection")
print(f"  SAE factor:   {SAE_CORRECTION:.4f}")

# ── POLLING RATE ──────────────────────────────────────────────────────────────

t_vals = df['time_num'].dropna().values
median_dt = np.median(np.diff(t_vals))
polling_hz = 1.0/median_dt if median_dt > 0 else 0
print(f"\nOBD polling: {polling_hz:.1f} Hz ({median_dt:.2f}s)")

# ── DETECT PULLS ──────────────────────────────────────────────────────────────

in_pull, p_start, p_start_t = False, None, None
pulls_found = []

for i, row in df.iterrows():
    thr  = row['throttle_num']
    spd  = row['speed_num']
    time = row['time_num']
    if pd.isna(thr) or pd.isna(time):
        continue
    if thr >= THROTTLE_THRESHOLD and spd > 5:
        if not in_pull:
            in_pull, p_start, p_start_t = True, i, time
    else:
        if in_pull:
            dur = time - p_start_t
            if dur >= MIN_PULL_SECONDS:
                seg = df.loc[p_start:i-1]
                pulls_found.append({
                    'start':p_start, 'end':i-1,
                    'start_time':p_start_t, 'duration':dur,
                    'max_rpm':seg['rpm_num'].max(),
                    'max_speed':seg['speed_num'].max(),
                })
            in_pull = False

print(f"\nPulls detected: {len(pulls_found)}")
for i, p in enumerate(pulls_found):
    print(f"  Pull {i+1}: {p['start_time']:.1f}s | {p['duration']:.1f}s | "
          f"to {p['max_rpm']:.0f} RPM | {p['max_speed']:.0f} MPH")

if not pulls_found:
    print("\n⚠ No pulls found.")
    sys.exit(1)

# ── QUALITY VALIDATOR ─────────────────────────────────────────────────────────

def score_quality(seg):
    warnings, score = [], 100
    speeds = seg[speed_col].values
    rpms = seg[rpm_col].values
    n = len(speeds)

    drops = np.sum(np.diff(speeds) < -1.5)
    drop_pct = drops / max(len(np.diff(speeds)), 1)
    if drop_pct > 0.15:
        warnings.append(f"Speed dropped {drops}x")
        score -= int(drop_pct * 60)

    mask = (rpms > 500) & (speeds > 10)
    if mask.sum() > 3:
        ratios = speeds[mask] / rpms[mask]
        cv = np.std(ratios) / np.mean(ratios)
        if cv > 0.05:
            warnings.append(f"Speed/RPM CV={cv:.2%} — possible shift")
            score -= int(cv * 200)

    if n < 8:
        warnings.append(f"Only {n} data points")
        score -= 20

    return max(0, min(100, score)), warnings

# ── PHYSICS ───────────────────────────────────────────────────────────────────

def calc_pull_hp(seg_df):
    seg = seg_df.copy().reset_index(drop=True)
    seg['speed_ms'] = seg['speed_num'] * 0.44704

    n = len(seg)
    if n >= 7:
        win = max(7, (n // 6) | 1)
        win = min(win, n if n%2==1 else n-1)
        seg['speed_smooth'] = savgol_filter(seg['speed_ms'].values, win, 3)
    else:
        seg['speed_smooth'] = seg['speed_ms']

    seg['accel'] = np.gradient(seg['speed_smooth'].values, seg['time_num'].values)

    v = seg['speed_smooth'].values
    a = seg['accel'].values

    F_total = (
        profile['eff_mass_kg'] * a
        + profile['Crr'] * profile['total_kg'] * G
        + 0.5 * RHO_STD * profile['Cd'] * profile['A'] * v**2
        + profile['total_kg'] * G * np.sin(np.arctan(ROAD_GRADE_PCT/100))
    )
    WHP = (F_total * v / 745.7) * SAE_CORRECTION

    rpm_arr = seg['rpm_num'].values
    with np.errstate(divide='ignore', invalid='ignore'):
        WTQ = np.where(rpm_arr > 0, (WHP * 5252) / rpm_arr, 0)

    seg['WHP'] = WHP
    seg['WTQ'] = WTQ
    return seg

def rpm_bin(seg):
    seg = seg.copy()
    rpm_min = int(seg['rpm_num'].min() // RPM_BIN_SIZE) * RPM_BIN_SIZE
    rpm_max = int(seg['rpm_num'].max() // RPM_BIN_SIZE + 1) * RPM_BIN_SIZE
    bins = np.arange(rpm_min, rpm_max + RPM_BIN_SIZE, RPM_BIN_SIZE)
    labels = (bins[:-1] + RPM_BIN_SIZE//2).astype(float)
    seg['rpm_bin'] = pd.cut(seg['rpm_num'], bins=bins, labels=labels)
    binned = (seg.groupby('rpm_bin', observed=True)[['WHP','WTQ']]
                .agg(['mean','std','count']))
    binned.columns = ['WHP','WHP_std','WHP_n','WTQ','WTQ_std','WTQ_n']
    binned.index = binned.index.astype(float)
    return binned.dropna(subset=['WHP','WTQ']).reset_index().rename(columns={'rpm_bin':'RPM'})

# ═══ FEATURE 3: SPEED TRAP TIMING ═════════════════════════════════════════════

def calc_speed_trap(seg_df, v_start_mph, v_end_mph, spd_corr=1.0):
    """
    Direct measurement of elapsed time between two speed thresholds.
    No physics model — just timer reading.
    Returns elapsed time in seconds, or None if data doesn't cover the range.

    This is the most trustworthy metric in the entire tool because it makes
    zero assumptions about mass, aero, or any other vehicle parameter.

    spd_corr applies the JS-side speed correction (dia_m / stock_dia_m) so
    bracket thresholds are real-world mph rather than OBD-reported (stock-tire)
    mph. Default 1.0 preserves prior behavior; pass profile['tire_dia_m'] /
    base_stock_dia_m to match the JS path exactly.
    """
    speeds = seg_df['speed_num'].values * spd_corr
    times  = seg_df['time_num'].values

    # Find first crossing of v_start (going up)
    idx_start = None
    for i in range(len(speeds) - 1):
        if speeds[i] <= v_start_mph and speeds[i+1] >= v_start_mph:
            # Linear interpolation for sub-sample precision
            frac = (v_start_mph - speeds[i]) / (speeds[i+1] - speeds[i]) if speeds[i+1] != speeds[i] else 0
            t_start = times[i] + frac * (times[i+1] - times[i])
            idx_start = i
            break

    if idx_start is None:
        return None

    # Find first crossing of v_end (going up) AFTER v_start crossing
    for i in range(idx_start, len(speeds) - 1):
        if speeds[i] <= v_end_mph and speeds[i+1] >= v_end_mph:
            frac = (v_end_mph - speeds[i]) / (speeds[i+1] - speeds[i]) if speeds[i+1] != speeds[i] else 0
            t_end = times[i] + frac * (times[i+1] - times[i])
            return t_end - t_start

    return None  # didn't reach v_end

def speed_traps_for_pull(seg_df, spd_corr=1.0):
    """Return dict of all speed trap timings for a single pull."""
    return {
        f"{lo}-{hi}": calc_speed_trap(seg_df, lo, hi, spd_corr)
        for lo, hi in SPEED_TRAPS
    }

# ── PROCESS PULLS ─────────────────────────────────────────────────────────────

results_binned   = []
quality_scores   = []
pull_iats_c      = []
pull_speed_traps = []   # list of dicts, one per pull
pull_segments    = []   # raw segments for speed trap recalc

for i, p in enumerate(pulls_found):
    seg = df.loc[p['start']:p['end']]
    q, ws = score_quality(seg)
    print(f"\nPull {i+1} — quality {q}/100")
    for w in ws:
        print(f"  ⚠  {w}")

    if iat_col and not seg[iat_col].dropna().empty:
        raw = pd.to_numeric(seg[iat_col], errors='coerce').iloc[0]
        if not np.isnan(raw):
            pull_iats_c.append((raw-32)*5/9 if IAT_UNITS=='F' else raw)

    if q < 50:
        print(f"  ✗ Skipping — quality too low")
        continue

    result = calc_pull_hp(seg)
    result_filt = result[result['speed_ms'] > 3.0].copy()
    binned = rpm_bin(result_filt)

    # Speed traps from raw segment (before HP filtering).
    # spd_corr brings OBD speed to real-world mph for non-stock tire diameters.
    traps = speed_traps_for_pull(result.reset_index(drop=True), profile['spd_corr'])

    results_binned.append(binned)
    quality_scores.append(q)
    pull_speed_traps.append(traps)
    pull_segments.append(result)

    peak = binned['WHP'].max()
    rpm_at_peak = binned.loc[binned['WHP'].idxmax(), 'RPM']
    print(f"  Peak WHP: {peak:.1f} @ {rpm_at_peak:.0f} RPM | "
          f"WTQ: {binned['WTQ'].max():.1f} lb-ft")

    # Display speed traps
    trap_strs = []
    for bracket, t in traps.items():
        if t is not None:
            trap_strs.append(f"{bracket} MPH: {t:.2f}s")
    if trap_strs:
        print(f"  Speed traps: {' | '.join(trap_strs)}")

if not results_binned:
    print("\n⚠ No pulls passed quality check.")
    sys.exit(1)

# Heat soak
if len(pull_iats_c) >= 2:
    print(f"\nIAT per pull: {[f'{t:.1f}°C' for t in pull_iats_c]}")
    for i, iat in enumerate(pull_iats_c[1:], 1):
        d = iat - pull_iats_c[0]
        if d > 8:
            print(f"  ⚠  Heat soak: Pull {i+1} +{d:.1f}°C — engine making less power")

# ── FEATURE 1: AVERAGING ──────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"MULTI-RUN AVERAGING ({len(results_binned)} clean pull(s))")
print(f"{'='*60}")

use_averaged = False
avg_rpm = avg_whp = avg_wtq = std_whp = None

if len(results_binned) >= MIN_PULLS_TO_AVERAGE:
    peaks = np.array([b['WHP'].max() for b in results_binned])
    med = np.median(peaks)
    keep = np.abs(peaks - med) <= OUTLIER_THRESHOLD_WHP
    n_rejected = int(np.sum(~keep))
    if n_rejected:
        print(f"  Rejected {n_rejected} outlier(s)")

    clean_b = [b for b,k in zip(results_binned, keep) if k]
    clean_q = [q for q,k in zip(quality_scores, keep) if k]

    if len(clean_b) >= MIN_PULLS_TO_AVERAGE:
        weights = np.array(clean_q, dtype=float) / 100.0
        iwhp, iwtq = [], []
        for b in clean_b:
            iwhp.append(np.interp(RPM_GRID, b['RPM'].values, b['WHP'].values, left=np.nan, right=np.nan))
            iwtq.append(np.interp(RPM_GRID, b['RPM'].values, b['WTQ'].values, left=np.nan, right=np.nan))
        iwhp = np.array(iwhp)
        iwtq = np.array(iwtq)

        w_mat = np.where(np.isnan(iwhp), 0, weights[:, np.newaxis])
        w_sum = w_mat.sum(axis=0)
        avg_whp = np.where(w_sum > 0, np.nansum(iwhp * w_mat, axis=0) / w_sum, np.nan)

        w_mat2 = np.where(np.isnan(iwtq), 0, weights[:, np.newaxis])
        w_sum2 = w_mat2.sum(axis=0)
        avg_wtq = np.where(w_sum2 > 0, np.nansum(iwtq * w_mat2, axis=0) / w_sum2, np.nan)

        n_valid = (~np.isnan(iwhp)).sum(axis=0)
        std_whp = np.where(n_valid >= 2, np.nanstd(iwhp, axis=0), np.nan)

        valid = ~np.isnan(avg_whp)
        avg_rpm = RPM_GRID[valid]
        avg_whp = avg_whp[valid]
        avg_wtq = avg_wtq[valid]
        std_whp = std_whp[valid]
        use_averaged = True

        peak_avg_hp = np.nanmax(avg_whp)
        peak_avg_rpm = avg_rpm[np.nanargmax(avg_whp)]
        mean_std = float(np.nanmean(std_whp[~np.isnan(std_whp)])) if np.any(~np.isnan(std_whp)) else 0

        print(f"\nAveraged ({len(clean_b)} pulls):")
        print(f"  Peak WHP:   {peak_avg_hp:.1f} @ {peak_avg_rpm:.0f} RPM")
        print(f"  Peak WTQ:   {np.nanmax(avg_wtq):.1f} lb-ft")
        print(f"  ±1σ:        {mean_std:.1f} WHP run-to-run")

# ═══ FEATURE 3: SPEED TRAP SUMMARY ════════════════════════════════════════════

print(f"\n{'='*60}")
print(f"SPEED TRAP TIMING (no physics model — direct measurement)")
print(f"{'='*60}")
print("This is the most trustworthy metric — pure timer reading.")
print("Use these numbers to compare before/after a mod with high confidence.\n")

for bracket_name in [f"{lo}-{hi}" for lo,hi in SPEED_TRAPS]:
    times = [traps[bracket_name] for traps in pull_speed_traps if traps[bracket_name] is not None]
    if not times:
        continue
    times = np.array(times)
    if len(times) == 1:
        print(f"  {bracket_name:>5} MPH: {times[0]:.2f}s (1 pull)")
    else:
        mean_t = times.mean()
        std_t  = times.std()
        print(f"  {bracket_name:>5} MPH: {mean_t:.2f}s ± {std_t:.3f}s "
              f"({len(times)} pulls, range {times.min():.2f}–{times.max():.2f}s)")

# ── INDIVIDUAL TABLES ─────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"INDIVIDUAL PULLS ({RPM_BIN_SIZE} RPM bins)")
print(f"{'='*60}")

for i, b in enumerate(results_binned):
    print(f"\nPull {i+1} (q={quality_scores[i]}/100):")
    print(f"  {'RPM':>7} {'WHP':>8} {'WTQ':>8}")
    print(f"  {'-'*26}")
    for _, row in b.iterrows():
        print(f"  {row['RPM']:>7.0f} {row['WHP']:>8.1f} {row['WTQ']:>8.1f}")

# ── SANITY ────────────────────────────────────────────────────────────────────

best = results_binned[np.argmax(quality_scores)]
peak_hp = best['WHP'].max()
peak_rpm = best.loc[best['WHP'].idxmax(), 'RPM']
peak_tq = best['WTQ'].max()
EXPECTED, TOL = 123, 15
print(f"\nBest pull: {peak_hp:.1f} WHP @ {peak_rpm:.0f} RPM | {peak_tq:.1f} WTQ")
print(f"Reference: ~{EXPECTED} WHP (stock NC2/3, 118–128 on Dynojet)")
print(f"Delta:     {peak_hp - EXPECTED:+.1f} WHP")
if abs(peak_hp - EXPECTED) <= TOL:
    print(f"✓ Within ±{TOL} WHP of reference")
else:
    print(f"⚠ More than ±{TOL} WHP from reference")

# ── PLOT ──────────────────────────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(11, 6))
grey = ['#777','#888','#999','#aaa']

for i, b in enumerate(results_binned):
    ax.plot(b['RPM'], b['WHP'], color=grey[i%len(grey)],
            linewidth=1.2, linestyle='--', alpha=0.5,
            label=f'Pull {i+1} (q={quality_scores[i]})')

if use_averaged:
    ax.plot(avg_rpm, avg_whp, color='#e8a020', linewidth=3.0,
            label=f'Averaged WHP ({len(clean_b)} pulls)')
    ax.plot(avg_rpm, avg_wtq, color='#e8a020', linewidth=1.5,
            linestyle=':', alpha=0.7, label='Averaged WTQ')
    has_std = ~np.isnan(std_whp)
    if has_std.any():
        ax.fill_between(avg_rpm[has_std],
                        avg_whp[has_std] - std_whp[has_std],
                        avg_whp[has_std] + std_whp[has_std],
                        color='#e8a020', alpha=0.18,
                        label=f'±1σ ({mean_std:.1f} WHP)')
else:
    bi = np.argmax(quality_scores)
    b = results_binned[bi]
    ax.plot(b['RPM'], b['WHP'], color='#e8a020', linewidth=3.0, label='Best WHP')
    ax.plot(b['RPM'], b['WTQ'], color='#e8a020', linewidth=1.5,
            linestyle=':', alpha=0.7, label='Best WTQ')

ax.set_xlabel('Engine RPM', fontsize=12)
ax.set_ylabel('WHP / WTQ (lb-ft)', fontsize=12)
ax.set_title(
    f"MiataDyno v2.3 — {vehicle_name}\n"
    f"{profile['total_lbs']:.0f} lbs | Baro: {baro_kpa:.1f} kPa | "
    f"Ambient: {ambient_c:.1f}°C | SAE: {SAE_CORRECTION:.4f}",
    fontsize=10
)
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('dyno_result.png', dpi=150)
print("\nChart saved as dyno_result.png")
plt.show()