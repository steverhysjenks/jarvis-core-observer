from dataclasses import dataclass
from typing import Literal

from app.adapters.homeassistant import ha_client


MediaType = Literal[
    "artist",
    "album",
    "track",
    "playlist",
    "radio",
    "audiobook",
    "podcast",
]

ALLOWED_MEDIA_TYPES = {
    "artist",
    "album",
    "track",
    "playlist",
    "radio",
    "audiobook",
    "podcast",
}

MAX_SEARCH_RESULTS = 8


@dataclass(frozen=True)
class MusicSearchResult:
    media_type: str
    uri: str
    name: str
    artist: str | None = None
    album: str | None = None
    favorite: bool = False


class MusicAssistantAdapter:
    def __init__(self, config_entry_id: str):
        self.config_entry_id = config_entry_id

    async def search(
        self,
        name: str,
        *,
        media_types: list[MediaType] | None = None,
        limit: int = 5,
        library_only: bool = True,
        username: str | None = None,
    ) -> list[MusicSearchResult]:

        query = name.strip()
        if not query:
            return []

        requested_types = media_types or [
            "artist",
            "album",
            "track",
            "playlist",
        ]

        safe_types = [
            media_type
            for media_type in requested_types
            if media_type in ALLOWED_MEDIA_TYPES
        ]

        if not safe_types:
            return []

        safe_limit = max(
            1,
            min(int(limit), MAX_SEARCH_RESULTS),
        )

        payload = {
            "config_entry_id": self.config_entry_id,
            "name": query,
            "media_type": safe_types,
            "limit": safe_limit,
            "library_only": bool(library_only),
        }

        if username:
            payload["username"] = username

        response = await ha_client.call_service(
            "music_assistant",
            "search",
            payload,
            return_response=True,
        )

        service_response = response.get(
            "service_response",
            {},
        )

        results: list[MusicSearchResult] = []

        for items in service_response.values():
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                uri = item.get("uri")
                name_value = item.get("name")
                media_type = item.get("media_type")

                if (
                    not uri
                    or not name_value
                    or media_type not in ALLOWED_MEDIA_TYPES
                ):
                    continue

                artists = item.get("artists") or []
                artist = None

                if artists and isinstance(artists[0], dict):
                    artist = artists[0].get("name")

                album_data = item.get("album")
                album = None

                if isinstance(album_data, dict):
                    album = album_data.get("name")

                results.append(
                    MusicSearchResult(
                        media_type=media_type,
                        uri=uri,
                        name=name_value,
                        artist=artist,
                        album=album,
                        favorite=bool(
                            item.get("favorite", False)
                        ),
                    )
                )

        return results


    async def play_media(
        self,
        *,
        entity_id: str,
        media_id: str,
        media_type: str,
        enqueue: str = "replace",
        radio_mode: bool = False,
    ):
        """
        Play an already-resolved Music Assistant media item.

        Callers are responsible for supplying validated media
        and target identifiers.
        """

        if media_type not in ALLOWED_MEDIA_TYPES:
            raise ValueError(
                f"Unsupported media type: {media_type}"
            )

        if enqueue not in {
            "play",
            "replace",
            "next",
            "replace_next",
            "add",
        }:
            raise ValueError(
                f"Unsupported enqueue mode: {enqueue}"
            )

        payload = {
            "media_id": media_id,
            "media_type": media_type,
            "enqueue": enqueue,
            "radio_mode": bool(radio_mode),
            "entity_id": entity_id,
        }

        return await ha_client.call_service(
            "music_assistant",
            "play_media",
            payload,
        )
