# Marvin

**Author:** rogerwei489@gmail.com
**Status:** DRAFT
**Updated:** 2026.08.24

---

## Problem

As AI gets better at decision making, we are more inclined to use it for just that. We find ourselves using chatbots more and more to make decisions instead of helping us make them.

At the same time, because of this, it is becoming more important that we stay able to make unique and capable decisions of our own.

## Vision & Opportunity

Marvin is an AI agent that lets you make the decisions — automating what should be automated, not what can be automated.

Many of us use AI. Marvin gives you the capability of ChatGPT, Grok, or Claude, while putting you in charge.

Marvin does not ask follow-ups to suggest you do something. Marvin does not make decisions for you. Instead, Marvin automates repetitive, time-consuming tasks, leaving you time for important decisions.

## Target Use Cases

- As a student, I want a more convenient way to manage my notes, files, music, and timers without bouncing between apps — and without the assistant telling me what to study next.
- As an office worker, I want a personal assistant that files, reminds, searches, and controls the tools I already use, so I can spend attention on judgment calls.
- As a product manager, I want tedious chores (notes, lookups, playback, reminders) automated, while product decisions stay mine.

These are one user on one Mac, not a two-sided marketplace. The same product loop serves all three: speak or type a chore → Marvin does it → you decide what matters.

## Landscape

Other assistants are chat-first. They optimize for conversation: follow-up questions, recommendations, “would you like me to…”. That loop trains people to hand over judgment.

| Alternative | What they optimize | Where they fail this problem |
|---|---|---|
| ChatGPT / Claude / Grok (cloud chat) | General reasoning and tool plugins | Text-first; steer with follow-ups; your context leaves the machine |
| Siri / Alexa | Hands-free device control | Shallow tools; little vault/file depth; cloud by default |
| Local LLM apps (Ollama UIs, LM Studio) | Private chat | Chat, not a command center; weak daily-tool loop |
| Voice-to-text utilities | Fast dictation | Transcription only; no agent, no chores |

Marvin’s opening is a **local-first voice command center**: same model-class capability (local and/or the cloud models you already pay for), wired into Obsidian, Spotify, files, timers, and search — with a hard product rule that it executes chores and does not take the decision.

## Proposed Solution

Marvin is a Mac (Apple Silicon) personal voice agent that automates what should be automated, not what can be automated.

**Top 3 MVP value props**

1. Marvin can do what other chatbots do — local Qwen by default, or ChatGPT / Grok / Claude when you bring a key.
2. Marvin does not make decisions. It does not end turns with suggestions or “what should we do next.” It frees time so you can decide.
3. Marvin is a command center: Obsidian vault, Spotify, timers/reminders, web search (opt-in), finding files, opening pages, and running scripts you authorize.

**Default trust model:** on-device (mic → transcribe → local LLM → speak). Cloud LLM, web search, and Spotify leave the machine only when the user opts in.

## Goals

- Put decision-making back in the hands of humans.
- Free up time by automating basic tasks.

### Non-goals

- Full usability parity with every chatbot plugin / “tool port” of the internet.
- A $5/month subscription.
- Multi-user or team accounts; Marvin is a single-user Mac agent.
- Mobile, Linux GA, or a hosted Marvin in the cloud.
- Marvin choosing, ranking, or recommending what the user should do next.

### Y1 success metrics

Consumer desktop agent — not B2B domains. “Valuable” means people come back and use it for chores, not that they chat longer.

| Goal | Signals | Metrics | Targets |
|---|---|---|---|
| Engagement & adoption | Users find Marvin valuable enough to keep using it | 7-day active users (7DAU); 1-wk retention (come back 7d after first successful turn); 7d stickiness (7DAU / 28DAU) | >50 7DAU; >10% 1-wk retention; >5% 7d stickiness |
| Grow the user base | People complete download → first useful turn | First successful turn (voice or text that gets a reply); MoM 28DAU growth | >5% MoM 28DAU growth |
| Command-center, not chatbot | Users use Marvin for chores, not only chat | % of returning users with ≥1 tool action / week (vault, Spotify, timer, search, files) | >40% of WAU run a tool |
| Stay in charge | Users keep judgment; privacy boundary is understood | % of GA users who can state local vs cloud (survey or first-run quiz optional); % of turns on local model | Majority of turns local among users who never added a cloud key |
| Honest GTM | Pay-what-you-can does not block access | Download completions; paid vs free mix | Free path always works; paid is support, not a gate |

