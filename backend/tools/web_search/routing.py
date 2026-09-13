"""Deterministic web-search intent routing."""

from __future__ import annotations

import logging
import re

from backend.tools.web_search.types import SearchDecision

logger = logging.getLogger(__name__)

_EXPLICIT = re.compile(
    r"\b("
    r"search the web|search online|search for|google(?:\s+it)?|"
    r"look(?:\s+it)?\s+up online|look online|browse(?:\s+the\s+web)?|"
    r"research online|find online|verify (?:this|that|whether|if) online|"
    r"check online|web search|search the internet|"
    r"on the (?:web|internet)|from the (?:web|internet)|"
    r"use web search|look this up|look that up"
    r")\b",
    re.I,
)

# Very narrow auto-required current-info triggers. Prefer explicit search.
_CURRENT_REQUIRED = re.compile(
    r"\b("
    r"latest news|breaking news|today[\u2019']?s news|"
    r"current (?:price|stock price|exchange rate)|"
    r"who (?:is|are) the (?:current|now) |"
    r"what(?:[\u2019']?s| is) the (?:current|latest) (?:price|version|score)|"
    r"live score|weather (?:today|now|right now)"
    r")\b",
    re.I,
)

_FORBIDDEN = re.compile(
    r"\b("
    r"do not (?:browse|search|look online|use the web|use web search)|"
    r"don't (?:browse|search|look online)|"
    r"without (?:browsing|searching|looking online|the web)|"
    r"no (?:web )?search|offline only"
    r")\b",
    re.I,
)

_LOCAL_ONLY = re.compile(
    r"\b("
    r"rewrite|rephrase|edit this|summarize (?:this|the following)|translate|"
    r"poem|story|haiku|joke|calculate|what is \d|multiply|divide|plus|"
    r"how are you|hello|hi(?:\s|,|!|\.|$)|hey(?:\s|,|!|\.|$)|good morning|"
    r"good evening|thanks|thank you|goodbye|bye\b|"
    r"my (?:obsidian |)?(?:vault|notes?|daily note)|in my notes|from my notes|"
    r"left to do|incomplete tasks?"
    r")\b",
    re.I,
)

# Only when the model is allowed to *consider* searching because knowledge is
# genuinely insufficient — never for casual chat or "just in case".
_KNOWLEDGE_GAP_CANDIDATE = re.compile(
    r"\b("
    r"who (?:is|was|won)|what (?:is|was|are) the (?:official|legal|current)|"
    r"when (?:did|was|is)|which company|obscure|little[- ]known|"
    r"i don'?t know if|is it true that|fact[- ]check"
    r")\b",
    re.I,
)


def decide_web_search(
    user_message: str,
    *,
    available: bool,
    vault_required: bool = False,
) -> tuple[SearchDecision, str]:
    """
    Return (decision, reason) for whether web search should run this turn.

    Policy:
    - REQUIRED: explicit ask, or a very narrow current-info request
    - ALLOWED: rare knowledge-gap candidates (model may search only if it truly
      cannot answer; never auto-run)
    - NOT_NEEDED: everything else, including greetings and casual chat
    """
    text = (user_message or "").strip()
    if not text:
        return SearchDecision.NOT_NEEDED, "empty"

    if _FORBIDDEN.search(text):
        decision = SearchDecision.FORBIDDEN_BY_USER
        reason = "user_disabled_browsing"
        logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
        return decision, reason

    if not available:
        if _EXPLICIT.search(text) or _CURRENT_REQUIRED.search(text):
            decision = SearchDecision.UNAVAILABLE
            reason = "provider_unavailable"
            logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
            return decision, reason
        return SearchDecision.NOT_NEEDED, "provider_unavailable_not_requested"

    if _EXPLICIT.search(text):
        decision = SearchDecision.REQUIRED
        reason = "explicit_request"
        logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
        return decision, reason

    if _LOCAL_ONLY.search(text) and not _EXPLICIT.search(text):
        decision = SearchDecision.NOT_NEEDED
        reason = "local_or_casual"
        logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
        return decision, reason

    if vault_required and not _EXPLICIT.search(text):
        decision = SearchDecision.NOT_NEEDED
        reason = "vault_only"
        logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
        return decision, reason

    if _CURRENT_REQUIRED.search(text):
        decision = SearchDecision.REQUIRED
        reason = "narrow_current_info"
        logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
        return decision, reason

    if _KNOWLEDGE_GAP_CANDIDATE.search(text):
        decision = SearchDecision.ALLOWED
        reason = "possible_knowledge_gap"
        logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
        return decision, reason

    decision = SearchDecision.NOT_NEEDED
    reason = "default_no_search"
    logger.info("DEV: search decision=%s reason=%s", decision.value, reason)
    return decision, reason


_DEFERRED_SEARCH_RE = re.compile(
    r"\b("
    r"let me search|i'?ll search|i will search|"
    r"search(?:ing)? (?:the )?(?:web|online|internet)|"
    r"look(?:ing)? (?:it |that )?up online|"
    r"i'?ll look (?:that |it )?up|let me look (?:that |it )?up|"
    r"browse(?:ing)? (?:the )?(?:web|internet)|"
    r"i'?ll (?:check|verify) online"
    r")\b",
    re.I,
)

_INVENTED_SEARCH_RE = re.compile(
    r"("
    r"\[S\d+\]|"
    r"\baccording to (?:sources?|reports?|the web|online)\b|"
    r"\b(?:latest|breaking) (?:news|reports?)\b.+\b(says?|report)\b"
    r")",
    re.I,
)


def looks_like_deferred_web_search(reply: str) -> bool:
    """True when the model stalls with a promise to search the web."""
    return bool(_DEFERRED_SEARCH_RE.search(reply or ""))


def looks_like_invented_web_claim(reply: str) -> bool:
    """Heuristic: reply cites web sources without tool evidence this turn."""
    text = reply or ""
    if _INVENTED_SEARCH_RE.search(text):
        return True
    if re.search(r"(?m)^\s*([-*•]|\d+[.)])\s+\S+", text) and re.search(
        r"\b(source|online|according to|reported)\b",
        text,
        re.I,
    ):
        return True
    return False
