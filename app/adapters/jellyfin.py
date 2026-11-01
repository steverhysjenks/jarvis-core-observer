"""GET-only, bounded movie catalogue boundary. No discovery or playback API."""
from dataclasses import asdict, dataclass
import json
import os
import re
from urllib.parse import urlsplit
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
        return "ambiguous", None, []
    matches = [x for x in items if x.get("Type") == "Movie"
               and isinstance(x.get("Name"), str) and normalise(x["Name"]) == normalise(title)
               and (year is None or x.get("ProductionYear") == year)]
    if not matches:
        return "not_found", None, []
    choices = [{"title": x["Name"][:180], "year": x.get("ProductionYear") if type(x.get("ProductionYear")) is int else None}
               for x in matches[:5]]
    if len(matches) != 1:
        return "ambiguous", None, choices
    item = matches[0]
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
    return "resolved", Movie(identity, item["Name"][:180], item["ProductionYear"], tmdb), []


class JellyfinClient:
    async def lookup(self, title, year=None):
        base = os.environ.get("JELLYFIN_URL", "").rstrip("/")
        token = os.environ.get("JELLYFIN_TOKEN", "")
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
        params = {"UserId": user, "ParentId": library, "Recursive": "true",
                  "IncludeItemTypes": "Movie", "SearchTerm": title, "Limit": LIMIT,
                  "StartIndex": 0, "Fields": "ProviderIds,MediaSources", "EnableImages": "false",
                  "EnableUserData": "false", "EnableTotalRecordCount": "true"}
        if year is not None:
            params["Years"] = str(year)
        try:
            async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False) as client:
                async with client.stream("GET", base + "/Items", params=params,
                                         headers={"X-Emby-Token": token}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise CatalogueUnavailable()
            return resolve(json.loads(body), title, year)
        except (httpx.HTTPError, ValueError, TypeError):
            raise CatalogueUnavailable() from None


jellyfin_client = JellyfinClient()
