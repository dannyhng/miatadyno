# MiataDyno — Project Master Document
### Version 2.0 | Updated: April 28, 2026
### Purpose: Authoritative project state. Paste into a new chat to continue exactly where we left off.

---

## HOW TO USE THIS DOCUMENT IN A NEW CHAT

Paste this entire document at the start of a new conversation and say:
> "This is my complete project documentation. Read it fully, then help me continue from [WHERE YOU LEFT OFF]."

This is the single source of truth. If anything in this document conflicts with older notes, this document wins.

---

## SECTION 1: FOUNDER

**Name:** Danny Hoang (dannyhng on GitHub)
**Location:** Portland, OR
**Background:** Aspiring Network Engineer / IT Support Volunteer
**Certifications:** CCNA, CompTIA Security+, A+
**Stack experience:** Cisco IOS, pfSense, Proxmox, Docker, JavaScript (Astro), Python, GitHub
**Automotive:** VersaTuner, Autel scanner, DIY maintenance
**Car:** 2011 Mazda MX-5 NC2 PRHT (hard top — NOT soft top), 6MT
**Active mods:**
- 16x8 wheels at 12 lbs each
- Continental PureContact 205/55R16 tires (~19.4 lbs each)
- Race single muffler (-12 lbs vs stock)

**Style:** "Boring design is good design" — OEM+, clean, functional
**Communication preference:** Technically precise, no fluff, code/CLI examples
**Workflow:** Edit locally → git add → git commit → git push origin main
**Goal:** Lean, bootstrapped, solo execution. Ultimate goal is monetization, not hobby project.

---

## SECTION 2: PRODUCT — CURRENT STATE

