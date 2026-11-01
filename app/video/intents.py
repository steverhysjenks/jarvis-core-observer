"""Deterministic movie grammar. Bare play stays with music unless allowlisted."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class VideoIntent:
    operation: str
    title: str = ""
    year: int | None = None
    room: str | None = None


# Recognition aliases only: never catalogue IDs or evidence of availability.
BARE_MOVIES = {"forrest gump", "kpop demon hunters"}


def recognise(text: str) -> VideoIntent | None:
    text = re.sub(r"^(?:ask jarvis to\s+|jarvis[, :]\s*)", "", text.strip(), flags=re.I)
    text = text.rstrip(".!?").strip()
    if text.lower() == "confirm video takeover":
        return VideoIntent("confirm")
    if text.lower() == "cancel video takeover":
        return VideoIntent("cancel")
    match = re.fullmatch(r"(?:play\s+(.+)|get\s+(.+?)\s+ready(?:\s+(.+))?)", text, re.I)
    if not match:
        return None
    operation = "play" if match[1] else "prepare"
    body = match[1] or match[2]
    suffix = match[3]
    target = re.fullmatch(r"(.+?)\s+on\s+(?:the\s+)?(.+?)", body, re.I)
    if target:
        body, suffix = target[1], "on " + target[2]
    explicit_movie = bool(re.match(r"(?:the\s+)?(?:movie|film)\s+", body, re.I))
    body = re.sub(r"^(?:the\s+)?(?:movie|film)\s+", "", body, flags=re.I)
    year_match = re.fullmatch(r"(.+?)\s*\((\d{4})\)", body)
    year = int(year_match[2]) if year_match else None
    title = year_match[1].strip() if year_match else body.strip()
    if suffix and not re.search(r"\b(?:tv|television)\b", suffix, re.I) and not explicit_movie:
        return None
    if not (suffix or explicit_movie or operation == "prepare" or title.casefold() in BARE_MOVIES):
        return None
    # Claim explicit malformed video requests so they cannot become device inference.
    if (not title or len(title) > 180 or re.search(r"[;\r\n.!?/:\\]|\b(?:and then|then|and play|and turn)\b", title, re.I)
            or (year is not None and not 1888 <= year <= 2100)):
        return VideoIntent("invalid")
    room = None
    if suffix:
        room_match = re.fullmatch(r"on\s+(?:the\s+)?(?:(.+?)\s+)?(?:tv|television)", suffix, re.I)
        if not room_match:
            return VideoIntent("invalid")
        room = room_match[1].strip().casefold() if room_match[1] else "living room"
    return VideoIntent(operation, title, year, room)
