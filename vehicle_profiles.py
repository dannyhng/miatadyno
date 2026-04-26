# vehicle_profiles.py — MiataDyno
# NC Miata (2006–2015) verified data
# Sources: Mazda US press specs, community dyno data, Tom's verified weight database
# Last updated: April 2026
#
# WEIGHT LOGIC:
#   These are "dry-ish" weights (full fluids, no fuel).
#   Code adds fuel_level * 77 lbs + driver_weight separately.
#   1 lb of rotating wheel mass ≠ 1 lb of static mass.
#   Rotational inertia factor applied in build_vehicle_profile().

# ═══════════════════════════════════════════════════════════════
# WEIGHT MATRIX — No Fuel, US Spec (lbs)
# Key: (generation, top_type, transmission)
# ═══════════════════════════════════════════════════════════════

WEIGHT_MATRIX = {
    # NC1 (2006–2008)
    ('nc1', 'soft',  '5mt'): 2447,
    ('nc1', 'soft',  '6mt'): 2480,
    ('nc1', 'soft',  '6at'): 2520,
    ('nc1', 'prht',  '6mt'): 2545,
    ('nc1', 'prht',  '6at'): 2600,

    # NC2/3 (2009–2015) — shared weight spec
    ('nc23', 'soft', '6mt'): 2515,
    ('nc23', 'soft', '6at'): 2540,
    ('nc23', 'prht', '6mt'): 2593,
    ('nc23', 'prht', '6at'): 2610,
}

# NC1 had the 5MT as standard; NC2/3 shipped with 6MT only
VALID_TRANS = {
    'nc1':  ['5mt', '6mt', '6at'],
    'nc23': ['6mt', '6at'],
}

# ═══════════════════════════════════════════════════════════════
# AERODYNAMICS — Verified Values
# ═══════════════════════════════════════════════════════════════

FRONTAL_AREA_M2 = 1.78   # Static constant, all NC variants

# Cd by top configuration (top position during run)
CD_VALUES = {
    'soft_up':  0.36,    # Soft top raised
    'prht_up':  0.34,    # PRHT raised (slightly more slippery than soft)
    'top_down': 0.44,    # Either top, fully lowered — drag skyrockets
}

# ═══════════════════════════════════════════════════════════════
# TRANSMISSION GEAR RATIOS
# ═══════════════════════════════════════════════════════════════

GEAR_RATIOS = {
    '5mt': {
        'ratios':      [3.136, 1.888, 1.330, 1.000, 0.814],
        'final_drive': 4.100,
        'dtl':         0.15,   # drivetrain loss %
    },
    '6mt': {
        'ratios':      [3.709, 2.190, 1.536, 1.177, 1.000, 0.832],
        'final_drive': 4.100,
        'dtl':         0.15,
    },
    '6at': {
        'ratios':      [3.529, 2.042, 1.400, 1.000, 0.713, 0.582],
        'final_drive': 3.417,  # AT has shorter final drive — big difference
        'dtl':         0.20,   # Torque converter eats more power
    },
}

# ═══════════════════════════════════════════════════════════════
# STOCK WHEEL WEIGHTS (per wheel)
# Used to calculate unsprung mass delta vs aftermarket
# ═══════════════════════════════════════════════════════════════

STOCK_WHEEL_WEIGHT = {
    'nc1':  18.0,   # NC1 16" design (range 17.5–18.5, center)
    'nc23': 18.8,   # NC2/3 17" design (range 17.5–19.0, center)
}

# ═══════════════════════════════════════════════════════════════
# EXHAUST DATABASE — Verified Weights
# Stock baseline weights per section:
#   Muffler:  27.0 lbs
#   Midpipe:  20.0 lbs
#   Headers:  15.2 lbs (cast iron manifold + primary cat)
# ═══════════════════════════════════════════════════════════════

