from app.adapters.music_assistant import MusicSearchResult


MAX_LLM_CANDIDATES = 8

MEDIA_TYPE_PRIORITY = {
    "artist": 0,
    "playlist": 1,
    "album": 2,
    "track": 3,
    "radio": 4,
    "audiobook": 5,
    "podcast": 6,
}


def bound_candidates(
    results: list[MusicSearchResult],
    *,
    limit: int = MAX_LLM_CANDIDATES,
) -> list[MusicSearchResult]:
    """
    Apply the Jarvis-facing candidate budget.

    Music Assistant may return a limit per media type.
    Jarvis exposes only a small global candidate set to
    downstream reasoning/model layers.
    """

    safe_limit = max(
        1,
        min(int(limit), MAX_LLM_CANDIDATES),
    )

    ordered = sorted(
        results,
        key=lambda item: (
            MEDIA_TYPE_PRIORITY.get(
                item.media_type,
                99,
            ),
            item.name.casefold(),
        ),
    )

    seen: set[str] = set()
    bounded: list[MusicSearchResult] = []

    for result in ordered:
        if result.uri in seen:
            continue

        seen.add(result.uri)
        bounded.append(result)

        if len(bounded) >= safe_limit:
            break

    return bounded
