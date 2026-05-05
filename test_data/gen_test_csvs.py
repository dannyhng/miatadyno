"""Generate synthetic CSVs for validation plan items #2, #3, #4."""
import math
import os

OUT = os.path.dirname(os.path.abspath(__file__))


def write_csv(path, header, rows):
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")


def gen_pull(t0, dt, rpm_start, rpm_end, mph_start, mph_end, n, throttle=95):
    """Yield a list of (time, rpm, mph, throttle) for a synthetic WOT pull."""
    out = []
    for i in range(n):
        f = i / max(1, n - 1)
        rpm = rpm_start + (rpm_end - rpm_start) * f
        mph = mph_start + (mph_end - mph_start) * f
        out.append((round(t0 + i * dt, 2), round(rpm, 0), round(mph, 1), throttle))
    return out


def gen_cruise(t0, dt, rpm, mph, n, throttle=20):
    return [(round(t0 + i * dt, 2), rpm, mph, throttle) for i in range(n)]


# ---------------------------------------------------------------
# Test #3: km/h CSV with file peak ~140 km/h (≈87 mph)
# Should detect as km/h via fileMaxRaw > 130 → speedConv = 0.621371.
# Header has no "km/h" tag so detection falls to the file-peak heuristic.
# ---------------------------------------------------------------
hdr = ["Time(s)", "Engine RPM", "Vehicle Speed", "Absolute Throttle Position(%)", "Intake Air Temperature(C)"]
rows = []
# warm-up cruise
rows += [(t, r, s, th, 25) for (t, r, s, th) in gen_cruise(0, 0.5, 1500, 50, 20)]
# pull from 50→140 km/h, 2500→7000 rpm
pull = gen_pull(10, 0.2, 2500, 7000, 50, 140, 25)
rows += [(t, r, s, th, 25) for (t, r, s, th) in pull]
# coast back down
rows += [(round(15 + i * 0.5, 2), 1800, 100, 20, 26) for i in range(15)]
write_csv(os.path.join(OUT, "synth_kph.csv"), hdr, rows)

# ---------------------------------------------------------------
# Test #4: FI/MAP-only CSV — has MAP, no baro. MAP at WOT will be high
# (post-throttle, ~95–100 kPa for NA, but we'll plant boost-like values
# 150–180 kPa as if it were a turbo log).
# After parse: baro = median of WOT MAP ≈ 165 kPa → caught by Fix #3
# (out of 80–105 range) → defaulted to 99.9 kPa with 'out-of-range' note.
# Then with FI selected at analysis time, MAP-FI override fires and shows
# the atmospheric warning banner.
# ---------------------------------------------------------------
hdr = ["Time(s)", "Engine RPM", "Vehicle Speed(mph)", "Absolute Throttle Position(%)", "Intake Air Temperature(C)", "Manifold Absolute Pressure(kPa)"]
rows = []
rows += [(t, 1500, 30, 20, 35, 40) for (t, _, _, _) in gen_cruise(0, 0.5, 1500, 30, 20)]
# WOT pull with boost — MAP climbs to ~170 kPa
for i, (t, r, s, th) in enumerate(gen_pull(10, 0.2, 2500, 7000, 30, 90, 25)):
    f = i / 24.0
    map_val = 100 + 70 * f  # 100 → 170 kPa
    rows.append((t, r, s, th, 38, round(map_val, 1)))
rows += [(round(15 + i * 0.5, 2), 1800, 60, 20, 38, 50) for i in range(15)]
write_csv(os.path.join(OUT, "synth_fi_map.csv"), hdr, rows)

# ---------------------------------------------------------------
# Test #2: multi-pull heat-soak. Pull 1 cool (30°C IAT), Pull 5 hot (75°C).
# Pull 1 was correctly under-corrected with file-mean before fix; now with
# per-pull IAT, each pull gets ITS OWN correction.
# ---------------------------------------------------------------
# Three variants of the heat-soak file to exercise the three IAT-detection
# branches in detectPulls (post-P1 fix):
#   (a) °F header  → tempUnit='fahrenheit' branch (control)
#   (b) °C header  → tempUnit='celsius' branch (P1 bug repro)
#   (c) no tag     → null tempUnit, falls into the >60 heuristic (still buggy
#                    on heat-soaked Celsius without a header — documented)
def write_heatsoak(filename, header_iat_label, iats):
    hdr = [
        "Time(s)", "Engine RPM", "Vehicle Speed(mph)",
        "Absolute Throttle Position(%)", header_iat_label,
        "Barometric Pressure(kPa)",
    ]
    rows = []
    t = 0.0
    for iat in iats:
        for i in range(10):
            rows.append((round(t, 2), 1500, 30, 20, iat, 99.5))
            t += 0.5
        for (pt, pr, ps, pth) in gen_pull(t, 0.2, 2500, 7000, 30, 90, 25):
            rows.append((round(pt, 2), pr, ps, pth, iat, 99.5))
        t += 25 * 0.2
        for i in range(10):
            rows.append((round(t, 2), 1800, 60, 20, iat, 99.5))
            t += 0.5
    write_csv(os.path.join(OUT, filename), hdr, rows)

# (a) °F header: 30, 45, 55, 65, 75 °C → 86, 113, 131, 149, 167 °F
write_heatsoak("synth_heatsoak.csv", "Intake Air Temperature(F)", [86, 113, 131, 149, 167])

# (b) °C header — P1 bug repro: in pre-fix code, pulls 4 and 5 (65/75°C)
# get heuristic-treated as °F and become 18.3/23.9°C → heat-soak banner
# fails to fire. Post-fix: tempUnit='celsius' → values used as-is.
write_heatsoak("synth_heatsoak_celsius.csv", "Intake Air Temperature(C)", [30, 45, 55, 65, 75])

# (c) no unit tag — heuristic fallback path. Same Celsius values as (b),
# but the header has no °C/°F marker. detectUnit returns null → tempUnit
# is null → detectPulls falls into the >60 branch. Result is buggy by
# design (same as pre-P1-fix behavior on (b)) — this test is regression
# protection: if someone "fixes" the heuristic and breaks something else,
# this case will catch it.
write_heatsoak("synth_heatsoak_notagged.csv", "Intake Air Temperature", [30, 45, 55, 65, 75])

print("Wrote:")
for f in ("synth_kph.csv", "synth_fi_map.csv",
          "synth_heatsoak.csv", "synth_heatsoak_celsius.csv", "synth_heatsoak_notagged.csv"):
    p = os.path.join(OUT, f)
    print(f"  {p}  ({os.path.getsize(p)} bytes)")
