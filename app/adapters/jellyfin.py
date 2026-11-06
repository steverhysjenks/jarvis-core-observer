"""GET-only, bounded movie catalogue boundary. No discovery or playback API."""
from dataclasses import asdict, dataclass
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

LIMIT = 12
MAX_BYTES = 262144


class CatalogueUnavailable(Exception):
    """Sanitised failure; never include upstream bodies, URLs or credentials."""


def normalise(title):
    return " ".join(re.findall(r"\w+", title.casefold()))


@dataclass(frozen=True)
class Movie:
    item_id: str
    title: str
    year: int
    tmdb_id: str

    def as_dict(self):
        return asdict(self)


def resolve(payload, title, year=None):
    """Exact title/year only. Duplicate editions remain ambiguous, even same TMDB."""
    if not isinstance(payload, dict) or not isinstance(payload.get("Items"), list):
        raise CatalogueUnavailable()
    items, count = payload["Items"], payload.get("TotalRecordCount")
    if (len(items) > LIMIT or type(count) is not int or count < len(items)
            or payload.get("StartIndex", 0) != 0 or any(not isinstance(x, dict) for x in items)):
        raise CatalogueUnavailable()
    if count > len(items) or len(items) == LIMIT:
        raise CatalogueUnavailable()
    matches = [x for x in items if x.get("Type") == "Movie"
               and isinstance(x.get("Name"), str) and normalise(x["Name"]) == normalise(title)
               and (year is None or x.get("ProductionYear") == year)]
    if not matches:
        return "not_found", None, []
    movies = [_validated_movie(item) for item in matches]
    if len(movies) != 1:
        return "ambiguous", None, [{"title": m.title, "year": m.year} for m in movies[:5]]
    return "resolved", movies[0], []


def _validated_movie(item):
    try:
        identity = UUID(item["Id"]).hex
        tmdb = item["ProviderIds"]["Tmdb"]
        if not isinstance(tmdb, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", tmdb):
            raise ValueError()
        if type(item["ProductionYear"]) is not int or not 1888 <= item["ProductionYear"] <= 2100:
            raise ValueError()
        if item.get("LocationType") != "FileSystem" or item.get("IsPlaceHolder", False) is not False:
            raise ValueError()
        sources = item.get("MediaSources")
        if not isinstance(sources, list) or not sources or not all(isinstance(x, dict) for x in sources):
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise CatalogueUnavailable() from None
    return Movie(identity, item["Name"][:180], item["ProductionYear"], tmdb)


class JellyfinClient:
    async def _items(self, options, max_bytes=MAX_BYTES):
        base = os.environ.get("JELLYFIN_URL", "").rstrip("/")
        token_file = os.environ.get("JELLYFIN_TOKEN_FILE", "")
        try:
            token = (Path(token_file).read_text(encoding="utf-8").strip() if token_file
                     else os.environ.get("JELLYFIN_TOKEN", ""))
        except (OSError, UnicodeError, ValueError):
            raise CatalogueUnavailable() from None
        user = os.environ.get("JELLYFIN_USER_ID", "")
        library = os.environ.get("JELLYFIN_MOVIE_LIBRARY_ID", "")
        try:
            parsed = urlsplit(base)
        except ValueError:
            raise CatalogueUnavailable() from None
        # Deployment-owned configuration, never a request URL. No plaintext token transport.
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not token):
            raise CatalogueUnavailable()
        try:
            user, library = UUID(user).hex, UUID(library).hex
        except (ValueError, AttributeError):
            raise CatalogueUnavailable() from None
        params = {**options, "UserId": user, "ParentId": library, "Recursive": "true",
                  "IncludeItemTypes": "Movie", "StartIndex": 0, "EnableImages": "false",
                  "EnableUserData": "false", "EnableTotalRecordCount": "true"}
        try:
            async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False) as client:
                async with client.stream("GET", base + "/Items", params=params,
                                         headers={"Authorization": 'MediaBrowser Token="' + quote(token, safe="") + '"'}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise CatalogueUnavailable()
            return json.loads(body), {"user_id": user, "library_id": library}
        except (httpx.HTTPError, ValueError, TypeError):
            raise CatalogueUnavailable() from None

    async def lookup(self, title, year=None):
        options = {"SearchTerm": title, "Limit": LIMIT, "Fields": "ProviderIds,MediaSources"}
        if year is not None:
            options["Years"] = str(year)
        payload, _ = await self._items(options)
        return resolve(payload, title, year)

    async def title_index(self):
        """Explicit operator refresh: one bounded complete title listing, no pagination."""
        from app.video.title_index import MAX_TITLES, validate_index
        payload, scope = await self._items({"Limit": MAX_TITLES + 1}, 8 * 1024 * 1024)
        try:
            items, count = payload["Items"], payload["TotalRecordCount"]
            if (not isinstance(items, list) or type(count) is not int or count != len(items)
                    or not 0 < count <= MAX_TITLES or payload.get("StartIndex", 0) != 0
                    or any(not isinstance(x, dict) or x.get("Type") != "Movie" for x in items)):
                raise ValueError()
            value = {"schema": 1, **scope, "titles": [x["Name"] for x in items]}
            validate_index(value, scope["user_id"], scope["library_id"])
            return value
        except (KeyError, ValueError, TypeError, AttributeError):
            raise CatalogueUnavailable() from None


jellyfin_client = JellyfinClient()
