---
name: Marvin
description: Signal Board — retro enamel, tan field and bright green signal
colors:
  ink: "#1a1812"
  ink-soft: "#2e2a22"
  paper: "#e8d4a8"
  paper-deep: "#d4bc8a"
  signal: "#58f03a"
  signal-hover: "#7aff5c"
  signal-soft: "#2eb018"
  muted: "#5a5143"
  faint: "#7a6f5c"
  surface-white: "#f5edd8"
  danger: "#b53a2e"
  line-soft: "rgba(26, 24, 18, 0.2)"
typography:
  display:
    fontFamily: "Archivo Black, Arial Black, Impact, sans-serif"
    fontSize: "clamp(2.35rem, 8vw, 4.75rem)"
    fontWeight: 400
    lineHeight: 0.92
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Archivo Black, Arial Black, Impact, sans-serif"
    fontSize: "clamp(2rem, 6vw, 3.4rem)"
    fontWeight: 400
    lineHeight: 1.02
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Archivo Black, Arial Black, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.04em"
  body:
    fontFamily: "Archivo, Avenir Next, Segoe UI, sans-serif"
    fontSize: "clamp(1.02rem, 2.1vw, 1.15rem)"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Archivo, Avenir Next, Segoe UI, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.04em"
rounded:
  none: "0"
spacing:
  xs: "0.35rem"
  sm: "0.75rem"
  md: "1.25rem"
  lg: "1.5rem"
  xl: "2.25rem"
  page: "clamp(1.5rem, 4vw, 3.5rem)"
  sidebar: "260px"
components:
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.9rem 1.35rem"
  button-primary-hover:
    backgroundColor: "{colors.signal-hover}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.9rem 1.35rem"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.9rem 1.35rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.none}"
    padding: "0.55rem 1rem"
  signal-bar:
    backgroundColor: "{colors.signal}"
    rounded: "{rounded.none}"
    height: "0.55rem"
    width: "min(100%, 22rem)"
  status-pill:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.55rem 0.7rem"
  input-composer:
    backgroundColor: "{colors.surface-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.75rem 1rem"
  brand-mark:
    backgroundColor: "transparent"
    rounded: "{rounded.none}"
    size: "2.5rem"
---

# Design System: Marvin

## Overview

**Creative North Star: "Signal Board"**

Marvin reads as Swiss industrial enamel signage with a retro remap: stacked uppercase directives on warm tan paper, thick ink rules, and a single bright green signal like a CRT caution stripe — not a soft AI glow. Clarity is the personality. The marketing site boards the claim (local voice, you in charge); the app operates the same materials with green reserved for live voice and status.

Density is sparse and frontal. Surfaces are matte tan enamel fields with a whisper of grain; no orbs, no purple haze, no floating glass. Depth comes from ink borders and tonal tan steps, not shadows on primary chrome.

(Shipped Signal Board supersedes the older cream/sage/Fraunces note still lingering in PRODUCT.md brand history.)

**Key Characteristics:**
- Tan field `#e8d4a8` + warm ink `#1a1812` + one bright green signal `#58f03a`
- Archivo Black for directives; Archivo for body and UI chrome
- Square enamel edges (`border-radius: 0`) on primary chrome
- Thick ink rules (1.5px–2px) for section cuts and frames
- Green used sparingly: one bar, primary CTAs, live-voice accents

## Colors

A three-note enamel board: tan ground, ink figure, green signal stripe.

### Primary
- **Signal Green** (`#58f03a`): The only accent. Marketing: one horizontal signal bar, primary Download/choice CTAs, underline highlight under a directive line, text selection. App: Start Voice, live mode badge, listening/speaking status. Hover lifts to `#7aff5c`; soft reference `#2eb018`.

### Neutral
- **Tan Paper** (`#e8d4a8`): Default page and main canvas.
- **Tan Deep** (`#d4bc8a`): Atmosphere gradient foot, secondary button hover, sidebar, assistant bubble, composer rail.
- **Ink** (`#1a1812`): All primary type, borders, brand mark frame, active function fill (light theme).
- **Ink Soft** (`#2e2a22`): Supporting ink step.
- **Muted** (`#5a5143`): Lede, privacy copy, secondary labels (hue-tinted from tan).
- **Faint** (`#7a6f5c`): CTA notes, dim meta, inactive status.
- **Surface Cream** (`#f5edd8`): App cards/inputs on tan (light theme).
- **Danger** (`#b53a2e`): Stop-listening / destructive confirms (app).

### Named Rules
**The One Signal Rule.** Signal green occupies a small fraction of any screen. One bar or one live-voice control cluster is enough; flooding green kills the stripe.

**The Ink-On-Paper Rule.** Figure and rule are ink on tan (or tan on ink in dark theme). Never swap signal green into body text or large backgrounds.

## Typography

**Display Font:** Archivo Black (Arial Black, Impact)
**Body Font:** Archivo (Avenir Next, Segoe UI)

**Character:** Industrial board lettering — black condensed display stacked tight; body is sturdy grotesque at medium weight, never soft editorial serif.