---

## Conceptual Model

The user needs to learn **four things**. Everything else is settings.

```
You (voice or text)
    │
    ▼
Voice Lock?  ── if enrolled, only your voice continues
    │
    ▼
Transcribe on-device  (audio is not kept)
    │
    ▼
You already decided the chore
    │
    ├─ Chat / reason     → local model, or a cloud model you chose
    ├─ Do a chore        → Obsidian, Spotify, timer, search, files, scripts
    └─ Refuse a decision → no “you should…”, no “want me to also…?”
    │
    ▼
Spoken + written result. Stop.
```

**Mental model**

| Concept | What the user should believe |
|---|---|
| **Chore vs decision** | If you already know the action (“rename this note”, “play the album”, “timer 10 minutes”), Marvin does it. If the action is a judgment (“what should I prioritize?”, “which strategy is better?”), Marvin answers with information and stops. It does not pick for you or ask to proceed. |
| **Command center** | Marvin sits on top of apps you already have. It is not a new notes app, music app, or calendar. |
| **Local unless you leave** | Mic audio and Voice Lock never leave. Transcripts stay on disk unless you pick a cloud model or an opt-in tool (search, Spotify). Mixing a cloud model with vault tools can send note fragments out — that must be visible. |
| **One owner** | This Mac account’s Marvin listens to the enrolled voice. It is not a household concierge unless you turn Voice Lock off. |

**Surfaces**

- **Marketing site** (marvin.sarl): decide and get a build ($5 or free).
- **Marvin.app**: operate — listen, talk, settings, tools.

The user should not have to learn a new chat persona. They should learn *when Marvin will act* vs *when it will only answer*.

---

## Requirements

Organized by critical journeys for the top use case: **a Mac owner runs a daily command-center agent that executes chores and does not take decisions.**

Personas (student, office worker, PM) share this loop. There is no second marketplace side.

**Legend**

- **[P0]** = MVP for a GA release
- **[P1]** = Important for a delightful experience
- **[P2]** = Nice-to-have

---

### CUJ 1 — Get Marvin and complete a first useful turn

Visitor can tell Marvin is for them, get a Mac build without an account, install it, and finish one successful voice or text turn. GA is not a website; it is this loop.

#### Deciding and getting a build

- **[P0]** Visitors can understand, before download, that Marvin automates chores and does not make decisions for them.
- **[P0]** Visitors can get a working Apple Silicon Mac build without creating an account.
- **[P0]** Visitors can choose to pay $5 in support or continue on a free path. Payment is not required to obtain the app.
- **[P0]** Visitors who choose free can confirm they cannot pay, then download; visitors who can pay can go to payment instead of taking the free build by accident.
- **[P0]** Paying visitors complete payment before the paid download is granted; both paths land on the same class of build.
- **[P0]** Visitors can see what stays on-device vs what may leave (mic, vault, cloud model, search, Spotify) before they download.
- **[P0]** The team can see funnel drop-off: landing → choose → pay or confirm → download.
- **[P1]** Visitors can watch a short demo of a chore (vault / reminder / voice) before downloading.
- **[P2]** Visitors can verify the download (checksum) without extra trust in the site copy.

