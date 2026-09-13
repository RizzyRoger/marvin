---
name: web-search
description: >
  Decide when to call web_search, craft a focused query with purpose and freshness,
  and ground short spoken answers with [S1]-style citations. Use for current events,
  lookups, news, or any request that needs live web facts.
---

# Web search skill

Use the `web_search` tool when the user needs facts that may be outdated in model
memory, or explicitly asks to search / look something up online. Prefer tools over
guessing. If search is unavailable, say that clearly — never invent sources.

## When to search

Search when:

- The user asks for news, prices, scores, schedules, or “current” / “latest” info
- The answer depends on a specific recent event or page
- You lack a reliable factual basis and the user expects accuracy

Skip search when:

- The question is opinion, brainstorming, or about their vault (use Obsidian tools)
- They only want a definition you already know and currency does not matter

## Query discipline

- Prefer **one** focused query per turn; broaden only if results are empty or off-topic
- Set `purpose` when it helps: `general`, `news`, `finance`, `verification`, or `recommendation`
- Set `freshness` when recency matters (news, markets, “today”, “this week”)
- Do not pad with irrelevant domains just to increase citation count

## Answering for speech

Marvin replies are spoken aloud:

- Keep the spoken answer short (roughly under 80 words unless they ask for detail)
- Ground claims with brief markers like `[S1]`, `[S2]` matching tool results
- Do not invent URLs, titles, or quotes that were not returned
- If results conflict, say so in one sentence
- Do not end with a question or offer to search more unless they asked for options

## Failure modes

- Empty / failed search → say search failed or returned nothing useful; do not fabricate
- Weak matches → answer cautiously and note uncertainty
- User forbade the web → do not call `web_search`