### Hierarchy
- **Display** (400, `clamp(2.35rem, 8vw, 4.75rem)`, line-height 0.92, uppercase, tracking −0.02em): Stacked directives on the marketing hero (`MARVIN` / `LOCAL VOICE` / `YOU IN CHARGE`).
- **Headline** (400, `clamp(2rem, 6vw, 3.4rem)`, line-height 1.02, uppercase): Interior marketing page titles; optional yellow highlight fill on an emphasized word.
- **Title** (400, ~1.05rem, uppercase, tracking 0.04–0.06em): Brand name, app topbar/section titles, welcome heading.
- **Body** (500, `clamp(1.02rem, 2.1vw, 1.15rem)`, line-height 1.5, max ~38–44ch on marketing): Ledes and privacy; app messages ~0.9rem / 1.5.
- **Label** (600–700, 0.68–0.82rem, uppercase, tracking 0.04–0.08em): CTA notes, back links, functions headings, status pills, mode badges.

### Named Rules
**The Stacked Directive Rule.** Hero claims stack as short uppercase enamel lines, not a long sentence headline. Keep lines board-short; do not wrap into paragraph display.

**The No Soft Serif Rule.** Do not introduce Fraunces, Georgia, or other editorial display faces into this world.

## Layout

Marketing pages are a single centered enamel plate: `max-width: 52rem`, vertical flex, padding `clamp(1.5rem, 4vw, 3.5rem)`, content left-aligned within the plate. Rhythm between brand → directives → lede → signal bar → CTA → privacy uses ~1.5–2.25rem steps. Choice screens use a 2-column grid (`gap: 0.75rem`, `max-width: 34rem`) collapsing to one column at `520px`.

The app is a fixed sidebar + main split: sidebar `260px` with `2px` ink right rule; main holds topbar (`2px` bottom rule), scroll transcript, and composer (`2px` top rule). Sidebar padding `1.25rem`; chat padding `1.5rem`; composer padding `1rem 1.5rem`.

## Elevation & Depth

Primary chrome is flat. Depth is tonal (paper → paper-deep → white input) plus thick ink borders. Atmosphere is a quiet vertical paper gradient plus ~3.5% enamel noise — not lighting orbs.

Shadows appear only on transient overlays (settings/confirm/model menus). They are not part of the resting Signal Board language.

### Named Rules
**The Flat Enamel Rule.** Buttons, pills, badges, brand marks, signal bars, and chat bubbles sit flush. Do not add ambient drop shadows to resting chrome.

## Shapes

**Square enamel** is the form language: `--radius: 0` on brand marks, buttons, signal bars, status pills, mode badges, status dots, messages, and the composer field. Borders are hard ink strokes at **1.5px** (marketing controls, privacy rule) or **2px** (app sidebar/topbar/composer seams).

### Named Rules
**The Square Edge Rule.** Primary interactive chrome is square. Soft radii belong only to incidental overlay chrome until those surfaces are brought into enamel; do not treat soft cards as the house shape.

## Components

### Buttons
Enamel plates with ink stroke. Body font, weight 700, slight tracking.

- **Shape:** Square (`0`), border `1.5px solid` ink
- **Primary:** Signal fill, ink text; hover `#ffd11a` with `translateY(-1px)` (marketing); app primary omits the lift
- **Secondary:** Paper fill, ink text; hover paper-deep
- **Ghost (app):** Transparent, muted text; hover white card surface
- **Danger / listening stop:** Danger fill, white text
- **Focus:** Marketing uses `2px solid` signal outline, offset `3px`

### Signal Bar
Signature marketing stripe: height `0.55rem`, width `min(100%, 22rem)`, signal fill, `1.5px` ink border, square. One per first viewport / page plate.

### Status Pill & Mode Badge (app)
Square ink-framed chips; uppercase micro labels. Ready/listening/speaking dots use signal (or ink when processing). Mode badge fills signal only when voice is active.

### Brand
Square mark (`2.5rem` site / `48px` app) with ink frame on marketing; Archivo Black uppercase wordmark beside it.

### Stacked Directives
Unordered list of Archivo Black lines; optional `.signal-line` paints a yellow underline bar behind the final claim.

### Choice Cards (marketing)
Tall secondary/primary buttons in a two-up grid: bold label + faint hint; same square enamel stroke.

### Inputs / Composer
Square white field, `1px` ink border; focus border shifts to signal. Send control is signal enamel matching Start Voice.

### Navigation (app sidebar)
Function rows are flat; active row inverts to ink fill (light) or signal fill (dark) with soft signal border tint. Section labels are uppercase faint microtype.

### Chat Bubbles
Square; user on signal (light theme) with soft signal border; assistant on paper-deep. Max width ~75%.

## Do's and Don'ts

### Do:
- **Do** keep signal green rare — bar, primary CTA, or live-voice state.
- **Do** stack short uppercase Archivo Black directives for hero claims.
- **Do** use square edges and 1.5–2px ink rules on primary chrome.
- **Do** set body/lede on muted ink over tan, not green slabs of text.
- **Do** honor `prefers-reduced-motion` by dropping board-in and hover lift.

### Don't:
- **Don't** build soft AI heroes, purple gradients, glow orbs, or glassmorphism on resting surfaces.
- **Don't** round primary buttons, pills, badges, or the signal bar.
- **Don't** use green as a page wash or for long-form text.
- **Don't** revive Fraunces/Sora/sage or the old yellow signal — tan + bright green is the shipped remap.
- **Don't** invent kickers/eyebrows above the brand; the brand and directives are the board.
