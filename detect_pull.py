import pandas as pd

# ── Load the file (same as before) ────────────────────────────────────────
df = pd.read_csv('test_log.csv', skiprows=2)
df.columns = df.columns.str.strip()

# ── Find column names automatically ───────────────────────────────────────
# We search for keywords instead of hardcoding exact names
# This means it will still work when real BlueDriver column names
# are slightly different from our synthetic file

def find_col(df, keywords):
    """Find a column by searching for keywords in its name."""
    for col in df.columns:
        if any(k.lower() in col.lower() for k in keywords):
            return col
    return None

time_col    = find_col(df, ['time'])
rpm_col     = find_col(df, ['rpm'])
speed_col   = find_col(df, ['speed'])
throttle_col = find_col(df, ['load', 'throttle'])

print("Columns found:")
print(f"  Time:     {time_col}")
print(f"  RPM:      {rpm_col}")
print(f"  Speed:    {speed_col}")
print(f"  Throttle: {throttle_col}")

# ── Print every row so we can SEE the pull with our own eyes ───────────────
print("\nFull data — watch for throttle jumping above 85%:\n")
print(f"{'Row':<5} {'Time':>8} {'RPM':>8} {'Speed':>8} {'Throttle%':>10}")
print("-" * 45)

for i, row in df.iterrows():
    t   = row[time_col]
    rpm = row[rpm_col]
    spd = row[speed_col]
    thr = row[throttle_col]

    # Add a marker so the pull jumps out visually
    marker = " <--- PULL" if thr >= 85 else ""
    print(f"{i:<5} {t:>8.1f} {rpm:>8.0f} {spd:>8.1f} {thr:>10.1f}{marker}")

# ── Now automatically detect the pull ─────────────────────────────────────
print("\n" + "=" * 50)
print("PULL DETECTION")
print("=" * 50)

THROTTLE_THRESHOLD = 85   # % — above this counts as "full throttle"
MIN_DURATION       = 3.0  # seconds — pull must last at least this long

in_pull     = False
pull_start  = None
pulls_found = []

for i, row in df.iterrows():
    thr  = row[throttle_col]
    time = row[time_col]

    if thr >= THROTTLE_THRESHOLD and spd > 5:
        if not in_pull:
            in_pull    = True
            pull_start = i
            pull_start_time = time
    else:
        if in_pull:
            duration = time - pull_start_time
            if duration >= MIN_DURATION:
                pulls_found.append({
                    'start_row': pull_start,
                    'end_row':   i - 1,
                    'start_time': pull_start_time,
                    'end_time':   time,
                    'duration':   duration
                })
            in_pull = False

# Print results
if pulls_found:
    print(f"\nFound {len(pulls_found)} pull(s):\n")
    for idx, pull in enumerate(pulls_found):
        start_rpm = df.loc[pull['start_row'], rpm_col]
        end_rpm   = df.loc[pull['end_row'],   rpm_col]
        seg = df.loc[pull['start_row']:pull['end_row']]
        max_spd = seg[speed_col].max()
        max_thr = seg[throttle_col].max()
        print(f"  Pull {idx + 1}:")
        print(f"    Rows:     {pull['start_row']} → {pull['end_row']}")
        print(f"    Time:     {pull['start_time']:.1f}s → {pull['end_time']:.1f}s")
        print(f"    Duration: {pull['duration']:.1f} seconds")
        print(f"    RPM:      {start_rpm:.0f} → {end_rpm:.0f}")
        print(f"    Max speed:{max_spd:.0f} MPH")
        print(f"    Max thr:  {max_thr:.0f}%")
else:
    print("\nNo pulls found. Try lowering THROTTLE_THRESHOLD.")