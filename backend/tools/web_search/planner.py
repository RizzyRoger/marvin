"""Query planning, URL canonicalization, and result merging."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.tools.web_search.types import (
    FreshnessFilter,
    SearchDepth,
    SearchFreshness,
    SearchPurpose,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_items, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def request_hash(request: WebSearchRequest) -> str:
    payload = "|".join(str(part) for part in request.cache_key_parts())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def sanitize_external_query(query: str) -> str:
    """Minimize privacy leakage before sending a query to an external provider."""
    text = (query or "").strip()
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[redacted-email]", text)
    text = re.sub(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+", "[redacted]", text)
    text = re.sub(r"(?i)\bsk-[A-Za-z0-9]{10,}\b", "[redacted]", text)
    text = re.sub(r"(?i)\btvly-[A-Za-z0-9]{8,}\b", "[redacted]", text)
    # Drop local filesystem paths.
    text = re.sub(r"(?i)(/Users/[^\s]+|/home/[^\s]+|[A-Za-z]:\\[^\s]+)", "[local-path]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


def infer_purpose(user_message: str, query: str) -> SearchPurpose:
    lower = f"{user_message} {query}".lower()
    if re.search(r"\b(stock|market|nasdaq|finance|interest rate|crypto)\b", lower):
        return SearchPurpose.FINANCE
    if re.search(r"\b(news|breaking|headline|election)\b", lower):
        return SearchPurpose.NEWS
    if re.search(r"\b(verify|true|false|fact[- ]?check)\b", lower):
        return SearchPurpose.VERIFICATION
    if re.search(r"\b(best|recommend|vs|compare)\b", lower):
        return SearchPurpose.RECOMMENDATION
    return SearchPurpose.GENERAL


def infer_freshness(user_message: str) -> FreshnessFilter:
    from backend.clock import get_clock_service, get_turn_context

    lower = (user_message or "").lower()
    ctx = get_turn_context()
    clock = get_clock_service()
    if "yesterday" in lower and ctx is not None:
        day = clock.resolve_relative_date("yesterday", ctx)
        if day is not None:
            iso = day.isoformat()
            return FreshnessFilter(
                relative=SearchFreshness.ANY,
                start_date=iso,
                end_date=iso,
            )
    if re.search(r"\b(today|right now|breaking|as of today)\b", lower):
        return FreshnessFilter(relative=SearchFreshness.DAY)
    if re.search(r"\b(this week|past week|last week)\b", lower):
        return FreshnessFilter(relative=SearchFreshness.WEEK)
    if re.search(r"\b(this month|past month|last month)\b", lower):
        return FreshnessFilter(relative=SearchFreshness.MONTH)
    if re.search(r"\b(this year|past year|latest|current|recent)\b", lower):
        return FreshnessFilter(relative=SearchFreshness.YEAR)
    return FreshnessFilter(relative=SearchFreshness.ANY)


def infer_depth(user_message: str) -> SearchDepth:
    lower = (user_message or "").lower()
    if re.search(r"\b(compare|comprehensive|in depth|detailed research|pros and cons)\b", lower):
        return SearchDepth.DEEP
    if re.search(r"\b(quick|briefly|simple|what is the latest version)\b", lower):
        return SearchDepth.FAST
    return SearchDepth.BALANCED


def plan_queries(user_message: str, *, max_queries: int = 3) -> list[str]:
    """
    Produce one focused query for simple asks, or up to max_queries for broad comparisons.
    """
    text = sanitize_external_query(user_message)
    if not text:
        return []

    # Strip explicit search imperatives for cleaner provider queries.
    cleaned = re.sub(
        r"(?i)\b(search the web for|search online for|search for|look up|research|browse|find online)\b",
        " ",
        text,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")

    # Combined Obsidian + search workflows: keep only the public research clause.
    if re.search(r"(?i)\b(add|append|write|put).{0,40}\b(daily note|note)\b", cleaned):
        parts = re.split(
            r"(?i)\b(?:and then|then|,?\s*and)\b(?:\s+make|\s+add|\s+write|\s+put|\s+give)?",
            cleaned,
            maxsplit=1,
        )
        cleaned = parts[0].strip(" .") or cleaned

    broad = bool(
        re.search(r"(?i)\b(compare|versus|vs\.?|pros and cons|strength,? cardio,? and)\b", cleaned)
    )
    if not broad:
        query = cleaned or text
        return [query[:400]]

    # Split comparison axes when clearly enumerated.
    axes = re.findall(
        r"(?i)\b(strength|cardio|mobility|beginner|intermediate|advanced)\b",
        cleaned,
    )
    unique_axes: list[str] = []
    for axis in axes:
        key = axis.lower()
        if key not in unique_axes:
            unique_axes.append(key)
    if len(unique_axes) >= 2:
        topic = re.sub(
            r"(?i)\b(compare|the current|recommendations? for|best)\b",
            " ",
            cleaned,
        )
        topic = re.sub(r"\s+", " ", topic).strip()
        base = "exercise recommendations" if "exercise" in cleaned.lower() else topic
        planned = [f"{axis} {base}".strip()[:400] for axis in unique_axes[:max_queries]]
        return _dedupe_queries(planned)[:max_queries]

    return _dedupe_queries([cleaned[:400]])[:max_queries]


def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        key = re.sub(r"\s+", " ", query.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(query.strip())
    return out


def merge_responses(
    responses: list[WebSearchResponse],
    *,
    max_results: int = 8,
) -> WebSearchResponse:
    """Deduplicate by canonical URL and renumber source IDs S1..Sn."""
    merged: list[WebSearchResult] = []
    seen_urls: set[str] = set()
    for response in responses:
        for item in response.results:
            key = canonicalize_url(item.url)
            if not key or key in seen_urls:
                continue
            seen_urls.add(key)
            merged.append(item)
    merged.sort(key=lambda item: (-item.score, item.title.lower()))
    merged = merged[:max_results]
    numbered = [
        WebSearchResult(
            source_id=f"S{index}",
            title=item.title,
            url=item.url,
            snippet=item.snippet,
            score=item.score,
            published_at=item.published_at,
            query=item.query,
        )
        for index, item in enumerate(merged, start=1)
    ]
    query = responses[0].query if responses else ""
    provider = responses[0].provider if responses else "none"
    return WebSearchResponse(
        query=query,
        results=numbered,
        provider=provider,
        empty=len(numbered) == 0,
        provider_response_time_ms=sum(
            r.provider_response_time_ms or 0 for r in responses
        )
        or None,
    )
