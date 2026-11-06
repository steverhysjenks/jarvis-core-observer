"""Catalogue-derived ownership hints only; never playback identity or permission."""
import json
import os
from pathlib import Path
from uuid import UUID

from app.adapters.jellyfin import normalise

MAX_TITLES = 10000
MAX_INDEX_BYTES = 2 * 1024 * 1024
_last_good = None


def validate_index(value, user_id, library_id):
    if (not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1
            or UUID(value["user_id"]).hex != UUID(user_id).hex
            or UUID(value["library_id"]).hex != UUID(library_id).hex):
        raise ValueError("Invalid catalogue title index scope")
    titles = value.get("titles")
    if (not isinstance(titles, list) or not titles or len(titles) > MAX_TITLES
            or any(not isinstance(t, str) or not t.strip() or len(t) > 180
                   or any(ord(c) < 32 for c in t) for t in titles)):
        raise ValueError("Invalid catalogue titles")
    names = {normalise(t) for t in titles}
    # A subtitle prefix is an ownership hint, not an exact film match.
    # Thus an absent original remains video-owned/not_found, never a guessed sequel.
    names.update(normalise(t.split(":", 1)[0]) for t in titles if ":" in t)
    return frozenset(n for n in names if n)


def catalogue_titles():
    global _last_good
    scope = (os.getenv("VIDEO_TITLE_INDEX_FILE", ""), os.getenv("JELLYFIN_USER_ID", ""),
             os.getenv("JELLYFIN_MOVIE_LIBRARY_ID", ""))
    if not scope[0]:
        return frozenset()
    try:
        with Path(scope[0]).open("rb") as handle:
            data = handle.read(MAX_INDEX_BYTES + 1)
        if len(data) > MAX_INDEX_BYTES:
            raise ValueError("Oversized catalogue title index")
        names = validate_index(json.loads(data), *scope[1:])
        _last_good = scope, names
        return names
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        # Preserve previously established ownership on a damaged/replaced file.
        # Never reuse another user's/library's or another configured file's index.
        return _last_good[1] if _last_good and _last_good[0] == scope else frozenset()