### Live URLs
- Site: `https://dannyhng.github.io/miatadyno/`
- Repo: `https://github.com/dannyhng/miatadyno`
- Local working directory: `C:\Users\User\Desktop\miatadyno\`

### What It Does
A web app that:
1. Accepts a CSV log file from any OBD scanner (BlueDriver, OBD Fusion, Torque Pro)
2. Auto-detects file encoding (UTF-8 or UTF-16)
3. Detects full-throttle pulls in the data
4. Scores pull quality (0-100) before showing results
5. Calculates wheel horsepower and torque using road load physics
6. Applies SAE J1349 atmospheric correction (with optional weather API)
7. Detects multiple pulls, allows before/after comparison
8. Shows a power curve with stock reference band overlay
9. Generates a shareable result card (PNG download)
10. Provides AI-style interpretation comparing result to stock baseline

### Tagline
"Did your mod actually do anything?"

### Positioning (locked after community feedback)
**NOT:** "Cheap dyno alternative"
**IS:** "Data-driven tuning & diagnostics tool for NC Miata enthusiasts"

The accuracy positioning that should be on the landing page:
> This measures the difference between two runs on the same road in the same conditions. The delta (before vs after) is reliable. The absolute number is an estimate. Use it to answer "did my mod work and by how much," not "what does my car make."

---

## SECTION 3: VALIDATION STATUS

### Real Data Test (April 28, 2026)
Three full WOT pulls captured solo (no passenger), 13°C ambient, ideal cool dense air conditions.

**Vehicle:** NC2 PRHT, 16x8 wheels (12 lbs), 205/55R16 Continental PureContact, race muffler
**Total weight:** 2,763 lbs (car + half tank fuel + 170 lb driver)
**Tire diameter correction:** ×1.0264 (205/55R16 is 2.64% larger than stock 205/45R17)
**SAE correction factor:** 0.9568 (cooler/denser than standard atmosphere)

**Results:**
- Pull 1: 147.4 WHP — **rejected** (Savitzky-Golay edge effect on 9-point segment, monotonic rise unrealistic)
- Pull 2: 127.8 WHP @ 5,750 RPM — clean data, full RPM range
- Pull 3: 125.6 WHP @ 5,750 RPM — clean data, agrees with Pull 2

**Validated result:** ~126 WHP @ 5,750 RPM
**Stock NC2/3 PRHT reference:** 118-128 WHP (Dynojet)
**Delta vs stock midpoint:** +3 WHP (consistent with lighter rotational mass + race muffler)

**Speed traps (most trustworthy metric):**
- 30-50 MPH: Pull 2 = 3.70s, Pull 3 = 3.29s
- 40-60 MPH: Pull 2 = 3.70s, Pull 3 = 3.29s
- 50-70 MPH: Pull 2 = 3.82s, Pull 3 = 3.38s

**Conclusion:** The physics engine works correctly on real data. Numbers are physically plausible and within expected range for the build.

---

## SECTION 4: CURRENT TECHNICAL STATE

### Files In Repo
- `index.html` — Web app, deployed to GitHub Pages
- `calculate_hp.py` — v2.3 reference Python implementation (multi-run averaging, weather API, speed traps)
- `vehicle_profiles.py` — Single source of truth for NC vehicle data
- `detect_pull.py` — Standalone pull detection script
- `real_log.csv` — Validated WOT pull data (April 28, 2026)
- `MIATADYNO_MASTER_DOC.md` — This file

### Physics Implementation Status

**Validated and locked:**
- Road load equation: F_total = F_accel + F_rolling + F_aero + F_grade
- Block 4 fix applied: F_aero uses RHO_STD = 1.225, NOT actual density
- SAE J1349 correction handles all atmospheric normalization
- Multi-run averaging on common RPM grid (interpolation, not naive mean)
- Outlier rejection at ±5 WHP from group median
- Quality-weighted averaging (95-quality pull > 60-quality pull)
- Run-to-run std as primary uncertainty metric (not within-bin std)
- OBD jitter filter (>6 MPH delta in single 0.6s sample = bad row)
- Tire diameter speed correction for non-stock tires
- Heat-soak detection between pulls (8°C+ delta = warning)

**Vehicle profile constants (verified):**
```
NC1 (2006-2008): wt 2480 lbs, swl 15.0, stl 19.0, Cd 0.36 soft / 0.34 PRHT / 0.44 down
NC2 (2009-2012): wt 2509 lbs, swl 19.0, stl 18.0, Cd same as above
NC3 (2013-2015): wt 2509 lbs, swl 19.0, stl 18.0, Cd same as above
PRHT adds 78 lbs vs soft top base curb weight
Frontal area: 1.78 m² (all NC)
Drivetrain loss: 15% manual / 20% automatic
6MT final drive: 4.100 | 5MT: 4.300 | 6AT: 3.417
```

**Stock reference WHP ranges (Dynojet):**
- NC1: 113-123 WHP
- NC2/NC3: 118-128 WHP

### Web App UI Status

**Validated and working:**
- Two-path weight system: "I know it" (enter total) vs "Estimate it" (mod chooser)
- Dynamic wheel/tire database by rim size (15/16/17/18)
- Stock reference band overlay on power curve chart
- 5252 RPM annotation line + peak WHP label on chart
- Tooltip shows WHP/WTQ delta between before/after at any RPM
- Y-axis floor at 0 (prevents 2 WHP looking like a mountain)
- Quality scoring on detected pulls
- Terms acceptance modal before analysis
- Shareable result card with PNG download

**Known issue (fix at top of next session):**
The `setWeightMode` function doesn't run on initial page load. Fix: add `setWeightMode('know');` line right before `calcW();` in the initialization block. Without this, sections 04 and 05 are visible even when "I know it" is selected until the user toggles modes manually.

**Current UI structure (after redesign):**
1. Log File (upload)
2. Your Car (generation, top type, top position, driver weight) — universal
3. Wheels & Tires (always shown, affects speed reading)
4. Car Weight (the actual fork: I know it / Estimate it)
5. Exhaust — only shown in Estimate mode
6. Other Mods — only shown in Estimate mode
7. Mod Description
8. Run Analysis button

---

## SECTION 5: BUSINESS MODEL

### Pricing Strategy (3 tiers)

**Free**
- Single pull HP estimate
- Run quality score
- Atmospheric correction
- Speed trap timing
- Shareable result card
- Stock reference comparison
- Purpose: Marketing engine. Every shared card is an ad.

**One-time purchase: $12.99**
- Unlimited analyses
- 12 months of saved run history
- Before/after comparison with overlay
- Multi-run averaging across sessions
- Heat soak detection
- CSV export of power curve data
- Purpose: Anchors the subscription as the better value

**Pro subscription: $7.99/month or $49.99/year**
- Everything in one-time, permanently
- AI diagnostic interpretation (Claude API)
- Power health monitoring (alerts on power drop trends)
- Seasonal trend analysis
- VersaTuner log import (when built)
- Multiple car profiles
- Public leaderboard submission
- Priority Discord support
- Purpose: MRR engine. Recurring value through accumulated data and ongoing monitoring.

### Conversion Targets
- Conservative: 10% of active free users → paid
- 200 free users = 15 one-time + 5 Pro = $195 one-time + $40/mo MRR
- Break-even on infrastructure: 8 Pro subscribers ($61/mo costs)

### Year 1 Realistic
- 800 free users / 60 paid (35 one-time + 25 Pro)
- Year 1 revenue: ~$2,855 + ongoing MRR

### Year 2 With ND Expansion
- ND Miata support triples addressable market
- Target: 300 Pro subscribers = $2,397/mo MRR ($28,764/yr)
- Infrastructure scales to ~$150-200/mo
- Year 2 net profit estimate: ~$26,000

---

## SECTION 6: GO-TO-MARKET PLAN

### Pre-launch (right now)
- Status: Validated tool, real WOT pull on Danny's NC2 producing 126 WHP
- Action: Post to NC Miata Facebook group with screenshot of validated result
- Goal: 10 real users who upload their own pulls

### Month 1
- Reddit post on r/Miata (33k members)
- Demo video (90 seconds, screen record only)
- MiataNet NC subforum post
- Goal: 50 users

### Month 2
- Active feedback collection
- Two questions to ask every user:
  1. "What would make you pay for this?"
  2. "What feature would make you recommend this to another NC owner?"

### Month 3 (paid launch)
- FastAPI backend on Railway ($5/mo)
- Supabase free tier for auth + database
- Stripe integration
- Founding member offer: $9.99 one-time / $5.99/mo first 6 months
- Discord community with founding member badge
- Goal: 10 paying customers in first 2 weeks

### Month 4-6
- Add ND Miata support (doubles market, mostly profile updates)
- Launch VersaTuner CSV import beta
- Reach out to NC tuning shops for co-marketing

### Month 6+
- Public verified leaderboard
- Affiliate arrangements with mod shops (Racing Beat, Flyin' Miata, GoodWin)
- Power health monitoring email automation

---

## SECTION 7: TECHNICAL ROADMAP

### Priority order — do in this sequence

| # | Feature | Why | Effort |
|---|---------|-----|--------|
| 1 | Fix initial weight mode bug | Active visible bug | 5 min |
| 2 | Get 10 real users with real WOT pulls | Validation before features | external |
| 3 | FastAPI backend + Supabase + Stripe | Foundation for paid features | 2 weekends |
| 4 | User accounts + saved history | Retention foundation | 1 weekend |
| 5 | AI interpretation (Claude API) | Killer Pro feature | 1 evening |
| 6 | VersaTuner log import | Defensible moat | 1-2 weekends |
| 7 | ND Miata support | Triples market | 1 weekend |
| 8 | Community leaderboard | Viral retention | 2 weekends |
| 9 | Power health email automation | Highest-retention feature | 1 weekend |
| 10 | GPS grade correction | Accuracy refinement | 1 weekend |
| 11 | Mobile PWA polish | Nice to have | later |

### Tech stack decisions (locked)
- **Frontend:** HTML/CSS/JS on GitHub Pages (free) → Astro when complexity warrants
- **Backend (when needed):** FastAPI on Railway ($5/mo)
- **Database (when needed):** Supabase (free → $25/mo Pro)
- **Payments:** Stripe (2.9% + $0.30)
- **AI:** Claude Haiku 4.5 (~$0.0018 per interpretation)
- **Domain:** dannyhng.github.io/miatadyno (free) → custom domain at scale

---

## SECTION 8: COMPETITIVE LANDSCAPE

### Direct competitors
| Tool | Method | Price | Fatal flaw |
|------|--------|-------|-----------|
| Virtual Dyno (Brad Barnhill) | OBD CSV | Free | Windows only, 2009 UI, no mobile, no sharing |
| Virtual Dyno Mobile | OBD CSV | $5 app | 2.5/5 rating, "interface unclear", BT bugs |
| PerfExpert | Accelerometer | Paid | 6+ manual inputs, no OBD, no Miata profile |
| Log Dyno | OBD CSV | Paid | BMW-centric, broken reviews, no Mazda |
| Dragy | GPS hardware | $150+ device | No power estimate, just 0-60 / 1/4 mile |
| BlueDriver | Live OBD | Hardware | Diagnostics only, no performance analysis |

### Our differentiation
- Free entry, zero hardware
- Web-based, runs on phone or laptop
- NC Miata-specific intelligence (vehicle profiles, mod database)
- Before/after comparison as primary UX (not afterthought)
- Run quality scoring before showing numbers
- Stock reference comparison built-in
- Atmospheric correction with optional weather API
- Multi-run averaging with outlier rejection
- Speed trap timing as parallel output to HP estimate

### The actual moat
NC-Miata-specific domain knowledge. The physics engine is reproducible. The vehicle profiles, mod weight database, exhaust component database, and stock reference comparisons are not.

---

## SECTION 9: COMMUNITY FEEDBACK SUMMARY

### Validated insights from real Reddit/community posts
- **Speed trap timing valued more than HP estimates** (Petrol_Head72) — implemented as parallel output
- **Pivot from "dyno alternative" to "diagnostics + tuning assistant"** (lengthy critical reviewer) — accepted, repositioned
- **AI diagnostic layer is the killer feature** (same reviewer) — on roadmap as Pro tier feature
- **One-time vs subscription** — start with one-time, evolve to freemium with subscription endgame
- **Trust accuracy is biggest risk** — addressed with stock reference band, run quality scoring, conservative claims

### Rejected feedback
- Gemini's full V3.0 spec — Section 1 reverts the Block 4 aero fix (critical bug). Sections 3-5 already implemented. Don't refactor based on it.

---

## SECTION 10: ACTIVE BUGS AND TODOs

### Bugs to fix immediately
1. **`setWeightMode` doesn't run on page load** — add `setWeightMode('know');` before `calcW();` in initialization. Sections 04/05 visible in "I know it" mode until manually toggled.

### TODOs in priority order
1. Fix the initial state bug above
2. Push the WOT pull validation result to social (Facebook NC group)
3. Add 3-step progress indicator to top of content area
4. Add green/red visual feedback to upload zone on success/fail
5. Wait for first 10 external users before building anything else

---

## SECTION 11: KEY DATA & DECISIONS LOG

### Critical decisions made (do not revisit)
- Generic "OBD scanner" language, not BlueDriver-specific
- Solo runs only (no passenger encouraged in UI)
- 17" stock for NC2/3, 16" stock for NC1
- Tire diameter correction applied when non-stock tires entered
- F_aero uses RHO_STD (1.225), NOT actual density (Block 4 fix)
- SAE correction uses ambient temp, NOT IAT (per J1349)
- IAT used for heat-soak detection only
- 500 RPM bins for raw data, 250 RPM grid for averaging output
- ±5 WHP outlier rejection threshold
- Minimum 2 pulls for averaging to activate
- Stay on duplicate JS physics until paid tier launches (then migrate to FastAPI backend)

### Constants verified across sessions
- ρ_air standard: 1.225 kg/m³
- g: 9.81 m/s²
- Crr: 0.015 (street tires)
- Rotational inertia factor: 4.5%
- Half tank fuel: 12.7 gal × 0.5 × 6.1 lb/gal = 38.7 lbs

---

## SECTION 12: PROMPT FOR NEW CHAT

If starting a new Claude session, use this:

```
You are an expert technical co-founder helping me build MiataDyno — a web app
that analyzes OBD CSV files to generate virtual dyno results for NC Miata
(2006-2015) owners, showing before/after mod comparisons without a real dyno.

I have attached MIATADYNO_MASTER_DOC.md (this file). Read it fully.

Current status: [where you are]
Next step needed: [what you need help with]

Rules:
1. The physics engine is validated — do not propose architectural changes to it
2. F_aero uses RHO_STD (1.225), not actual density — this is the Block 4 fix
3. SAE correction uses ambient temp from weather API or 25°C default — NOT IAT
4. NC2/3 PRHT base weight is 2593 lbs (curb, no fuel); soft top is 2515 lbs
5. Stock NC2/3 reference range is 118-128 WHP on a Dynojet
6. Founder is developer-adjacent — explain code-level changes clearly
7. Workflow is: edit locally → git add → git commit → git push origin main
8. Ultimate goal is monetization, not hobby project
9. Don't suggest features until 10 real users have uploaded real pulls
10. Don't refactor working physics based on unverified AI feedback
```

---

*Document ends. Last updated: April 28, 2026.*
*Next update trigger: After paid tier launches OR after 10 real users upload pulls.*