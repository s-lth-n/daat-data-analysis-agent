# Login Page — UI/UX Theory Mapping (v16 / v17)
**Theme:** Glass on Powder Blue (light) · Glass on Night Chalk + Oat Foam (dark)
**Palette sources:**
- Light mode — @everlin.designs: Dark Cocoa `#583722` + Powder Blue `#BDD7DE`
- Dark mode — Oat Foam `#F4EDE4` + Night Chalk `#212121`
**Cross-mode accent:** Powder Blue `#BDD7DE` (focus ring + badge dot)
**Deployment:** Local self-hosted (single admin)

---

## Sources (your folder verbatim)

| Code | File |
|------|------|
| **G** | *101 UX Principles* — Will Grant (Packt, 2018) |
| **K** | *Don't Make Me Think, Revisited* — Steve Krug (2013) |
| **M** | *UX for Beginners* — Joel Marsh (O'Reilly, 2016) |
| **N** | *UX Research* — Brad Nunnally & David Farkas (O'Reilly, 2016) |
| **P1** | Yudhanto et al. — *Design Thinking on Company Profile Web* (IEEE APICS 2022) |
| **P2** | Ruiz et al. — *FENIkS — Learning UI Functional Design Through Simulation* (IEEE TLT 2020) |
| **P3** | Gunawan et al. — *Effect of UI Design on UX in E-Commerce* (IEEE CONMEDIA 2021) |
| **MS** | Your `UIUX_Master_Summary.pdf` |

---

## Why this version

The v15 critique cleaned up redundant text (no *"Welcome back"*, no tagline) and balanced hierarchy. v16/v17 keeps those wins and **restores** what worked in v14 — glassmorphism + Powder Blue palette + decorative bg text — because:

> **MS hal.19** explicitly names *"pilihan glassmorphism"* as your chosen design direction. The contrast warning in **MS hal.4** is scoped to *dark* glass; both modes here keep on-glass text ≥7:1 AAA.

Two specific upgrades:
- **Stacked bg text** *"DATA ANALYST"* / *"AGENT"* (atas-bawah) — bigger visual identity without competing with the card
- **Dark mode amplified** — opacity bumped 4.5% → 12% so the bg type is *visible* on Night Chalk

---

## What changed v15 → v16

| Change | Theory citation |
|---|---|
| Restored Powder Blue gradient as the page bg | **MS hal.19** glass is the chosen direction; **N** aesthetic-usability — colored canvas + glass = the look you wanted |
| Restored glassmorphism on login card, sidebar, chat input | **MS hal.19** — `backdrop-filter: blur(24px)` + 62% white frost |
| Bg text stacked: *"DATA ANALYST"* / *"AGENT"* | **G Bab 64** decoration ≠ sole meaning channel; **K Bab 3 hal.31-35** hierarchy of attention; **N** brand identity as texture |
| Dark mode bg text opacity 4.5% → 12% | Earlier dark glass was "barely readable" — boosting opacity within the **G Bab 59** decoration tier (still <2:1 — never reads as content) |
| Brand monogram 32 → 48 px | **G Bab 4** size+weight hierarchy; the CTA still wins because it's full-width 50px |
| Brand name in CSS title 22 → 26 px | **G Bab 4** Tier 1 |
| Single-line badge with animated PB dot | **G Bab 20** orient new admin; **G Bab 89** human voice; **P3** trust signal; **G Bab 40** dot is a small status indicator (micro-animation exception) |

## What changed v16 → v17 (this revision)

| Change | Theory citation |
|---|---|
| **Dark mode palette swap to Oat Foam + Night Chalk** | **N** aesthetic-usability — warm cream on near-black is calmer than cocoa-on-cocoa, easier to look at; **G Bab 59** base ratio 13.86:1 AAA |
| Light mode untouched — PB gradient + cocoa + glass card | Per your instruction, only dark mode changes |
| Powder Blue stays as cross-mode accent | **G Bab 64** color reinforces meaning consistently across modes; users learn that PB = focus / status |

---

## Element-by-element mapping (strict citations)

| # | Element | Decision | CSS rule | Theory + page |
|---|---------|----------|----------|---------------|
| 1 | **Page bg (light)** — Powder Blue gradient | Brand-anchored canvas; glass card sits above it | `--page-bg` light | **MS hal.19**; **N** aesthetic-usability |
| 2 | **Page bg (dark)** — Night Chalk gradient `#212121 → #1A1A1A → #212121` | Calm true-dark canvas; reduces eye strain | `--page-bg` dark | **N**; user feedback that dark cocoa-on-cocoa was "kinda dull" |
| 3 | **Stacked bg text "DATA ANALYST / AGENT"** — `clamp(90px,15vw,220px)` weight 900, two-line via `\A` + `white-space: pre`, blur 1.5px, embossed shadows | Brand identity as texture; glass card frosts the center | `#auth-page::before` | **G Bab 64** decoration ≠ content; **K Bab 3 hal.31-35** hierarchy of attention; **G Bab 40** static |
| 4 | **Bg text opacity** — light 7.5%, dark 12% | Light mode subtler; dark amplified per your "make it pop" feedback | `--emboss-color` per mode | **G Bab 59** still <2:1, never reads as content |
| 5 | **Background blobs** — cocoa-soft + cocoa, blurred, static | Ambient warmth | `body::before / ::after` | **G Bab 60** subtle depth; **G Bab 40** no animation |
| 6 | **Login card — glassmorphism** — `rgba(255,255,255,0.62)` light / `rgba(42,42,42,0.72)` dark · `backdrop-filter: saturate(180%) blur(24px)` · 22px radius · soft shadow | Master Summary's chosen design direction | `div.sm\:max-w-md` | **MS hal.19**; **G Bab 59** post-blend ≥7:1 AAA in both modes; **G Bab 60** border + shadow affordance; **P3** polish → trust |
| 7 | **Card entrance** — single 0.5s fade+rise | One-shot; no ongoing motion | `@keyframes card-enter` | **G Bab 40** allows micro-animation that doesn't shift element positions |
| 8 | **Brand monogram "DA"** — 48×48 cocoa (light) / Oat Foam (dark) tile · white "DA" (light) / Night Chalk "DA" (dark) · 12px radius · 18px / 800 | Visual anchor at Tier 1 | `.brand-mono` (mockup) | **G Bab 4** size hierarchy; **G Bab 7** tappable affordance; **G Bab 69** ≥44px target; **G Bab 59** 12.36 / 13.86:1 AAA |
| 9 | **Title "Data Analyst Agent"** — 26px / 700, solid `--text` | Tier 1 — sole heading after monogram | `div.mb-1 > div.text-2xl.font-medium::before` | **G Bab 4** size hierarchy; **G Bab 2-3** system stack; **G Bab 89** human voice; **G Bab 59** AAA |
| 10 | **Subtitle "Sign in to continue"** — 14px / 400, `--text2` | Tells user what to do | `...::after` | **K Bab 5 hal.45-46** hapus happy talk; **G Bab 4** Tier 3 |
| 11 | **Field labels** — "Username", "Password" — 14px / 500, `--text2` | Always visible, never replaced by placeholder | `label` | **G Bab 67** persistent labels |
| 12 | **Inputs** — 48px tall, 16px font, `backdrop-filter: blur(8px)`, 12px radius | Glass like the card; clearly affordant | `input[type=…]` | **G Bab 5** 16px (also iOS no-zoom); **G Bab 38** never clear data; **G Bab 60** visible border; **G Bab 69** 48px ≥44px |
| 13 | **Input focus** — cocoa border (or oat in dark) + 3px Powder Blue glow + bg lifts to 85% opaque | First place PB earns its accent role | `input:focus` | **G Bab 45** validate ASAP; **P2 FENIkS** umpan balik visual layer; **G Bab 64** color + border-change reinforce |
| 14 | **Placeholder** — light `--text3 #806647` (4.62:1 AA) / dark `#9A9085` (4.58:1 AA), opacity 1, roman | Hint without competing with typed text | `::placeholder` | **G Bab 67** placeholder ≠ label; **K Bab 3** muted metadata |
| 15 | **Sign-in button** — full-width cocoa (light) / Oat Foam (dark), 50px tall, white text (light) / Night Chalk text (dark), 12px radius, soft shadow | OBVIOUS-tier primary; visually heaviest element on the page | `button[type="submit"]` | **G Bab 7** looks like a button; **G Bab 8** sensible size; **G Bab 9** click feedback; **G Bab 69** 50px ≥44px; **Marsh Lesson 65 hal.143-144** Axis of Interaction; **Marsh Lesson 67 hal.148-149** distinct primary; **MS hal.6** OBVIOUS tier; **G Bab 59** 12.36 / 13.86:1 AAA |
| 16 | **Button hover** — bg → `--accent2`, deeper shadow | Color/depth shift, no positional jump | `:hover` | **G Bab 9**; **P2** feedback layer 2 |
| 17 | **Button active** — `translateY(1px)` + reduced shadow | Tactile press response | `:active` | **G Bab 9**; **P2** feedback layer 3 |
| 18 | **Button focus-visible** — Powder Blue 3px ring on top of normal shadow | Keyboard users get the same focus signal | `:focus-visible` | **G Bab 66** logical tab order; **G Bab 64** color reinforces |
| 19 | **Button disabled / loading** — bg `#c9bba8`, no shadow, copy → *"Signing in…"* | State communicated explicitly; spinner never runs forever | `:disabled` + JS swap | **G Bab 56** stop on error; **P2 FENIkS** explanatory feedback |
| 20 | **Local-mode badge** — single line, pill, pale PB bg + animated PB dot | PB earns accent appearance #2 — trust signal | `.local-badge` | **G Bab 20** orient new admin; **G Bab 89** human voice; **P3** trust signal |
| 21 | **Badge dot pulse** — 2.4s ease-in-out infinite, opacity 0.75↔1.0, scale 1↔1.18 | Small status indicator; doesn't shift any interactive element | `@keyframes badge-pulse` | **G Bab 40** micro-animation exception (signal "system is alive" per **P2**) |
| 22 | ~~Forgot password / OAuth / signup footer~~ | Removed | — | **K Bab 1 hal.11**; **G Bab 14**; **K Bab 3** |
| 23 | **Reduced-motion fallback** | All animations off if user prefers | `@media (prefers-reduced-motion: reduce)` | **G Bab 65** honor accessibility |

---

## Final contrast verification

### LIGHT — glass card on Powder Blue · blend ≈ `#e8eff1`

| Pair | Ratio | Grade |
|------|-------|-------|
| Title `--text` `#2A1810` | **14.59:1** | AAA |
| Subtitle `--text2` `#6B4630` | **7.09:1** | AAA |
| Label `--text2` | **7.09:1** | AAA |
| Placeholder `--text3` `#806647` | **4.62:1** | AA |
| Brand mono: white on cocoa-deep | **12.36:1** | AAA |
| Sign-in: white on cocoa-deep | **12.36:1** | AAA |

### DARK — Night Chalk + Oat Foam · glass blend ≈ `#2A2A2A`

| Pair | Ratio | Grade |
|------|-------|-------|
| Title `--text` `#F4EDE4` | **12.36:1** | AAA |
| Subtitle `--text2` `#D9D0C4` | **9.41:1** | AAA |
| Placeholder `--text3` `#9A9085` | **4.58:1** | AA |
| Brand mono: Night on Oat | **13.86:1** | AAA |
| Sign-in: Night on Oat | **13.86:1** | AAA |

Every element is **AAA** except placeholders (intentionally muted per **Krug Bab 3**), which sit at **AA**.

The **embossed background text** stays under 2:1 in both modes — *intentionally* unreadable per **Grant Bab 64** (texture, not content).

---

## Quick-reference cross-check

| Your priority | Where on login |
|---|---|
| 🔴 16px body / 1.5 line-height (G Bab 5) | inputs, prose, body |
| 🔴 ≥44px tap targets (G Bab 69) | inputs 48px, button 50px, monogram 48px |
| 🔴 Persistent labels (G Bab 67) | "Username", "Password" — 14px / 500 |
| 🔴 Contrast ≥ 4.1:1 (G Bab 59) | every text element ≥AA, all interactive AAA |
| 🟡 Blank slate guidance (G Bab 20) | local-mode badge orients first-time admin |
| 🟡 Write like a human (G Bab 89) | "Sign in to continue", *"Running locally · your data stays on this machine"* |
| 🟢 System font stack (G Bab 3) | no `@import`, no Fraunces |
| 🟢 Don't confound expectations (G Bab 93) | centered card, button below fields |

---

## Files in this delivery

1. `custom.css` — drop into Open WebUI → Admin Settings → Interface → Custom CSS
2. `login_mockup.html` — open in browser; uses `custom.css` for live preview / thesis screenshots
3. `login_theory_mapping.md` — this file (paste into UI/UX chapter of the Tugas Akhir)