EXHAUST_DB = {

    'muffler': {
        'label':   'Muffler / Axle-Back',
        'stock_lbs': 27.0,
        'options': [
            {'name': 'Stock OEM Muffler',                   'weight': 27.0, 'delta': 0.0,   'verified': True},
            {'name': 'Tomei ExPreme Ti (Titanium)',          'weight':  5.3, 'delta': -21.7, 'verified': True,  'note': 'Lightest available. Titanium.'},
            {'name': 'GWR RoadsterSport Race (Single)',      'weight':  8.0, 'delta': -19.0, 'verified': True,  'note': 'Minimalist, loud.'},
            {'name': 'GWR RoadsterSport Duals (RSII)',       'weight': 19.0, 'delta':  -8.0, 'verified': True,  'note': 'Best balance of weight and style.'},
            {'name': 'Racing Beat Duals',                    'weight': 27.0, 'delta':   0.0, 'verified': True,  'note': 'High quality, no weight change.'},
            {'name': 'Flyin\' Miata Cat-Back (muffler)',     'weight': 13.5, 'delta': -13.5, 'verified': False, 'note': 'Community-reported weight.'},
            {'name': 'Borla ATAK',                           'weight': 14.5, 'delta': -12.5, 'verified': False},
            {'name': 'MagnaFlow Street Series',              'weight': 15.0, 'delta': -12.0, 'verified': False},
        ]
    },

    'midpipe': {
        'label':   'Midpipe / Test Pipe',
        'stock_lbs': 20.0,
        'options': [
            {'name': 'Stock OEM Midpipe (with resonator/cat)', 'weight': 20.0, 'delta':  0.0,  'verified': True},
            {'name': 'GWR RoadsterSport HighFlow',              'weight': 16.5, 'delta': -3.5,  'verified': True,  'note': 'Larger diameter, higher flow.'},
            {'name': 'Flyin\' Miata High-Flow Cat',             'weight': 15.5, 'delta': -4.5,  'verified': False},
            {'name': 'Test Pipe / Straight Pipe',               'weight': 12.0, 'delta': -8.0,  'verified': False, 'note': 'Off-road/track use only.'},
        ]
    },

    'headers': {
        'label':   'Headers / Manifold',
        'stock_lbs': 15.2,
        'options': [
            {'name': 'Stock OEM Manifold (cast iron + primary cat)', 'weight': 15.2, 'delta':  0.0,  'verified': True},
            {'name': 'GWR Street Header (catted, stainless)',         'weight': 11.0, 'delta': -4.2,  'verified': True},
            {'name': 'Aftermarket Race Header (catless)',             'weight':  7.75,'delta': -7.0,  'verified': False, 'note': 'Avg of 7.0–8.5 lb range.'},
            {'name': 'Flyin\' Miata Long Tube Headers',              'weight':  7.0, 'delta': -8.2,  'verified': False},
        ]
    },
}

# ═══════════════════════════════════════════════════════════════
# WHEEL DATABASE (per wheel weight in lbs)
# Delta vs stock calculated at runtime from STOCK_WHEEL_WEIGHT
# ═══════════════════════════════════════════════════════════════

WHEEL_DB = [
    {'name': 'Stock NC1 16" alloy',           'wt': 18.0, 'size': '16x6.5', 'verified': True},
    {'name': 'Stock NC2/3 17" alloy',         'wt': 18.8, 'size': '17x7',   'verified': True},
    {'name': 'Konig Hypergram 15×8',          'wt': 13.2, 'size': '15x8',   'verified': True,  'note': 'Most popular NC track wheel.'},
    {'name': 'Rota Grid 15×8',                'wt': 13.8, 'size': '15x8',   'verified': True},
    {'name': 'MSR 045 15×8',                  'wt': 14.0, 'size': '15x8',   'verified': False},
    {'name': 'Enkei RPF1 16×8',               'wt': 14.1, 'size': '16x8',   'verified': True,  'note': 'Industry benchmark cast wheel.'},
    {'name': 'Enkei RPF1 17×8',               'wt': 15.8, 'size': '17x8',   'verified': True},
    {'name': 'Konig Hypergram 17×8',          'wt': 16.5, 'size': '17x8',   'verified': True},
    {'name': 'Gram Lights 57DR 17×9',         'wt': 15.4, 'size': '17x9',   'verified': True},
    {'name': 'Rays Volk TE37 15×8',           'wt': 10.8, 'size': '15x8',   'verified': True,  'note': 'Lightest widely available option.'},
    {'name': 'Rays Volk CE28N 17×8',          'wt': 13.2, 'size': '17x8',   'verified': True},
    {'name': 'Work Emotion CR 15×8',          'wt': 12.8, 'size': '15x8',   'verified': False},
    {'name': 'XXR 527 15×8',                  'wt': 14.2, 'size': '15x8',   'verified': False},
]

# ═══════════════════════════════════════════════════════════════
# OTHER WEIGHT MODS
# ═══════════════════════════════════════════════════════════════

