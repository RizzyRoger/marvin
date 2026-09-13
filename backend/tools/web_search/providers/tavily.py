"""Tavily web-search provider adapter."""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.tools.web_search.types import (
    ProviderHealth,
    SearchDepth,
    SearchErrorCategory,
    SearchFreshness,
    SearchPurpose,
    WebSearchError,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)

logger = logging.getLogger(__name__)

_DEPTH_MAP = {
    SearchDepth.FAST: "fast",
    SearchDepth.BALANCED: "basic",
    SearchDepth.DEEP: "advanced",
}

_PURPOSE_TOPIC = {
    SearchPurpose.GENERAL: "general",
    SearchPurpose.NEWS: "news",
    SearchPurpose.FINANCE: "finance",
    SearchPurpose.VERIFICATION: "general",
    SearchPurpose.RECOMMENDATION: "general",
}


class TavilyProvider:
    """Trusted backend adapter around the Tavily Search API."""

    def __init__(self, api_key: str, *, timeout_ms: int = 8000):
        self._api_key = (api_key or "").strip()
        self._timeout_s = max(1.0, timeout_ms / 1000.0)
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self._api_key)
        return self._client

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(
                available=False,
                provider="tavily",
                detail="TAVILY_API_KEY is not configured",
            )
        return ProviderHealth(available=True, provider="tavily", detail="configured")

    def map_request(self, request: WebSearchRequest) -> dict[str, Any]:
        """Map provider-neutral request to Tavily Search parameters."""
        params: dict[str, Any] = {
            "query": request.query,
            "search_depth": _DEPTH_MAP.get(request.depth, "basic"),
            "topic": _PURPOSE_TOPIC.get(request.purpose, "general"),
            "max_results": max(1, min(int(request.max_results), 10)),
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        if request.include_domains:
            params["include_domains"] = request.include_domains[:20]
        if request.exclude_domains:
            params["exclude_domains"] = request.exclude_domains[:20]
        if request.locale_or_country:
            params["country"] = request.locale_or_country
        freshness = request.freshness
        if freshness.start_date or freshness.end_date:
            if freshness.start_date:
                params["start_date"] = freshness.start_date
            if freshness.end_date:
                params["end_date"] = freshness.end_date
        elif freshness.relative != SearchFreshness.ANY:
            params["time_range"] = freshness.relative.value
        return params

    def search(
        self,
        request: WebSearchRequest,
        cancellation_event,
    ) -> WebSearchResponse:
        if not self.is_available():
            raise WebSearchError(
                SearchErrorCategory.MISSING_CONFIG,
                "Web Search is not configured, so I could not check current sources.",
            )
        if cancellation_event is not None and cancellation_event.is_set():
            raise WebSearchError(SearchErrorCategory.CANCELED, "Search canceled.")

        params = self.map_request(request)
        started = time.perf_counter()
        logger.info(
            "DEV: provider request started provider=tavily purpose=%s depth=%s",
            request.purpose.value,
            request.depth.value,
        )
        try:
            client = self._get_client()
            # Prefer timeout kwarg when supported by the installed SDK.
            try:
                raw = client.search(**params, timeout=self._timeout_s)
            except TypeError:
                raw = client.search(**params)
        except WebSearchError:
            raise
        except Exception as exc:
            raise self._classify_exception(exc) from None

        if cancellation_event is not None and cancellation_event.is_set():
            raise WebSearchError(SearchErrorCategory.CANCELED, "Search canceled.")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return self._normalize(request, raw, elapsed_ms)

    def _classify_exception(self, exc: Exception) -> WebSearchError:
        text = str(exc)
        # Never include secrets; strip anything that looks like a key fragment.
        safe = text
        if self._api_key and self._api_key in safe:
            safe = safe.replace(self._api_key, "[redacted]")
        lower = safe.lower()
        if "timeout" in lower or "timed out" in lower:
            return WebSearchError(
                SearchErrorCategory.TIMEOUT,
                "The web search timed out before returning reliable results.",
            )
        if any(token in lower for token in ("401", "403", "unauthorized", "forbidden", "invalid api")):
            return WebSearchError(
                SearchErrorCategory.AUTH,
                "Web Search could not authenticate. Its API configuration needs attention.",
            )
        if "429" in lower or "rate" in lower:
            return WebSearchError(
                SearchErrorCategory.RATE_LIMIT,
                "Web Search is temporarily rate-limited. Try again shortly.",
            )
        if "quota" in lower or "credit" in lower:
            return WebSearchError(
                SearchErrorCategory.QUOTA,
                "Web Search quota is exhausted for this configuration.",
            )
        if "400" in lower or "invalid" in lower:
            return WebSearchError(
                SearchErrorCategory.INVALID_REQUEST,
                "The web search request was rejected as invalid.",
            )
        if any(token in lower for token in ("500", "502", "503", "504", "outage")):
            return WebSearchError(
                SearchErrorCategory.PROVIDER_OUTAGE,
                "The web search provider is temporarily unavailable.",
            )
        if any(token in lower for token in ("network", "connection", "dns")):
            return WebSearchError(
                SearchErrorCategory.NETWORK,
                "A network error interrupted the web search.",
            )
        return WebSearchError(
            SearchErrorCategory.INTERNAL,
            "Web Search failed due to an internal provider error.",
        )

    def _normalize(
        self,
        request: WebSearchRequest,
        raw: Any,
        elapsed_ms: int,
    ) -> WebSearchResponse:
        if not isinstance(raw, dict):
            raise WebSearchError(
                SearchErrorCategory.MALFORMED,
                "The web search provider returned a malformed response.",
            )
        items = raw.get("results")
        if items is None:
            raise WebSearchError(
                SearchErrorCategory.MALFORMED,
                "The web search provider returned a malformed response.",
            )
        if not isinstance(items, list):
            raise WebSearchError(
                SearchErrorCategory.MALFORMED,
                "The web search provider returned a malformed response.",
            )

        results: list[WebSearchResult] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip() or url
            snippet = str(
                item.get("content")
                or item.get("snippet")
                or item.get("raw_content")
                or ""
            ).strip()
            if not url:
                continue
            score = item.get("score")
            try:
                score_f = float(score) if score is not None else 0.0
            except (TypeError, ValueError):
                score_f = 0.0
            published = item.get("published_date") or item.get("published_at")
            results.append(
                WebSearchResult(
                    source_id=f"S{index}",
                    title=title,
                    url=url,
                    snippet=snippet,
                    score=score_f,
                    published_at=str(published) if published else None,
                    query=request.query,
                )
            )

        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else None
        logger.info(
            "DEV: provider response received provider=tavily results=%d ms=%d",
            len(results),
            elapsed_ms,
        )
        return WebSearchResponse(
            query=request.query,
            results=results,
            provider="tavily",
            provider_request_id=str(raw.get("request_id") or "") or None,
            provider_response_time_ms=elapsed_ms,
            usage=usage,
            empty=len(results) == 0,
        )
