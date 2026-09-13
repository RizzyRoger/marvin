"""Thin Spotify Web API client for Connect playback control."""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.tools.spotify.auth import spotify_api_request
from backend.tools.spotify.types import SpotifyError, SpotifyErrorCategory

logger = logging.getLogger(__name__)

_PLAYBACK_START_HINT = (
    "Spotify device is available but playback could not start. "
    "Click Play once in the Spotify app, then try again."
)

_QUERY_NOISE = re.compile(
    r"\b("
    r"play|put on|please|the|a|an|my|album|albums|playlist|playlists|"
    r"song|songs|track|tracks|artist|by|on spotify|spotify"
    r")\b",
    re.I,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def get_devices() -> list[dict[str, Any]]:
    data = spotify_api_request("GET", "/me/player/devices")
    return list(data.get("devices") or [])


def _choose_device(devices: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer active, then computer, then first listed device."""
    active = next((d for d in devices if d.get("is_active")), None)
    if active:
        return active
    computer = next(
        (d for d in devices if str(d.get("type") or "").lower() == "computer"),
        None,
    )
    if computer:
        return computer
    return devices[0]


def ensure_active_device() -> str:
    """
    Return a concrete Spotify Connect device id.

    Raises NO_DEVICE only when the devices list is empty.
    """
    devices = get_devices()
    if not devices:
        raise SpotifyError(
            SpotifyErrorCategory.NO_DEVICE,
            "No Spotify device is available. Open Spotify on a phone or computer first.",
        )
    chosen = _choose_device(devices)
    device_id = str(chosen.get("id") or "").strip()
    if not device_id:
        raise SpotifyError(
            SpotifyErrorCategory.NO_DEVICE,
            "No Spotify device is available. Open Spotify on a phone or computer first.",
        )
    if not chosen.get("is_active"):
        # Wake / transfer without forcing play; callers that need audio use play_on_device.
        try:
            spotify_api_request(
                "PUT",
                "/me/player",
                json_body={"device_ids": [device_id], "play": False},
            )
            logger.info(
                "SPOTIFY: transferred_playback device=%s type=%s",
                chosen.get("name"),
                chosen.get("type"),
            )
        except SpotifyError as exc:
            # Transfer can 404 when idle; play_on_device will still pass device_id.
            logger.info(
                "SPOTIFY: transfer skipped category=%s message=%s",
                exc.category.value,
                exc.message,
            )
    return device_id


def _player_params(device_id: str | None) -> dict[str, Any] | None:
    if device_id:
        return {"device_id": device_id}
    return None


def play_on_device(
    device_id: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> None:
    """
    Start or resume playback on a specific device.

    Retries once after refreshing the device list if Spotify returns a player 404.
    """
    body = json_body if json_body is not None else {}
    try:
        spotify_api_request(
            "PUT",
            "/me/player/play",
            params=_player_params(device_id),
            json_body=body,
        )
        return
    except SpotifyError as first:
        if first.category != SpotifyErrorCategory.NO_DEVICE:
            raise
        logger.info("SPOTIFY: play 404; refreshing devices and retrying")

    devices = get_devices()
    if not devices:
        raise SpotifyError(
            SpotifyErrorCategory.NO_DEVICE,
            "No Spotify device is available. Open Spotify on a phone or computer first.",
        )
    retry_id = str(_choose_device(devices).get("id") or "").strip() or device_id
    try:
        spotify_api_request(
            "PUT",
            "/me/player/play",
            params=_player_params(retry_id),
            json_body=body,
        )
    except SpotifyError as second:
        if second.category == SpotifyErrorCategory.NO_DEVICE:
            raise SpotifyError(
                SpotifyErrorCategory.API,
                _PLAYBACK_START_HINT,
            ) from second
        raise


def get_now_playing() -> dict[str, Any]:
    data = spotify_api_request("GET", "/me/player/currently-playing")
    if not data:
        # Fall back to player state when currently-playing is empty.
        data = spotify_api_request("GET", "/me/player") or {}
    item = data.get("item") or {}
    artists = ", ".join(
        a.get("name") for a in (item.get("artists") or []) if a.get("name")
    )
    return {
        "is_playing": bool(data.get("is_playing")),
        "name": item.get("name") or "",
        "artists": artists,
        "album": (item.get("album") or {}).get("name") or "",
        "device": ((data.get("device") or {}).get("name") or ""),
        "uri": item.get("uri") or "",
    }


def playback_action(action: str, *, volume_percent: int | None = None) -> str:
    device_id = ensure_active_device()
    action = (action or "").strip().lower()
    if action in {"play", "resume"}:
        play_on_device(device_id)
        return "Resumed playback."
    if action == "pause":
        try:
            spotify_api_request(
                "PUT",
                "/me/player/pause",
                params=_player_params(device_id),
            )
        except SpotifyError as exc:
            if exc.category == SpotifyErrorCategory.NO_DEVICE and get_devices():
                raise SpotifyError(
                    SpotifyErrorCategory.API,
                    _PLAYBACK_START_HINT,
                ) from exc
            raise
        return "Paused."
    if action in {"next", "skip"}:
        spotify_api_request(
            "POST",
            "/me/player/next",
            params=_player_params(device_id),
        )
        return "Skipped to the next track."
    if action in {"previous", "back"}:
        spotify_api_request(
            "POST",
            "/me/player/previous",
            params=_player_params(device_id),
        )
        return "Went back to the previous track."
    if action == "volume":
        if volume_percent is None:
            raise SpotifyError(
                SpotifyErrorCategory.API,
                "A volume percent between 0 and 100 is required.",
            )
        level = max(0, min(100, int(volume_percent)))
        spotify_api_request(
            "PUT",
            "/me/player/volume",
            params={"volume_percent": level, "device_id": device_id},
        )
        return f"Volume set to {level} percent."
    raise SpotifyError(
        SpotifyErrorCategory.API,
        f"Unsupported playback action: {action}",
    )


def _normalize_title(value: str) -> str:
    return _NON_ALNUM.sub("", (value or "").lower())


def clean_search_query(query: str) -> str:
    text = _QUERY_NOISE.sub(" ", query or "")
    return re.sub(r"\s+", " ", text).strip() or (query or "").strip()


def title_match_score(query: str, name: str) -> int:
    """Higher is better; 0 means too weak to play as a match."""
    from difflib import SequenceMatcher

    cleaned = clean_search_query(query) or query
    nq = _normalize_title(cleaned)
    nn = _normalize_title(name)
    if not nq or not nn:
        return 0
    if nq == nn:
        return 100
    if nq in nn or nn in nq:
        return 85
    ratio = SequenceMatcher(None, nq, nn).ratio()
    if ratio >= 0.92:
        return 90
    if ratio >= 0.82:
        return 75
    q_tokens = [t for t in re.split(r"\s+", cleaned.lower()) if t]
    n_tokens = [t for t in re.split(r"\s+", (name or "").lower()) if t]
    if q_tokens and all(
        any(qt in nt or nt in qt or SequenceMatcher(None, qt, nt).ratio() >= 0.85 for nt in n_tokens)
        for qt in q_tokens
    ):
        return 70
    # Shared long token
    for qt in q_tokens:
        if len(qt) >= 4 and any(qt in nt or nt in qt for nt in n_tokens):
            return 40
    return 0


def _market_ok(item: dict[str, Any], market: str | None) -> bool:
    if not market:
        return True
    markets = item.get("available_markets")
    if markets is None:
        return True
    if not markets:
        # Empty list usually means not playable in common catalog views.
        return False
    return market.upper() in {str(m).upper() for m in markets}


def _user_market() -> str | None:
    try:
        profile = spotify_api_request("GET", "/me")
        country = str((profile or {}).get("country") or "").strip().upper()
        return country or None
    except SpotifyError:
        return None


def list_user_playlists(*, limit: int = 50) -> list[dict[str, Any]]:
    """Return the current user's playlists (paginated)."""
    items: list[dict[str, Any]] = []
    offset = 0
    page_size = min(50, max(1, limit))
    while True:
        data = spotify_api_request(
            "GET",
            "/me/playlists",
            params={"limit": page_size, "offset": offset},
        )
        batch = list(data.get("items") or [])
        items.extend(batch)
        if len(batch) < page_size or len(items) >= 200:
            break
        offset += page_size
    return items


def find_user_playlist(query: str) -> dict[str, Any] | None:
    """Best title match among the user's own playlists, or None."""
    cleaned = clean_search_query(query) or (query or "").strip()
    if not cleaned:
        return None
    try:
        playlists = list_user_playlists()
    except SpotifyError as exc:
        # Missing playlist scope → caller may fall back to public search.
        logger.info(
            "SPOTIFY: user playlists unavailable category=%s message=%s",
            exc.category.value,
            exc.message,
        )
        raise
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in playlists:
        name = str(item.get("name") or "")
        score = title_match_score(cleaned, name)
        if score >= 70:
            ranked.append((score, item))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: (-pair[0], pair[1].get("name") or ""))
    return ranked[0][1]


def get_user_top_affinity(*, time_range: str = "medium_term") -> dict[str, Any]:
    """Fetch top artists/tracks for ranking play intent (best-effort)."""
    artists: list[dict[str, Any]] = []
    tracks: list[dict[str, Any]] = []
    try:
        data = spotify_api_request(
            "GET",
            "/me/top/artists",
            params={"limit": 30, "time_range": time_range},
        )
        artists = [a for a in (data.get("items") or []) if a and a.get("id")]
    except SpotifyError as exc:
        logger.info(
            "SPOTIFY: top artists unavailable category=%s",
            exc.category.value,
        )
    try:
        data = spotify_api_request(
            "GET",
            "/me/top/tracks",
            params={"limit": 30, "time_range": time_range},
        )
        tracks = [t for t in (data.get("items") or []) if t and t.get("id")]
    except SpotifyError as exc:
        logger.info(
            "SPOTIFY: top tracks unavailable category=%s",
            exc.category.value,
        )
    return {
        "artist_ids": {str(a.get("id")) for a in artists},
        "artist_names": {
            str(a.get("name") or "").strip().lower() for a in artists if a.get("name")
        },
        "track_ids": {str(t.get("id")) for t in tracks},
        "album_ids": {
            str((t.get("album") or {}).get("id"))
            for t in tracks
            if (t.get("album") or {}).get("id")
        },
        "album_names": {
            str((t.get("album") or {}).get("name") or "").strip().lower()
            for t in tracks
            if (t.get("album") or {}).get("name")
        },
    }


def _affinity_bonus(
    item: dict[str, Any],
    search_type: str,
    affinity: dict[str, Any],
) -> int:
    bonus = 0
    if search_type == "artist":
        if str(item.get("id") or "") in affinity.get("artist_ids", set()):
            bonus += 40
        name = str(item.get("name") or "").strip().lower()
        if name and name in affinity.get("artist_names", set()):
            bonus += 25
    elif search_type == "album":
        if str(item.get("id") or "") in affinity.get("album_ids", set()):
            bonus += 45
        name = str(item.get("name") or "").strip().lower()
        if name and name in affinity.get("album_names", set()):
            bonus += 35
        for artist in item.get("artists") or []:
            aid = str(artist.get("id") or "")
            aname = str(artist.get("name") or "").strip().lower()
            if aid and aid in affinity.get("artist_ids", set()):
                bonus += 30
            elif aname and aname in affinity.get("artist_names", set()):
                bonus += 20
    elif search_type == "track":
        if str(item.get("id") or "") in affinity.get("track_ids", set()):
            bonus += 35
        album = item.get("album") or {}
        if str(album.get("id") or "") in affinity.get("album_ids", set()):
            bonus += 20
        for artist in item.get("artists") or []:
            aid = str(artist.get("id") or "")
            aname = str(artist.get("name") or "").strip().lower()
            if aid and aid in affinity.get("artist_ids", set()):
                bonus += 25
            elif aname and aname in affinity.get("artist_names", set()):
                bonus += 15
    return bonus


def _rank_search_items(
    query: str,
    items: list[dict[str, Any]],
    *,
    market: str | None,
    min_score: int = 70,
    search_type: str = "track",
    affinity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    affinity = affinity or {}
    ranked: list[tuple[int, int, int, dict[str, Any]]] = []
    for item in items:
        name = str(item.get("name") or "")
        score = title_match_score(query, name)
        if score < min_score:
            continue
        market_bonus = 1 if _market_ok(item, market) else 0
        affinity_bonus = _affinity_bonus(item, search_type, affinity)
        ranked.append((score + affinity_bonus, affinity_bonus, market_bonus, item))
    ranked.sort(
        key=lambda row: (-row[0], -row[1], -row[2], row[3].get("name") or "")
    )
    preferred = [item for _total, _aff, ok, item in ranked if ok]
    if preferred:
        return preferred
    return [item for _total, _aff, _ok, item in ranked]


def _play_item(device_id: str, item: dict[str, Any], search_type: str) -> str:
    uri = item.get("uri")
    name = item.get("name") or "that"
    if not uri:
        raise SpotifyError(
            SpotifyErrorCategory.API,
            f"Spotify returned a {search_type} without a playable URI.",
        )
    if search_type == "track":
        artists = ", ".join(
            a.get("name") for a in (item.get("artists") or []) if a.get("name")
        )
        play_on_device(device_id, json_body={"uris": [uri]})
        label = f"{name} by {artists}" if artists else name
        return f"Playing {label}."
    if search_type == "artist":
        play_on_device(device_id, json_body={"context_uri": uri})
        return f"Playing music by {name}."
    if search_type == "playlist":
        play_on_device(device_id, json_body={"context_uri": uri})
        return f"Playing your playlist {name}." if item.get("_from_library") else f"Playing {name}."
    play_on_device(device_id, json_body={"context_uri": uri})
    return f"Playing the album {name}." if search_type == "album" else f"Playing {name}."


def search_and_play(query: str, *, kind: str = "auto") -> str:
    q = (query or "").strip()
    if not q:
        raise SpotifyError(SpotifyErrorCategory.API, "A search query is required.")
    device_id = ensure_active_device()
    cleaned = clean_search_query(q) or q
    requested = (kind or "auto").lower().strip()
    if requested not in {"track", "album", "playlist", "artist", "auto"}:
        requested = "auto"

    if requested == "playlist":
        try:
            owned = find_user_playlist(cleaned)
        except SpotifyError as exc:
            if exc.category in {
                SpotifyErrorCategory.AUTH,
                SpotifyErrorCategory.API,
                SpotifyErrorCategory.PREMIUM_REQUIRED,
            }:
                owned = None
                logger.info("SPOTIFY: falling back to public playlist search")
            else:
                raise
        if owned and owned.get("uri"):
            owned = {**owned, "_from_library": True}
            try:
                return _play_item(device_id, owned, "playlist")
            except SpotifyError:
                logger.info(
                    "SPOTIFY: library playlist play failed name=%s",
                    owned.get("name"),
                )

    market = _user_market()
    affinity = get_user_top_affinity()
    type_order = (
        ["album", "artist", "track"]
        if requested == "auto"
        else [requested]
    )

    scored: list[tuple[int, str, dict[str, Any]]] = []
    for search_type in type_order:
        params: dict[str, Any] = {"q": cleaned, "type": search_type, "limit": 10}
        if market:
            params["market"] = market
        try:
            data = spotify_api_request("GET", "/search", params=params)
        except SpotifyError:
            continue
        bucket = [
            item
            for item in list((data.get(f"{search_type}s") or {}).get("items") or [])
            if item and item.get("uri")
        ]
        if not bucket:
            continue
        min_score = 40 if search_type == "artist" else 70
        candidates = _rank_search_items(
            cleaned,
            bucket,
            market=market,
            min_score=min_score,
            search_type=search_type,
            affinity=affinity,
        )
        for rank_i, item in enumerate(candidates[:5]):
            name = str(item.get("name") or "")
            base = title_match_score(cleaned, name)
            aff = _affinity_bonus(item, search_type, affinity)
            type_bias = 8 if search_type == "album" and aff >= 20 else 0
            if search_type == "artist" and aff >= 25:
                type_bias = 5
            scored.append((base + aff + type_bias - rank_i, search_type, item))

    if not scored and requested == "playlist":
        params = {"q": cleaned, "type": "playlist", "limit": 10}
        if market:
            params["market"] = market
        data = spotify_api_request("GET", "/search", params=params)
        bucket = [
            item
            for item in list((data.get("playlists") or {}).get("items") or [])
            if item and item.get("uri")
        ]
        for item in _rank_search_items(
            cleaned, bucket, market=market, min_score=70, search_type="playlist"
        ):
            scored.append(
                (title_match_score(cleaned, str(item.get("name") or "")), "playlist", item)
            )

    if not scored:
        raise SpotifyError(
            SpotifyErrorCategory.API,
            f"No Spotify match for “{cleaned}”. Try a more specific name.",
        )

    scored.sort(key=lambda row: (-row[0], row[1], row[2].get("name") or ""))
    last_error: SpotifyError | None = None
    attempted_names: list[str] = []
    for total, search_type, item in scored:
        name = str(item.get("name") or "")
        if attempted_names and title_match_score(attempted_names[0], name) < 70:
            if title_match_score(cleaned, name) < 70:
                continue
        attempted_names.append(name)
        try:
            logger.info(
                "SPOTIFY: playing type=%s name=%s score=%s",
                search_type,
                name,
                total,
            )
            return _play_item(device_id, item, search_type)
        except SpotifyError as exc:
            last_error = exc
            logger.info(
                "SPOTIFY: play candidate failed type=%s name=%s category=%s",
                search_type,
                name,
                exc.category.value,
            )
            continue

    if last_error and last_error.category == SpotifyErrorCategory.NO_DEVICE:
        raise last_error
    label = attempted_names[0] if attempted_names else cleaned
    raise SpotifyError(
        SpotifyErrorCategory.API,
        f"Could not play “{label}”. It may be unavailable in your Spotify market.",
    )
