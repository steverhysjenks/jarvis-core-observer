"""Bounded semantic music policy.

Semantic concepts may resolve only to explicitly approved Music Assistant
catalogue genres. The LLM does not choose tracks, artists, URIs, or arbitrary
genre names.
"""

from __future__ import annotations


MOOD_GENRES: dict[str, tuple[str, ...]] = {
    "relaxing": (
        "Ambient",
        "Acoustic",
        "New Age",
        "Instrumental",
    ),
    "upbeat": (
        "Dance",
        "Disco",
        "Funk",
        "Fitness & Workout",
    ),
}


def genres_for_mood(
    mood: str | None,
) -> tuple[str, ...]:
    """Return the bounded MA genres permitted for a mood."""
    if not mood:
        return ()

    key = " ".join(
        mood.strip().casefold().split()
    )

    return MOOD_GENRES.get(key, ())


ACTIVITY_GENRES = {
    "cooking": (
        "Funk",
        "Dance",
        "Pop",
    ),
    "working": (
        "Instrumental",
        "Ambient",
        "Acoustic",
    ),
    "reading": (
        "Ambient",
        "Instrumental",
        "New Age",
    ),
    "workout": (
        "Fitness & Workout",
        "Dance",
    ),
}


def genres_for_activity(
    activity: str | None,
) -> tuple[str, ...]:
    if not activity:
        return ()

    key = " ".join(
        activity.strip().casefold().split()
    )

    return ACTIVITY_GENRES.get(key, ())
