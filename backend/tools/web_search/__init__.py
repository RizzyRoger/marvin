"""Web search public API for Marvin."""

from backend.tools.web_search.routing import (
    decide_web_search,
    looks_like_deferred_web_search,
    looks_like_invented_web_claim,
)
from backend.tools.web_search.sanitize import strip_urls_for_speech
from backend.tools.web_search.service import (
    TOOL_DEFINITION,
    dispatch_web_search_tool,
    get_provider,
    ground_assistant_reply,
    register_web_search_capability,
    run_planned_search,
    set_provider_for_tests,
    tools_for_web_search,
    user_facing_error,
    web_search_is_available,
    wrap_search_results,
)
from backend.tools.web_search.types import (
    SearchDecision,
    SearchErrorCategory,
    WebSearchError,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)
from backend.tools.web_search.providers.fake import FakeWebSearchProvider

__all__ = [
    "FakeWebSearchProvider",
    "SearchDecision",
    "SearchErrorCategory",
    "TOOL_DEFINITION",
    "WebSearchError",
    "WebSearchRequest",
    "WebSearchResponse",
    "WebSearchResult",
    "decide_web_search",
    "looks_like_deferred_web_search",
    "looks_like_invented_web_claim",
    "dispatch_web_search_tool",
    "get_provider",
    "ground_assistant_reply",
    "register_web_search_capability",
    "run_planned_search",
    "set_provider_for_tests",
    "strip_urls_for_speech",
    "tools_for_web_search",
    "user_facing_error",
    "web_search_is_available",
    "wrap_search_results",
]
