from dataclasses import dataclass

from app.adapters.music_assistant import MusicSearchResult
from app.adapters.music_assistant_native import (
    NativeTrack,
    music_assistant_native,
)
from app.music.policy import MAX_LLM_CANDIDATES
from app.music.semantic_policy import (
    genres_for_activity,
    genres_for_mood,
)


SAMPLE_SIZE = 50
MAX_SAMPLE_ATTEMPTS = 3


@dataclass(frozen=True)
class RetrievalSpec:
    genre: str | None = None
    year_from: int | None = None
    year_to: int | None = None


def _normalise(value: str) -> str:
    return " ".join(
        value.strip().casefold().split()
    )


async def resolve_genre_id(
    genre_name: str,
) -> int | None:
    """
    Resolve a requested genre only against actual MA genre
    names mapped to tracks.

    No fuzzy or LLM-created catalogue match is permitted.
    """

    wanted = _normalise(genre_name)

    if not wanted:
        return None

    genres = await music_assistant_native.genres(
        limit=100
    )

    exact = [
        genre
        for genre in genres
        if _normalise(genre.name) == wanted
    ]

    if len(exact) != 1:
        return None

    return exact[0].item_id


def _matches_year(
    track: NativeTrack,
    year_from: int | None,
    year_to: int | None,
) -> bool:
    if year_from is None and year_to is None:
        return True

    if track.year is None:
        return False

    if (
        year_from is not None
        and track.year < year_from
    ):
        return False

    if (
        year_to is not None
        and track.year > year_to
    ):
        return False

    return True


def _to_search_result(
    track: NativeTrack,
) -> MusicSearchResult:
    return MusicSearchResult(
        media_type="track",
        uri=track.uri,
        name=track.name,
        artist=track.artist,
        album=track.album,
        favorite=track.favorite,
    )


async def retrieve_tracks(
    spec: RetrievalSpec,
    *,
    limit: int = MAX_LLM_CANDIDATES,
) -> list[MusicSearchResult]:
    """
    Perform bounded descriptive retrieval.

    Genre filtering is delegated to Music Assistant.

    Era filtering is deterministic Jarvis policy over
    authoritative album-year metadata returned by MA.

    Native URIs remain internal and are returned only through
    the existing MusicSearchSession boundary.
    """

    safe_limit = max(
        1,
        min(int(limit), MAX_LLM_CANDIDATES),
    )

    genre_id = None

    if spec.genre:
        genre_id = await resolve_genre_id(
            spec.genre
        )

        if genre_id is None:
            return []

    selected: list[NativeTrack] = []
    seen_uris: set[str] = set()

    # Genre-only requests need no sampling loop beyond one
    # bounded MA query because MA performs the filter itself.
    attempts = (
        1
        if (
            spec.year_from is None
            and spec.year_to is None
        )
        else MAX_SAMPLE_ATTEMPTS
    )

    for _ in range(attempts):
        tracks = await music_assistant_native.tracks(
            genre_id=genre_id,
            limit=SAMPLE_SIZE,
            order_by="random",
        )

        for track in tracks:
            if track.uri in seen_uris:
                continue

            seen_uris.add(track.uri)

            if not _matches_year(
                track,
                spec.year_from,
                spec.year_to,
            ):
                continue

            selected.append(track)

            if len(selected) >= safe_limit:
                break

        if len(selected) >= safe_limit:
            break

    return [
        _to_search_result(track)
        for track in selected[:safe_limit]
    ]



