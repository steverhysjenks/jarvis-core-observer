from app.adapters.music_assistant import (
    MusicAssistantAdapter,
    MusicSearchResult,
)
from app.music.models import (
    MusicCandidate,
    ResolvedMusicCandidate,
)
from app.music.policy import (
    MAX_LLM_CANDIDATES,
    bound_candidates,
)


MUSIC_ASSISTANT_CONFIG_ENTRY_ID = (
    "01M25SMCNN4RW6A7WZ4GBQDC3A"
)

music_assistant = MusicAssistantAdapter(
    MUSIC_ASSISTANT_CONFIG_ENTRY_ID
)


class MusicSearchSession:
    """
    One bounded retrieval session.

    Public candidates contain opaque IDs only.
    Music Assistant URIs remain private to this session.
    """

    def __init__(
        self,
        results: list[MusicSearchResult],
    ):
        self._results: dict[str, MusicSearchResult] = {}
        self.candidates: list[MusicCandidate] = []

        for index, result in enumerate(results, start=1):
            candidate_id = f"m{index}"

            self._results[candidate_id] = result

            self.candidates.append(
                MusicCandidate(
                    candidate_id=candidate_id,
                    media_type=result.media_type,
                    name=result.name,
                    artist=result.artist,
                    album=result.album,
                    favorite=result.favorite,
                )
            )

    def resolve(
        self,
        candidate_id: str,
    ) -> ResolvedMusicCandidate:
        result = self._results.get(candidate_id)

        if result is None:
            raise ValueError(
                f"Unknown music candidate: {candidate_id}"
            )

        return ResolvedMusicCandidate(
            candidate_id=candidate_id,
            uri=result.uri,
            media_type=result.media_type,
            name=result.name,
            artist=result.artist,
            album=result.album,
        )


async def search_library(
    query: str,
    *,
    limit: int = MAX_LLM_CANDIDATES,
) -> MusicSearchSession:

    results = await music_assistant.search(
        query,
        limit=limit,
        library_only=True,
    )

    bounded = bound_candidates(
        results,
        limit=limit,
    )

    return MusicSearchSession(bounded)


async def play_candidate(
    session: MusicSearchSession,
    candidate_id: str,
    area: str,
):
    """
    Play a candidate produced by this retrieval session
    on an explicitly allowed semantic target.
    """

    from app.music.targets import resolve_target

    resolved = session.resolve(candidate_id)
    target = resolve_target(area)

    await music_assistant.play_media(
        entity_id=target.entity_id,
        media_id=resolved.uri,
        media_type=resolved.media_type,
        enqueue="replace",
        radio_mode=False,
    )

    return {
        "candidate_id": resolved.candidate_id,
        "name": resolved.name,
        "media_type": resolved.media_type,
        "target_area": target.area,
        "target_name": target.name,
    }


def select_exact_candidate(
    session: MusicSearchSession,
    query: str,
) -> MusicCandidate | None:
    """
    Select an exact catalogue match deterministically.

    Rules:
    - exact name matches only
    - prefer artist for an exact artist request
    - prefer a unique favourite where available
    - otherwise use stable candidate order

    Multiple copies of the same track by the same artist
    are treated as equivalent catalogue recordings.
    """

    wanted = query.strip().casefold()

    if not wanted:
        return None

    exact = [
        candidate
        for candidate in session.candidates
        if candidate.name.strip().casefold() == wanted
    ]

    if not exact:
        return None

    # An exact artist match represents an artist request
    # more naturally than an album or track with the same
    # title.
    artists = [
        candidate
        for candidate in exact
        if candidate.media_type == "artist"
    ]

    if artists:
        return artists[0]

    # Honour an unambiguous favourite.
    favourites = [
        candidate
        for candidate in exact
        if candidate.favorite
    ]

    if len(favourites) == 1:
        return favourites[0]

    # Music Assistant relevance/order is retained.
    # This also gives us stable behaviour for equivalent
    # copies of the same recording.
    return exact[0]


async def play_explicit(
    query: str,
    area: str,
) -> dict:
    """
    Retrieve an explicit request from Music Assistant and
    play it only when an exact catalogue match exists.

    No fuzzy fallback is allowed here.
    """

    session = await search_library(
        query,
        limit=MAX_LLM_CANDIDATES,
    )

    candidate = select_exact_candidate(
        session,
        query,
    )

    if candidate is None:
        return {
            "handled": False,
            "reason": "no_exact_match",
            "query": query,
        }

    result = await play_candidate(
        session,
        candidate.candidate_id,
        area,
    )

    return {
        "handled": True,
        "selection": "exact_match",
        **result,
    }


async def play_descriptive(
    session: MusicSearchSession,
    area: str,
) -> dict:
    """
    Play one candidate from an already-grounded descriptive
    retrieval session.

    v1 selection policy:
      - candidate must already exist in the bounded session
      - use the first candidate from MA's random retrieval order
      - playback still resolves through the opaque candidate ID

    No catalogue URI may be supplied by the semantic layer.
    """

    if not session.candidates:
        return {
            "handled": False,
            "reason": "no_candidates",
        }

    candidate = session.candidates[0]

    result = await play_candidate(
        session,
        candidate.candidate_id,
        area,
    )

    return {
        "handled": True,
        "selection": "bounded_random",
        "candidate_count": len(session.candidates),
        **result,
    }
