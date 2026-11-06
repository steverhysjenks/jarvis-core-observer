"""Deterministic movie grammar with scoped catalogue-derived bare-title ownership."""
from dataclasses import dataclass
import re
from app.adapters.jellyfin import normalise
from app.video.title_index import catalogue_titles


@dataclass(frozen=True)
class VideoIntent:
    operation: str
    title: str = ""
    year: int | None = None
    room: str | None = None


def recognise(text: str) -> VideoIntent | None:
    text = re.sub(r"^(?:ask jarvis to\s+|jarvis[, :]\s*)", "", text.strip(), flags=re.I)
    # Strip only a leading polite play request. Title data and ownership rules
    # below are unchanged; unknown bare names do not become film requests.
    text = re.sub(r"^(?:can|could)\s+you\s+(?=play\s)", "", text, flags=re.I)
    text = text.rstrip(".!?").strip()
    if text.lower() == "confirm video takeover":
        return VideoIntent("confirm")
    if text.lower() == "cancel video takeover":
        return VideoIntent("cancel")
    match = re.fullmatch(r"(?:play\s+(.+)|get\s+(.+?)\s+ready(?:\s+(.+))?)", text, re.I | re.S)
    if not match:
        return None
    operation = "play" if match[1] else "prepare"
    body = match[1] or match[2]
    suffix = match[3]
    if re.match(r"(?:the\s+)?(?:song|track|album|artist|playlist|music)\b", body, re.I):
        return None
    # Only a terminal television destination is syntax; "on" inside a title is data.
    target = re.fullmatch(r"(.+)\s+(on\s+(?:the\s+)?(?:(?:[\w-]+\s+){0,5})?(?:tv|television))", body, re.I | re.S)
    if target:
        body, suffix = target[1], target[2]
    explicit_movie = bool(re.match(r"(?:the\s+)?(?:movie|film)\s+", body, re.I))
    body = re.sub(r"^(?:the\s+)?(?:movie|film)\s+", "", body, flags=re.I)
    year_match = re.fullmatch(r"(.+?)\s+(?:\((\d{4})\)|(\d{4}))", body)
    year = int(year_match[2] or year_match[3]) if year_match else None
    title = year_match[1].strip() if year_match else body.strip()
    if suffix and not re.search(r"\b(?:tv|television)\b", suffix, re.I) and not explicit_movie:
        return None
    if not (suffix or explicit_movie or normalise(title) in catalogue_titles()):
        return None
    # Claim explicit malformed video requests so they cannot become device inference.
    if (not title or len(title) > 180 or re.search(r"[;\x00-\x1f/\\]|\b(?:https?|file|infuse|data|javascript):|www\.|\b(?:and then|then|and play|and turn)\b", title, re.I)
            or (year is not None and not 1888 <= year <= 2100)):
        return VideoIntent("invalid")
    room = None
    if suffix:
        room_match = re.fullmatch(r"on\s+(?:the\s+)?(?:(.+?)\s+)?(?:tv|television)", suffix, re.I)
        if not room_match:
            return VideoIntent("invalid")
        room = room_match[1].strip().casefold() if room_match[1] else "living room"
    return VideoIntent(operation, title, year, room)