async def retrieve_similar_tracks(
    reference: str | None,
    limit: int = MAX_LLM_CANDIDATES,
) -> list[MusicSearchResult]:
    """
    Resolve an exact MA library artist, ask MA for similar artists,
    then return bounded tracks belonging to those grounded artists.
    """
    if not reference:
        return []

    normalized = " ".join(
        reference.strip().casefold().split()
    )

    artists = await music_assistant_native.artists(
        search=reference,
        limit=10,
    )

    exact = [
        artist
        for artist in artists
        if " ".join(
            str(artist.get("name", ""))
            .strip()
            .casefold()
            .split()
        ) == normalized
    ]

    if len(exact) != 1:
        return []

    reference_artist = exact[0]
    reference_id = reference_artist.get("item_id")

    if reference_id is None:
        return []

    similar = await music_assistant_native.similar_artists(
        item_id=str(reference_id),
        limit=8,
    )

    results: list[MusicSearchResult] = []
    seen_uris: set[str] = set()

    # MA owns the similarity relationship. We only bound and
    # de-duplicate tracks returned for those grounded artists.
    for artist in similar:
        artist_id = artist.get("item_id")

        if artist_id is None:
            continue

        tracks = await music_assistant_native.artist_tracks(
            item_id=str(artist_id),
        )

        for track in tracks:
            if track.uri in seen_uris:
                continue

            seen_uris.add(track.uri)
            results.append(_to_search_result(track))

            if len(results) >= limit:
                return results

    return results


async def retrieve_activity_tracks(
    activity: str | None,
    limit: int = MAX_LLM_CANDIDATES,
) -> tuple[str | None, list[MusicSearchResult]]:
    """
    Retrieve grounded tracks for a bounded activity policy.

    The semantic activity never becomes a catalogue query.
    Jarvis policy first maps it to approved MA genres,
    then normal MA catalogue retrieval supplies the tracks.
    """

    for genre in genres_for_activity(activity):
        results = await retrieve_tracks(
            RetrievalSpec(
                genre=genre,
            ),
            limit=limit,
        )

        if results:
            return genre, results

    return None, []


async def retrieve_mood_tracks(
    mood: str | None,
    limit: int = MAX_LLM_CANDIDATES,
) -> tuple[str | None, list[MusicSearchResult]]:
    """
    Retrieve grounded tracks for a bounded mood policy.

    The semantic mood never becomes a catalogue query.
    Jarvis policy first maps it to approved MA genres,
    then normal MA catalogue retrieval supplies the tracks.
    """

    for genre in genres_for_mood(mood):
        results = await retrieve_tracks(
            RetrievalSpec(
                genre=genre,
            ),
            limit=limit,
        )

        if results:
            return genre, results

    return None, []


async def retrieve_semantic_session(
    intent,
):
    """
    Convert an already-validated descriptive semantic intent
    into a bounded opaque MusicSearchSession.

    Supported here:
      activity
      mood
      genre
      era
      era_genre

    Playback is deliberately outside this function.
    """

    # Local imports avoid coupling the lower-level retrieval
    # primitives to semantic classification at import time.
    from app.music.service import MusicSearchSession

    if intent.retrieval_type == "similar":
        if not intent.similar_to:
            return None

        results = await retrieve_similar_tracks(
            intent.similar_to,
            limit=MAX_LLM_CANDIDATES,
        )

        return MusicSearchSession(results)

    if intent.retrieval_type == "activity":
        if not intent.activity:
            return None

        _genre, results = await retrieve_activity_tracks(
            intent.activity,
            limit=MAX_LLM_CANDIDATES,
        )

        return MusicSearchSession(results)

    if intent.retrieval_type == "mood":
        if not intent.mood:
            return None

        _genre, results = await retrieve_mood_tracks(
            intent.mood,
            limit=MAX_LLM_CANDIDATES,
        )

        return MusicSearchSession(results)

    if intent.retrieval_type == "genre":
        if not intent.genre:
            return None

        spec = RetrievalSpec(
            genre=intent.genre,
        )

    elif intent.retrieval_type == "era":
        if (
            intent.year_from is None
            or intent.year_to is None
        ):
            return None

        spec = RetrievalSpec(
            year_from=intent.year_from,
            year_to=intent.year_to,
        )

    elif intent.retrieval_type == "era_genre":
        if (
            not intent.genre
            or intent.year_from is None
            or intent.year_to is None
        ):
            return None

        spec = RetrievalSpec(
            genre=intent.genre,
            year_from=intent.year_from,
            year_to=intent.year_to,
        )

    else:
        return None

    results = await retrieve_tracks(
        spec,
        limit=MAX_LLM_CANDIDATES,
    )

    return MusicSearchSession(results)
