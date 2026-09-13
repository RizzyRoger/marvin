"""Provider-neutral web-search types and protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class SearchPurpose(str, Enum):
    GENERAL = "general"
    NEWS = "news"
    FINANCE = "finance"
    VERIFICATION = "verification"
    RECOMMENDATION = "recommendation"


class SearchDepth(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"


class SearchFreshness(str, Enum):
    ANY = "any"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class SearchDecision(str, Enum):
    REQUIRED = "required"
    ALLOWED = "allowed"
    NOT_NEEDED = "notNeeded"
    FORBIDDEN_BY_USER = "forbiddenByUser"
    UNAVAILABLE = "unavailable"


class SearchErrorCategory(str, Enum):
    EMPTY = "empty"
    TIMEOUT = "timeout"
    CANCELED = "canceled"
    MISSING_CONFIG = "missing_config"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    INVALID_REQUEST = "invalid_request"
    PROVIDER_OUTAGE = "provider_outage"
    MALFORMED = "malformed"
    INTERNAL = "internal"
    NETWORK = "network"


@dataclass(frozen=True)
class FreshnessFilter:
    relative: SearchFreshness = SearchFreshness.ANY
    start_date: str | None = None  # YYYY-MM-DD
    end_date: str | None = None


@dataclass
class WebSearchRequest:
    query: str
    purpose: SearchPurpose = SearchPurpose.GENERAL
    depth: SearchDepth = SearchDepth.BALANCED
    freshness: FreshnessFilter = field(default_factory=FreshnessFilter)
    include_domains: list[str] = field(default_factory=list)
    exclude_domains: list[str] = field(default_factory=list)
    max_results: int = 5
    locale_or_country: str | None = None
    turn_id: str = ""
    generation_id: str = ""
    tool_call_id: str = ""
    force_fresh: bool = False

    def cache_key_parts(self) -> tuple[Any, ...]:
        return (
            self.query.strip().lower(),
            self.purpose.value,
            self.depth.value,
            self.freshness.relative.value,
            self.freshness.start_date,
            self.freshness.end_date,
            tuple(sorted(d.lower() for d in self.include_domains)),
            tuple(sorted(d.lower() for d in self.exclude_domains)),
            self.max_results,
            (self.locale_or_country or "").lower(),
        )


@dataclass
class WebSearchResult:
    source_id: str
    title: str
    url: str
    snippet: str
    score: float = 0.0
    published_at: str | None = None
    query: str = ""


@dataclass
class WebSearchResponse:
    query: str
    results: list[WebSearchResult]
    provider: str
    received_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    provider_request_id: str | None = None
    provider_response_time_ms: int | None = None
    usage: dict[str, Any] | None = None
    empty: bool = False


@dataclass
class ProviderHealth:
    available: bool
    provider: str
    detail: str = ""


@dataclass
class WebSearchError(Exception):
    category: SearchErrorCategory
    message: str

    def __str__(self) -> str:
        return self.message


class WebSearchProvider(Protocol):
    """Provider-neutral search interface."""

    def is_available(self) -> bool: ...

    def search(
        self,
        request: WebSearchRequest,
        cancellation_event,
    ) -> WebSearchResponse: ...

    def health_check(self) -> ProviderHealth: ...
