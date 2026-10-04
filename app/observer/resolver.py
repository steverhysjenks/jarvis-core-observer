import json

from app.storage.ledger import (
    mark_resolved,
    open_entries,
)


def resolve_routine_departure(
    entry: dict,
    context: dict,
) -> dict | None:
    """
    Resolve a departure-deviation situation once the
    primary user is demonstrably no longer home.

    Departure confirmation is deterministic. The LLM
    does not participate in situation resolution.
    """

    user = context.get(
        "user",
        {},
    )

    if user.get("home") is not False:
        return None

    resolved = mark_resolved(
        entry["candidate_key"],
        "primary_user_no_longer_home",
    )

    return {
        "candidate_key":
            entry["candidate_key"],
        "candidate_type":
            entry["candidate_type"],
        "resolved": True,
        "reason":
            "primary_user_no_longer_home",
        "resolved_at":
            resolved.get("resolved_at")
            if resolved else None,
    }


RESOLVERS = {
    "routine_departure_deviation":
        resolve_routine_departure,
}


def resolve_open_situations(
    context: dict,
) -> list[dict]:
    """
    Evaluate unresolved situations against current
    deterministic context.

    Unknown candidate types remain open rather than
    being guessed at or passed to an LLM.
    """

    resolutions = []

    for entry in open_entries():
        resolver = RESOLVERS.get(
            entry.get("candidate_type")
        )

        if resolver is None:
            continue

        # Validate that persisted candidate data remains
        # parseable. Resolution currently uses the
        # semantic context, but malformed persisted state
        # should fail closed rather than mutate lifecycle.
        try:
            json.loads(
                entry["candidate_json"]
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            continue

        resolution = resolver(
            entry,
            context,
        )

        if resolution is not None:
            resolutions.append(
                resolution
            )

    return resolutions
