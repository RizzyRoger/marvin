"""Deterministic Spotify intent routing."""

from __future__ import annotations

import re

from backend.tools.spotify.types import SpotifyDecision

_EXPLICIT = re.compile(
    r"\b("
    r"spotify|"
    r"play(?:\s+(?:me|some|a|the|my))?|"
    r"un-?pause|"
    r"pause(?:\s+(?:the\s+)?(?:music|song|track|spotify))?|"
    r"resume(?:\s+(?:the\s+)?(?:music|song|track|spotify))?|"
    r"continue(?:\s+(?:the\s+|my\s+)?(?:music|song|track|spotify))?|"
    r"start(?:\s+(?:the\s+|my\s+)?(?:music|song|track))|"
    r"skip(?:\s+(?:this|the))?(?:\s+(?:song|track))?|"
    r"next(?:\s+(?:song|track))|"
    r"previous(?:\s+(?:song|track))?|"
    r"go back(?:\s+a\s+(?:song|track))?|"
    r"volume|"
    r"turn (?:it|the music|spotify) (?:up|down)|"
    r"what(?:['’]?s| is) playing|"
    r"now playing|"
    r"current(?:ly)? playing|"
    r"stop (?:the )?(?:music|song|track|spotify)|"
    r"put on\b|"
    r"queue\b"
    r")\b",
    re.I,
)

# Avoid treating plain "play" in non-music senses alone without more context —
# require music-ish cues OR spotify OR control verbs beyond bare play.
_MUSIC_CUE = re.compile(
    r"\b("
    r"song|track|album|playlist|artist|music|spotify|"
    r"on spotify|in spotify|"
    r"volume|pause|un-?pause|resume|continue|skip|next track|previous track|"
    r"what(?:['’]?s| is) playing|now playing"
    r")\b",
    re.I,
)

_BARE_PLAY = re.compile(
    r"^\s*play\b.+",
    re.I,
)

_BARE_PUT_ON = re.compile(
    r"\bput on\b.+\S",
    re.I,
)

# "unpause my song" / "continue the music" / "start my track"
_RESUME_CONTROL = re.compile(
    r"\b("
    r"un-?pause|"
    r"resume|"
    r"continue|"
    r"start(?:\s+(?:the\s+|my\s+)?(?:music|song|track))"
    r")\b.+\b(music|song|track|spotify)\b|"
    r"\b(music|song|track|spotify)\b.+\b(un-?pause|resume|continue)\b",
    re.I,
)


def decide_spotify(
    user_message: str,
    *,
    available: bool,
) -> tuple[SpotifyDecision, str]:
    text = (user_message or "").strip()
    if not text:
        return SpotifyDecision.NOT_NEEDED, "empty"
    if not available:
        if (
            (_EXPLICIT.search(text) and _MUSIC_CUE.search(text))
            or _BARE_PLAY.search(text)
            or _BARE_PUT_ON.search(text)
            or _RESUME_CONTROL.search(text)
        ):
            return SpotifyDecision.UNAVAILABLE, "spotify_unavailable"
        return SpotifyDecision.NOT_NEEDED, "unavailable_but_not_requested"
    if _MUSIC_CUE.search(text) and _EXPLICIT.search(text):
        return SpotifyDecision.REQUIRED, "explicit_spotify_or_music_control"
    if _RESUME_CONTROL.search(text):
        return SpotifyDecision.REQUIRED, "resume_control"
    if _BARE_PLAY.search(text) and len(text.split()) >= 2:
        # "play bohemian rhapsody" / "play some jazz"
        return SpotifyDecision.REQUIRED, "play_request"
    if _BARE_PUT_ON.search(text) and len(text.split()) >= 3:
        # "put on some jazz"
        return SpotifyDecision.REQUIRED, "put_on_request"
    return SpotifyDecision.NOT_NEEDED, "no_spotify_intent"


_DEFERRED_SPOTIFY_RE = re.compile(
    r"\b("
    r"let me play|i'?ll play|i will play|"
    r"playing that (?:now|for you)|"
    r"i'?ll (?:pause|skip|resume|unpause)|"
    r"let me (?:pause|skip|start|resume)|"
    r"i'?ll (?:put that on|queue)|"
    r"one (?:sec|second|moment).{0,40}\b(music|spotify|track|song)\b"
    r")\b",
    re.I,
)