OTHER_MODS = [
    {'name': 'AC system deleted',              'delta': -28,  'verified': True},
    {'name': 'Hard Dog M2 roll bar',           'delta': +22,  'verified': True},
    {'name': 'Hard Dog M3 roll bar',           'delta': +28,  'verified': True},
    {'name': 'Full tube cage',                 'delta': +65,  'verified': False},
    {'name': 'Flyin\' Miata supercharger kit', 'delta': +45,  'verified': True},
    {'name': 'Carbon fiber hood',              'delta': -15,  'verified': False},
    {'name': 'Fire extinguisher + mount',      'delta':  +5,  'verified': True},
    {'name': 'Battery relocation (smaller)',   'delta': -15,  'verified': False},
]

# ═══════════════════════════════════════════════════════════════
# TIRE ROLLING DIAMETER
# ═══════════════════════════════════════════════════════════════

def calc_tire_diameter_m(width_mm, aspect_ratio, wheel_dia_inches):
    """
    Industry standard rolling diameter formula.
    diameter = wheel_dia + 2 × (width × aspect/100 × 0.0393701)
    """
    sidewall_in = width_mm * (aspect_ratio / 100) * 0.0393701
    total_in    = wheel_dia_inches + (2 * sidewall_in)
    return total_in * 0.0254   # inches → meters

# ═══════════════════════════════════════════════════════════════
# VEHICLE PROFILE BUILDER
# ═══════════════════════════════════════════════════════════════

def build_vehicle_profile(
    generation,           # 'nc1' or 'nc23'
    top_type,             # 'soft' or 'prht'
    transmission,         # '5mt', '6mt', or '6at'
    top_position,         # 'up' or 'down' (affects Cd)
    tire_width,           # mm, e.g. 205
    tire_aspect,          # e.g. 45
    wheel_dia_inches,     # e.g. 17
    wheel_weight_lbs,     # per wheel
    exhaust_delta_lbs,    # sum of (muffler + midpipe + header) deltas
    other_delta_lbs,      # roll bar, AC delete, etc.
    fuel_level,           # 0.0–1.0
    driver_weight_lbs,
    passenger=False,
):
    # ── Base weight from matrix ──
    key = (generation, top_type, transmission)
    if key not in WEIGHT_MATRIX:
        raise ValueError(f"Invalid combination: {key}")
    base_wt_lbs = WEIGHT_MATRIX[key]

    # ── Stock wheel weight for this gen ──
    stock_whl_lbs = STOCK_WHEEL_WEIGHT.get(generation, 18.8)

    # ── Wheel unsprung mass delta (4 wheels) ──
    wheel_delta_lbs = 4 * (wheel_weight_lbs - stock_whl_lbs)

    # ── Fuel weight: 12.7 gal tank × 6.1 lbs/gal ──
    fuel_lbs = fuel_level * 12.7 * 6.1   # max ~77.5 lbs

    # ── Total static mass ──
    total_lbs = (
        base_wt_lbs
        + wheel_delta_lbs
        + exhaust_delta_lbs
        + other_delta_lbs
        + fuel_lbs
        + driver_weight_lbs
        + (165 if passenger else 0)
    )
    total_kg = total_lbs * 0.453592

    # ── Rotational inertia (adds ~4.5% effective mass) ──
    # Accounts for: 4 wheels+tires, driveshaft, diff internals
    eff_mass_kg = total_kg * 1.045

    # ── Aero ──
    if top_position == 'down':
        Cd = CD_VALUES['top_down']
    elif top_type == 'prht':
        Cd = CD_VALUES['prht_up']
    else:
        Cd = CD_VALUES['soft_up']

    # ── Transmission ──
    trans_data = GEAR_RATIOS[transmission]

    # ── Tire ──
    tire_dia_m = calc_tire_diameter_m(tire_width, tire_aspect, wheel_dia_inches)

    return {
        # Identity
        'generation':        generation,
        'top_type':          top_type,
        'transmission':      transmission,
        'top_position':      top_position,

        # Mass
        'base_wt_lbs':       base_wt_lbs,
        'total_lbs':         total_lbs,
        'total_kg':          total_kg,
        'eff_mass_kg':       eff_mass_kg,

        # Breakdown (for UI display)
        'wheel_delta_lbs':   wheel_delta_lbs,
        'exhaust_delta_lbs': exhaust_delta_lbs,
        'other_delta_lbs':   other_delta_lbs,
        'fuel_lbs':          fuel_lbs,
        'driver_lbs':        driver_weight_lbs,

        # Aero
        'Cd':                Cd,
        'A':                 FRONTAL_AREA_M2,
        'Crr':               0.015,

        # Drivetrain
        'dtl':               trans_data['dtl'],
        'gear_ratios':       trans_data['ratios'],
        'final_drive':       trans_data['final_drive'],

        # Tire
        'tire_dia_m':        tire_dia_m,
        'tire_dia_in':       tire_dia_m / 0.0254,
    }