Mini-PRD: [Download and pay-what-you-can funnel](#mini-prd-download-funnel)

#### Install and first-run

- **[P0]** Users can install Marvin on their Mac and grant microphone access.
- **[P0]** Users can complete first launch without a cloud account or API key (local default stack).
- **[P0]** Users can point Marvin at an existing Obsidian vault, or skip and set it later.
- **[P0]** Users can see that models may download on first launch and that the app is not ready until they have.
- **[P1]** Users can finish Voice Lock enrollment during first-run, or defer it.
- **[P1]** Users who received an unsigned build can open it through Gatekeeper without being told to disable security.
- **[P2]** Users can restore from a previous Marvin data folder.

#### First useful turn

- **[P0]** Users can start and stop listening.
- **[P0]** Users can speak a request and get a spoken reply plus a visible transcript.
- **[P0]** Users can type instead of speaking and get the same agent behavior.
- **[P0]** Users can tell whether Marvin is listening, thinking, or speaking.
- **[P0]** After the first turn, users can do another turn without re-setup.
- **[P1]** Users can switch between local and a cloud model they have keyed, and see which one will run.
- **[P2]** Users can run a built-in “try this” chore (e.g. set a 1-minute timer) as a first-run check.

---

### CUJ 2 — Daily command center: chores done, decisions left to the user

Owner already has Marvin running. They want tedious work executed across notes, music, time, search, and files — without Marvin steering the next decision. This is the GA core.

#### Talk without being steered

- **[P0]** Users can ask Marvin to do a chore or to answer a question in natural language (voice or text).
- **[P0]** Marvin does not end a turn by asking what to do next, offering extra work, or recommending a decision the user did not request.
- **[P0]** Users can interrupt speech and start a new request.
- **[P0]** Users can see the transcript of what was heard and what was said.
- **[P1]** Users can tell which function ran (chat, vault, Spotify, timer, search, etc.) without managing modes by default.
- **[P2]** Users can pin or name a recurring chore for later (e.g. morning task dump into today’s note).

#### Notes and files (Obsidian)

- **[P0]** Users can find and read notes in their vault by speaking or typing a description, not only an exact path.
- **[P0]** Users can create, append, rename, edit, or delete a note **only when they explicitly ask for that change**.
- **[P0]** Users can have Marvin refuse vault writes when they did not authorize a change.
- **[P0]** Users can keep a blocked area of the vault (e.g. Projects) out of Marvin’s reach.
- **[P0]** Users can add and check off tasks in daily notes in a form Marvin can find later.
- **[P1]** Users can summarize a document or note they point Marvin at, without Marvin turning the summary into a recommended plan unless asked.
- **[P2]** Users can work across more than one vault.

Mini-PRD: [Obsidian writes and authorization](#mini-prd-obsidian-writes)

#### Time (timers and reminders)

- **[P0]** Users can start, cancel, pause, resume, and adjust a countdown timer by voice or text.
- **[P0]** Users can notice when a timer fires (sound + visible state) even if they are not looking at the transcript.
- **[P1]** Users can create a reminder for later (not only a live countdown).
- **[P2]** Users can list pending timers/reminders and manage them from the UI as well as by voice.

#### Music (Spotify)

- **[P0]** Users can connect and disconnect their Spotify account.
- **[P0]** Connected users can play, pause, skip, and request a track/album/artist by voice or text.
- **[P1]** Users can hear why playback failed (no device, not connected) without a chatty recovery pitch.
- **[P2]** Users can use playback history/affinity so “play something I like” is a chore, not a recommendation essay.

#### Lookup and the rest of the desktop

- **[P0]** Users can opt into web search; with it off, Marvin does not send queries off-machine.
- **[P0]** Users who opted in can ask Marvin to look something up and get an answer grounded in that search.
- **[P1]** Users can ask Marvin to find a file on their Mac or in the vault and open or reveal it.
- **[P1]** Users can ask Marvin to open a web page they named.
- **[P1]** Users can run a script or file they named, with an explicit authorization bar (not silent execution).
- **[P2]** Users can add their own skills/tools without a full plugin marketplace.

Non-goal reminder: GA does not require porting every third-party tool. P1 desktop chores are the named MVP set (find files, open pages, run authorized scripts), not unlimited app control.

#### When the user is actually deciding

- **[P0]** Users can ask for information, a summary, or options and receive them **without** Marvin selecting the option or asking to execute a follow-up.
- **[P1]** Users can see that a turn was “answer only” (no tool write, no playback, no timer) so they trust it did not act.
- **[P2]** Users can mark a topic as “decision — never act” (future; not GA).

---

### CUJ 3 — Stay in charge of privacy, speakers, and data

Owner needs a clear boundary: who Marvin listens to, what leaves the Mac, and how to leave. Without this, the vision is marketing.

#### Who can speak

- **[P0]** Users can enroll their voice and turn Voice Lock on or off.
- **[P0]** With Voice Lock on, other speakers cannot get a transcribed request through to the agent.
- **[P0]** Users can test Voice Lock and see whether *this* utterance would be accepted.
- **[P0]** Users can delete the enrolled voice profile.
- **[P1]** Users can adjust how strict Voice Lock is.
- **[P2]** Users can enroll more than one allowed voice.

Mini-PRD: [Voice Lock](#mini-prd-voice-lock)

#### What stays local

- **[P0]** Users can run the full listen → reason → speak loop with no cloud account (local models).
- **[P0]** Users can add optional cloud provider keys (OpenAI / Anthropic / xAI) and pick a model per turn or as default.
- **[P0]** Users can see, in settings, a plain list of what never leaves vs what may leave when a feature is on.
- **[P0]** Users can see when a cloud model is selected, including that vault text in that turn may leave.
- **[P0]** Raw microphone audio is not persisted; only the transcript (and Voice Lock embeddings if enrolled) are kept locally.
- **[P1]** Users can see per turn whether local LLM, cloud LLM, and/or an off-machine tool (search, Spotify) ran.
- **[P2]** Users can force “local only” that disables cloud models and off-machine tools in one control.

Mini-PRD: [Local vs cloud boundary](#mini-prd-local-cloud)

#### Settings, history, and leaving

- **[P0]** Users can open settings from the app and change vault path, theme/scale, providers, Voice Lock, Spotify, and skills.
- **[P0]** Users can clear chat history without deleting keys or Voice Lock (and can understand the difference).
- **[P0]** Users can wipe Marvin data (app, Application Support, logs, Keychain items) using documented steps.
- **[P0]** Users can turn individual skills/tools off so Marvin will not call them.
- **[P1]** Users can get help/support from the site or app without creating an account.
- **[P2]** Users can export chat history as a file they own.

---

## Appendix

### Product / design considerations

**Conceptual model options (choice for GA)**

| Option | Verdict |
|---|---|
| Chatbot with plugins | Rejected — that is the problem we are leaving |
| Always-on household speaker | Rejected — privacy and Voice Lock become the product instead of chores |
| Menu-bar only, no window | Deferred — operate surface needs transcript + settings for trust |
| **Standalone Mac app + marketing site** | **GA** — site persuades; app operates |

**Standalone vs integrated:** Standalone `Marvin.app`. Integrations are into *the user’s* Obsidian, Spotify, and files — Marvin is not inside those apps.

**Mobile vs desktop:** Desktop Mac (Apple Silicon) only for GA. Voice on a phone would change the trust model (always-with-you mic) and is out of scope.

**Unsigned vs notarized:** Honest distribution. Until Developer ID + notarization, the site and first-run must tell the truth about Gatekeeper (Right-click → Open). Do not instruct users to disable macOS security.

**Tone:** Calm, direct. “You stay in charge.” Privacy is a fact table, not fear copy. No fake testimonials or invented metrics.

### GTM

**Positioning:** Personal local-first voice agent that executes chores and refuses to take decisions. Not “another ChatGPT wrapper.” Not “Siri, but private” unless the command-center loop is real.

**Portfolio:** One product, two surfaces (marvin.sarl and Marvin.app). No SKU split in Y1.

**Example press release (internal, directional)**

> *Marvin, a Mac voice agent, is available today. It listens on-device, talks back, and runs the repetitive work in your vault, music, and timers — then stops. It will not ask what you should do next. Local by default; ChatGPT, Claude, or Grok only if you bring a key. Five dollars if you can support it, free if you cannot.*

**Pricing and packaging**

- One-time **$5 support** or **free if you cannot afford it**. Same app. Not a subscription (non-goal).
- Cloud model usage is the user’s own provider bill, not Marvin’s.
- Optional keys: OpenAI, Anthropic, xAI, Spotify, Tavily. None required for the local loop.

**Launch bar**

- Apple Silicon DMG from GitHub Releases.
- GoatCounter on the site (no cookies); funnel visibility for the team is P0.
- No fabricated social proof.

### Mini-PRDs (stubs — write full docs if a P0 starts to sprawl)

#### Mini-PRD: Download funnel

States: landing → choose ($5 vs cannot afford) → Stripe payment **or** confirm → download. Paid and free must not silently converge before the confirm step. Errors: payment abandon, Stripe blocked, DMG 404.

#### Mini-PRD: Voice Lock

Enrollment utterances, on/off, strictness, reject path (no transcript to LLM), test control, delete profile. Failure: noisy room, shared Mac, false reject of owner.

#### Mini-PRD: Local vs cloud boundary

Matrix already in SECURITY.md is the spec. Product requirement is that the matrix is **visible in-app and on the site**, and that vault + cloud model in one turn warns that fragments can leave.

#### Mini-PRD: Obsidian writes

Read by default. Write/create/delete only on explicit user language. Blocked folders. Task checkbox format so “check that off” later works. Never invent file contents not read.

---

*Keep this document under ~8 pages. Cut P2s first.*