_INVENTED_SPOTIFY_RE = re.compile(
    r"\b("
    r"now playing|currently playing|"
    r"i (?:put on|started|queued|paused|skipped)|"
    r"playing ['\"].+['\"]|"
    r"(?:track|song) (?:is|called) ['\"]?.+"
    r")\b",
    re.I,
)

_FALSE_FAILURE_RE = re.compile(
    r"\b("
    r"did not allow|doesn't allow|does not allow|"
    r"could(?:\s+no|\s*n['’]?t)|unable|failed|"
    r"could not (?:be )?reach(?:ed)?|"
    r"could not (?:reach|resume|pause|un-?pause|play|access|skip)|"
    r"can(?:not|['’]?t)\s+(?:reach|resume|pause|un-?pause|play|access|skip)|"
    r"unreachable|"
    r"wasn't able|was not able|"
    r"refused|inaccessible|unavailable"
    r")\b",
    re.I,
)

_SWITCHED_TITLE_RE = re.compile(
    r"\b("
    r"instead of|rather than|"
    r"played .+ instead|"
    r"playing .+ instead"
    r")\b",
    re.I,
)

_SPOTIFY_SUCCESS_RE = re.compile(
    r"^\s*(Resumed playback|Paused|Skipped to the next track|"
    r"Went back to the previous track|Volume set to \d+ percent|"
    r"Playing .+)\.\s*$",
    re.I,
)

_SPOTIFY_DATA_RE = re.compile(
    r"<spotify_data[^>]*>\s*(.*?)\s*</spotify_data>",
    re.I | re.S,
)


def looks_like_deferred_spotify(reply: str) -> bool:
    """True when the model stalls with a promise to control Spotify."""
    return bool(_DEFERRED_SPOTIFY_RE.search(reply or ""))


def looks_like_invented_spotify_claim(reply: str) -> bool:
    """Heuristic: reply claims playback state without Spotify tool evidence."""
    return bool(_INVENTED_SPOTIFY_RE.search(reply or ""))


def looks_like_false_spotify_failure(reply: str) -> bool:
    """True when the model claims Spotify failed despite a successful tool result."""
    return bool(_FALSE_FAILURE_RE.search(reply or ""))


def looks_like_switched_spotify_title(reply: str) -> bool:
    """True when the model claims it played a substitute title."""
    return bool(_SWITCHED_TITLE_RE.search(reply or ""))


def unwrap_spotify_tool_text(result: str) -> str:
    """Extract the spoken confirmation from a wrapped Spotify tool result."""
    text = (result or "").strip()
    match = _SPOTIFY_DATA_RE.search(text)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return text


def is_spotify_success_text(text: str) -> bool:
    return bool(_SPOTIFY_SUCCESS_RE.match((text or "").strip()))


def prefer_spotify_tool_truth(reply: str, tool_texts: list[str]) -> str | None:
    """
    If tools succeeded but the model denied success or invented a substitute,
    return the last successful tool confirmation instead.
    """
    successes = [t for t in tool_texts if is_spotify_success_text(t)]
    if not successes:
        return None
    last = successes[-1]
    if looks_like_false_spotify_failure(reply) or looks_like_switched_spotify_title(
        reply
    ):
        return last

    # Short playback confirmations: prefer tool text unless the reply clearly
    # affirms the same outcome (models often invent "could not be reached").
    reply_l = (reply or "").lower().strip()
    last_l = last.lower().rstrip(".")
    short_controls = (
        "resumed playback",
        "paused",
        "skipped to the next track",
        "went back to the previous track",
    )
    if last_l in short_controls or last_l.startswith("volume set to"):
        if last_l not in reply_l and not reply_l.startswith(last_l):
            # Affirmative paraphrases that still count as success.
            affirm = False
            if last_l == "resumed playback" and re.search(
                r"\b(resumed|unpaused|playing again|started again)\b", reply_l
            ):
                affirm = True
            elif last_l == "paused" and re.search(r"\bpaused\b", reply_l):
                affirm = True
            elif "skipped" in last_l and re.search(r"\b(skipped|next track)\b", reply_l):
                affirm = True
            elif "went back" in last_l and re.search(
                r"\b(previous|went back|last track)\b", reply_l
            ):
                affirm = True
            elif last_l.startswith("volume set to") and "volume" in reply_l:
                affirm = True
            if not affirm:
                return last

    # Also prefer tool text when the model invents a different "Playing …" line.
    if is_spotify_success_text(last) and last.lower().startswith("playing"):
        tool_body = last[len("Playing ") :].rstrip(".").lower()
        if tool_body and tool_body not in reply_l and "playing" in reply_l:
            return last
    return None