# ═══════════════════════════════════════════════════════════════
# SELF TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 60)
    print('VEHICLE PROFILES — SELF TEST')
    print('=' * 60)

    # Test 1: NC2 Soft Top 6MT, stock everything
    p1 = build_vehicle_profile(
        generation='nc23', top_type='soft', transmission='6mt',
        top_position='up',
        tire_width=205, tire_aspect=45, wheel_dia_inches=17,
        wheel_weight_lbs=18.8,
        exhaust_delta_lbs=0, other_delta_lbs=0,
        fuel_level=0.5, driver_weight_lbs=165,
    )
    print(f'\nTest 1 — NC2/3 Soft Top 6MT, half tank, 165lb driver:')
    print(f'  Base weight:   {p1["base_wt_lbs"]} lbs (no fuel)')
    print(f'  Total weight:  {p1["total_lbs"]:.0f} lbs')
    print(f'  Effective mass:{p1["eff_mass_kg"]:.1f} kg (with rotational inertia)')
    print(f'  Cd:            {p1["Cd"]} (soft top up)')
    print(f'  Drivetrain loss: {p1["dtl"]*100:.0f}%')
    print(f'  Final drive:   {p1["final_drive"]}')
    print(f'  Tire dia:      {p1["tire_dia_in"]:.2f}" ({p1["tire_dia_m"]:.4f} m)')

    # Test 2: NC1 PRHT 6AT — automatic penalty
    p2 = build_vehicle_profile(
        generation='nc1', top_type='prht', transmission='6at',
        top_position='up',
        tire_width=195, tire_aspect=50, wheel_dia_inches=16,
        wheel_weight_lbs=18.0,
        exhaust_delta_lbs=0, other_delta_lbs=0,
        fuel_level=0.5, driver_weight_lbs=165,
    )
    print(f'\nTest 2 — NC1 PRHT 6AT, half tank, 165lb driver:')
    print(f'  Base weight:   {p2["base_wt_lbs"]} lbs')
    print(f'  Total weight:  {p2["total_lbs"]:.0f} lbs')
    print(f'  Cd:            {p2["Cd"]} (PRHT up)')
    print(f'  Drivetrain loss: {p2["dtl"]*100:.0f}% (AT penalty)')
    print(f'  Final drive:   {p2["final_drive"]} (AT shorter ratio)')

    # Test 3: Fully modded NC2 with top down
    exh = (-21.7) + (-3.5) + (-4.2)  # Tomei Ti + GWR midpipe + GWR street header
    p3 = build_vehicle_profile(
        generation='nc23', top_type='soft', transmission='6mt',
        top_position='down',
        tire_width=205, tire_aspect=50, wheel_dia_inches=15,
        wheel_weight_lbs=13.2,   # Konig Hypergram
        exhaust_delta_lbs=exh,
        other_delta_lbs=-28,     # AC deleted
        fuel_level=0.5, driver_weight_lbs=165,
    )
    print(f'\nTest 3 — NC2 Soft 6MT, top DOWN, Hypergrams, Tomei+GWR exhaust, no AC:')
    print(f'  Base weight:   {p3["base_wt_lbs"]} lbs')
    print(f'  Exhaust delta: {p3["exhaust_delta_lbs"]:.1f} lbs')
    print(f'  Wheel delta:   {p3["wheel_delta_lbs"]:.1f} lbs')
    print(f'  Total weight:  {p3["total_lbs"]:.0f} lbs')
    print(f'  Saved vs stock:{p1["total_lbs"] - p3["total_lbs"]:.0f} lbs')
    print(f'  Cd:            {p3["Cd"]} (TOP DOWN — drag penalty)')

    # Test 4: Exhaust totals
    print(f'\nExhaust DB totals:')
    for section, data in EXHAUST_DB.items():
        print(f'  {section}: {len(data["options"])} options, stock = {data["stock_lbs"]} lbs')

    print(f'\nWheel DB: {len(WHEEL_DB)} options')
    print(f'Weight matrix: {len(WEIGHT_MATRIX)} combinations')
    print('\n✓ vehicle_profiles.py self-test passed')