# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

<!-- inferred: interview UI timed out; confirm or correct -->
Primary users are Mac owners (Apple Silicon) who want a personal voice agent they control — especially people who care that speech and history can stay on-device. Secondary audience: visitors to marvin.sarl deciding whether to download.

## Product Purpose

Marvin is a local-first personal voice AI agent for Mac. It listens, transcribes, reasons (local and/or cloud LLM), speaks back, and can run tools (Obsidian, Spotify, timers, web search, etc.). Success means the user can run a useful daily voice agent with a clear privacy boundary: local by default, cloud only when they choose.

## Positioning

<!-- inferred from site + README -->
Unlike cloud assistants, Marvin’s claim is **you stay in charge**: automate what should be automated, not everything that can be; optional fully local stack; Voice Lock can reject other speakers. Neighboring products can offer chat; they cannot truthfully claim Marvin’s same local pipeline + user-controlled automation stance without copying the product.

## Operating Context

- **Desktop app:** `Marvin.app` / pywebview shell around `frontend/` talking to a local Python backend (`backend/`).
- **Marketing site:** static pages in `docs/` at https://marvin.sarl (GitHub Pages).
- **Distribution:** unsigned Apple Silicon DMG from GitHub Releases (`Marvin-1.0.0-arm64.dmg`); Gatekeeper requires Right-click → Open until notarized.
- **Funnel:** `index` → `choose` ($5 support vs “can’t afford”) → Stripe/payment or free → `download.html`.
- **Optional integrations:** Obsidian vault path, Spotify PKCE, Tavily search, cloud provider keys in Keychain.

## Capabilities and Constraints

- Pipeline: mic → Silero VAD → Whisper → LLM (local Qwen default or cloud) → Piper TTS → speakers.
- Only transcribed text is persisted; raw audio is not kept.
- ~4.5 GB models on disk for full local stack; torch dominates app size.
- No Apple Developer ID / notarization yet (unsigned distribution).
- <!-- undecided --> Payment provider may leave Stripe (business registration blocker); Gumroad/Lemon Squeezy under consideration — site still references Stripe Payment Link until replaced.
- Linux mentioned in README; shipped download is Mac arm64 DMG.

## Brand Commitments

- Name: **Marvin**
- Domain: **marvin.sarl**
- Logo: `docs/brand-logo.png` / app brand mark
- Voice (site copy): calm, direct; “you stay in charge”; local / privacy optional, not fear-mongering
- Incumbent marketing look (do not invent a new world in init): cream paper, sage highlight, Fraunces + Sora — recorded later via `/impeccable document` if desired

## Evidence on Hand

- Live site: https://marvin.sarl (`docs/`)
- App UI: `frontend/`
- Release asset: https://github.com/RizzyRoger/marvin/releases/download/v1.0.0/Marvin-1.0.0-arm64.dmg
- Docs: README.md, SECURITY.md, Licenses.md
- No fabricated testimonials, press, or user metrics — do not invent them

## Product Principles

1. **Local-first, cloud-optional** — default trust model is on-device; leaving the machine is an explicit user choice.
2. **User in charge** — automate chores, not judgment; surface decisions to the human.
3. **Honest distribution** — unsigned Mac build and payment friction are product facts, not marketing gloss.
4. **Privacy as a feature, not theater** — say what stays local and what may leave (see SECURITY.md).
5. **One product, two surfaces** — marketing site persuades; app UI operates — same brand, different mode.

## Accessibility & Inclusion

<!-- inferred / minimal -->
No formal WCAG target locked yet. Marketing and app should remain keyboard-usable and readable; free download path exists so price is not a hard barrier.
