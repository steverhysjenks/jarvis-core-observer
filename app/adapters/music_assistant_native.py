from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


MAX_NATIVE_RESULTS = 100


class MusicAssistantNativeError(RuntimeError):
    """Native Music Assistant catalogue request failed."""


@dataclass(frozen=True)
class NativeTrack:
    item_id: str
    uri: str
    name: str
    artist: str | None
    album: str | None
    year: int | None
    genres: tuple[str, ...]
    favorite: bool


@dataclass(frozen=True)
class NativeGenre:
    item_id: int
    name: str


class MusicAssistantNativeAdapter:
    """
    Bounded read-only access to the Music Assistant native API.

    This adapter is catalogue-only. Playback remains behind the
    existing Home Assistant Music Assistant adapter.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token

    async def _command(
        self,
        command: str,
        args: dict[str, Any],
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "message_id": "jarvis-core",
            "command": command,
            "args": args,
        }

        try:
            async with httpx.AsyncClient(
                timeout=10.0
            ) as client:
                response = await client.post(
                    f"{self.base_url}/api",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

        except (
            httpx.HTTPError,
            ValueError,
        ) as exc:
            raise MusicAssistantNativeError(
                f"Music Assistant request failed: {command}"
            ) from exc

        # MA may return either the command result directly or
        # a message envelope depending on API transport/version.
        if isinstance(data, dict):
            if data.get("error"):
                raise MusicAssistantNativeError(
                    f"Music Assistant command failed: "
                    f"{command}: {data['error']}"
                )

            if "result" in data:
                return data["result"]

        return data

    async def genres(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[NativeGenre]:
        safe_limit = max(
            1,
            min(int(limit), MAX_NATIVE_RESULTS),
        )

        args: dict[str, Any] = {
            "limit": safe_limit,
            "offset": 0,
            "order_by": "name",
            "summary": False,
            "kwargs": {},
            "media_type": "track",
        }

        if search:
            args["search"] = search.strip()

        raw = await self._command(
            "music/genres/library_items",
            args,
        )

        if not isinstance(raw, list):
            return []

        genres: list[NativeGenre] = []

        for item in raw:
            if not isinstance(item, dict):
                continue

            item_id = item.get("item_id")
            name = item.get("name")

            if item_id is None or not name:
                continue

            try:
                numeric_id = int(item_id)
            except (TypeError, ValueError):
                continue

            genres.append(
                NativeGenre(
                    item_id=numeric_id,
                    name=str(name),
                )
            )

        return genres


    async def artists(
        self,
        *,
        search: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return bounded hydrated artists from the MA library."""
        safe_limit = max(
            1,
            min(int(limit), MAX_NATIVE_RESULTS),
        )

        args: dict[str, Any] = {
            "limit": safe_limit,
            "offset": 0,
            "order_by": "name",
            "summary": False,
            "kwargs": {},
        }

        if search:
            args["search"] = search.strip()

        raw = await self._command(
            "music/artists/library_items",
            args,
        )

        if not isinstance(raw, list):
            return []

        return [
            item
            for item in raw
            if isinstance(item, dict)
        ]

    async def similar_artists(
        self,
        *,
        item_id: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Return MA-grounded similar artists for a library artist."""
        safe_limit = max(
            1,
            min(int(limit), MAX_NATIVE_RESULTS),
        )

        raw = await self._command(
            "music/artists/similar_artists",
            {
                "item_id": str(item_id),
                "provider_instance_id_or_domain": "library",
                "limit": safe_limit,
            },
        )

        if not isinstance(raw, list):
            return []

        return [
            item
            for item in raw
            if isinstance(item, dict)
        ]

    async def artist_tracks(
        self,
        *,
        item_id: str,
    ) -> list[NativeTrack]:
        """Return tracks belonging to a grounded MA library artist."""
        raw = await self._command(
            "music/artists/artist_tracks",
            {
                "item_id": str(item_id),
                "provider_instance_id_or_domain": "library",
            },
        )

        if not isinstance(raw, list):
            return []

        tracks: list[NativeTrack] = []

        for item in raw:
            if not isinstance(item, dict):
                continue

            track_id = item.get("item_id")
            uri = item.get("uri")
            name = item.get("name")

            if not track_id or not uri or not name:
                continue

            artists = item.get("artists") or []
            artist = None

            if artists and isinstance(artists[0], dict):
                artist = artists[0].get("name")

            album_data = item.get("album")
            album = None
            year = None

            if isinstance(album_data, dict):
                album = album_data.get("name")
                raw_year = album_data.get("year")

                if isinstance(raw_year, int):
                    year = raw_year

            metadata = item.get("metadata") or {}
            raw_genres = []

            if isinstance(metadata, dict):
                raw_genres = metadata.get("genres") or []

            genres = tuple(
                str(value)
                for value in raw_genres
                if isinstance(value, str)
            )

            tracks.append(
                NativeTrack(
                    item_id=str(track_id),
                    uri=str(uri),
                    name=str(name),
                    artist=artist,
                    album=album,
                    year=year,
                    genres=genres,
                    favorite=bool(
                        item.get("favorite", False)
                    ),
                )
            )

        return tracks


    async def tracks(
        self,
        *,
        genre_id: int | None = None,
        limit: int = 50,
        order_by: str = "random",
    ) -> list[NativeTrack]:
        safe_limit = max(
            1,
            min(int(limit), MAX_NATIVE_RESULTS),
        )

        args: dict[str, Any] = {
            "limit": safe_limit,
            "offset": 0,
            "order_by": order_by,
            "summary": False,
            "kwargs": {},
        }

        if genre_id is not None:
            args["genre"] = int(genre_id)

        raw = await self._command(
            "music/tracks/library_items",
            args,
        )

        if not isinstance(raw, list):
            return []

        tracks: list[NativeTrack] = []

        for item in raw:
            if not isinstance(item, dict):
                continue

            item_id = item.get("item_id")
            uri = item.get("uri")
            name = item.get("name")

            if not item_id or not uri or not name:
                continue

            artists = item.get("artists") or []
            artist = None

            if artists and isinstance(artists[0], dict):
                artist = artists[0].get("name")

            album_data = item.get("album")
            album = None
            year = None

            if isinstance(album_data, dict):
                album = album_data.get("name")

                raw_year = album_data.get("year")
                if isinstance(raw_year, int):
                    year = raw_year

            metadata = item.get("metadata") or {}
            raw_genres = []

            if isinstance(metadata, dict):
                raw_genres = metadata.get("genres") or []

            genres = tuple(
                str(value)
                for value in raw_genres
                if isinstance(value, str)
            )

            tracks.append(
                NativeTrack(
                    item_id=str(item_id),
                    uri=str(uri),
                    name=str(name),
                    artist=artist,
                    album=album,
                    year=year,
                    genres=genres,
                    favorite=bool(
                        item.get("favorite", False)
                    ),
                )
            )

        return tracks


music_assistant_native = MusicAssistantNativeAdapter(
    settings.music_assistant_url,
    settings.music_assistant_token,
)
