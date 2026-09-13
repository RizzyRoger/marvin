"""Deterministic fake web-search provider for tests and local development."""

from __future__ import annotations

import threading
import time
from typing import Callable

from backend.tools.web_search.types import (
    ProviderHealth,
    SearchErrorCategory,
    WebSearchError,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)


class FakeWebSearchProvider:
    """In-memory provider used when Tavily is unavailable or under test."""

    def __init__(
        self,
        *,
        available: bool = True,
        results: list[WebSearchResult] | None = None,
        error: WebSearchError | None = None,
        delay_ms: int = 0,
        on_search: Callable[[WebSearchRequest], None] | None = None,
    ):
        self._available = available
        self._results = results
        self._error = error
        self._delay_ms = delay_ms
        self._on_search = on_search
        self.calls: list[WebSearchRequest] = []
        self.lock = threading.Lock()

    def is_available(self) -> bool:
        return self._available

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            available=self._available,
            provider="fake",
            detail="ok" if self._available else "unavailable",
        )

    def search(
        self,
        request: WebSearchRequest,
        cancellation_event,
    ) -> WebSearchResponse:
        with self.lock:
            self.calls.append(request)
        if self._on_search:
            self._on_search(request)
        if self._delay_ms:
            deadline = time.monotonic() + (self._delay_ms / 1000.0)
            while time.monotonic() < deadline:
                if cancellation_event is not None and cancellation_event.is_set():
                    raise WebSearchError(
                        SearchErrorCategory.CANCELED,
                        "Search canceled.",
                    )
                time.sleep(0.01)
        if cancellation_event is not None and cancellation_event.is_set():
            raise WebSearchError(SearchErrorCategory.CANCELED, "Search canceled.")
        if self._error is not None:
            raise self._error
        if not self._available:
            raise WebSearchError(
                SearchErrorCategory.MISSING_CONFIG,
                "Web Search is not configured, so I could not check current sources.",
            )
        results = list(self._results) if self._results is not None else [
            WebSearchResult(
                source_id="S1",
                title=f"Result for {request.query}",
                url="https://example.com/result",
                snippet=f"Evidence about {request.query}.",
                score=0.9,
                query=request.query,
            )
        ]
        # Re-number source IDs for this response.
        numbered = [
            WebSearchResult(
                source_id=f"S{i}",
                title=item.title,
                url=item.url,
                snippet=item.snippet,
                score=item.score,
                published_at=item.published_at,
                query=request.query,
            )
            for i, item in enumerate(results, start=1)
        ]
        return WebSearchResponse(
            query=request.query,
            results=numbered,
            provider="fake",
            provider_response_time_ms=self._delay_ms,
            empty=len(numbered) == 0,
        )
