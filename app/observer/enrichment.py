from datetime import datetime
from zoneinfo import ZoneInfo


LOCAL_TIMEZONE = ZoneInfo(
    "Europe/London"
)


def _minutes(
    time_string: str,
) -> int:
    hour, minute = map(
        int,
        time_string.split(":"),
    )

    return hour * 60 + minute


def enrich_candidate(
    observer: dict,
    candidate: dict,
) -> dict:
    enriched = {
        **candidate,
        "facts": {},
    }

    facts = enriched["facts"]

    user = observer.get(
        "user",
        {},
    )

    schedule = observer.get(
        "schedule",
        {},
    )

    facts["user_currently_home"] = (
        user.get("home") is True
    )

    facts["user_area"] = user.get(
        "area"
    )

    if (
        candidate.get("type")
        == "routine_departure_deviation"
    ):
        routine = candidate.get(
            "routine",
            {},
        )

        current = candidate.get(
            "current",
            {},
        )

        facts["minutes_from_typical"] = (
            current.get(
                "minutes_from_expected"
            )
        )

        source_range = routine.get(
            "source_range",
            {},
        )

        current_time = current.get(
            "time"
        )

        latest = source_range.get(
            "latest"
        )

        earliest = source_range.get(
            "earliest"
        )

        if (
            current_time
            and earliest
            and latest
        ):
            current_dt = (
                datetime.fromisoformat(
                    current_time
                ).astimezone(
                    LOCAL_TIMEZONE
                )
            )

            current_minutes = (
                current_dt.hour * 60
                + current_dt.minute
            )

            earliest_minutes = _minutes(
                earliest
            )

            latest_minutes = _minutes(
                latest
            )

            facts[
                "outside_historical_range"
            ] = not (
                earliest_minutes
                <= current_minutes
                <= latest_minutes
            )

            facts[
                "minutes_beyond_historical_latest"
            ] = max(
                0,
                current_minutes
                - latest_minutes,
            )

        facts["routine_confidence"] = (
            routine.get("confidence")
        )

        facts["routine_recurrence"] = (
            routine.get("recurrence")
        )

    if (
        candidate.get("type")
        == "activity_opportunity"
    ):
        activity = candidate.get(
            "activity",
            {},
        )

        opportunity = candidate.get(
            "opportunity",
            {},
        )

        constraints = candidate.get(
            "constraints",
            {},
        )

        family = constraints.get(
            "family",
            {},
        )

        today = candidate.get(
            "today",
            {},
        )

        facts["activity_type"] = (
            activity.get("type")
        )

        facts[
            "activity_typical_time"
        ] = activity.get(
            "typical_time"
        )

        facts[
            "activity_typical_duration_minutes"
        ] = activity.get(
            "typical_duration_minutes"
        )

        facts[
            "activity_typical_distance_miles"
        ] = activity.get(
            "typical_distance_miles"
        )

        facts[
            "activity_free_minutes"
        ] = opportunity.get(
            "free_minutes"
        )

        facts[
            "activity_required_minutes"
        ] = opportunity.get(
            "required_minutes"
        )

        facts[
            "activity_free_start"
        ] = opportunity.get(
            "free_start"
        )

        facts[
            "activity_free_end"
        ] = opportunity.get(
            "free_end"
        )

        facts[
            "activity_matching_completed_today"
        ] = today.get(
            "matching_activity_completed"
        )

        facts[
            "activity_family_constraint_permitted"
        ] = family.get(
            "permitted"
        )

        facts[
            "activity_children_with_me"
        ] = family.get(
            "children_with_me"
        )

        facts[
            "activity_allowed_with_children"
        ] = family.get(
            "allowed_with_children"
        )

        facts[
            "activity_calendar_evidence_available"
        ] = (
            observer
            .get("capabilities", {})
            .get("calendar")
            is True
            and isinstance(
                schedule.get("events"),
                list,
            )
        )

    event = schedule.get(
        "next_timed_event"
    )

    facts["calendar_event_soon"] = False
    facts[
        "calendar_starts_in_minutes"
    ] = None

    if event:
        starts_in = event.get(
            "starts_in_minutes"
        )

        if (
            isinstance(
                starts_in,
                (int, float),
            )
            and 0 <= starts_in <= 30
        ):
            facts[
                "calendar_event_soon"
            ] = True

            facts[
                "calendar_starts_in_minutes"
            ] = starts_in

            facts[
                "calendar_event_summary"
            ] = event.get(
                "summary"
            )

            facts[
                "calendar_event_location"
            ] = event.get(
                "location"
            )

    return enriched


def candidate_is_valid(
    candidate: dict,
) -> bool:
    facts = candidate.get(
        "facts",
        {},
    )

    if (
        candidate.get("type")
        == "routine_departure_deviation"
        and not facts.get(
            "user_currently_home",
            False,
        )
    ):
        return False

    return True


def candidate_has_required_facts(
    candidate: dict,
) -> bool:
    """
    Verify that deterministic enrichment produced the facts
    required for safe probabilistic judgement.

    Unknown candidate types currently have no additional
    required-fact contract.
    """

    candidate_type = candidate.get(
        "type"
    )

    facts = candidate.get(
        "facts",
        {},
    )

    if (
        candidate_type
        == "routine_departure_deviation"
    ):
        required = (
            "user_currently_home",
            "minutes_from_typical",
            "outside_historical_range",
            "minutes_beyond_historical_latest",
            "routine_confidence",
            "routine_recurrence",
        )

        return all(
            facts.get(key) is not None
            for key in required
        )

    if (
        candidate_type
        == "activity_opportunity"
    ):
        required = (
            "user_currently_home",
            "activity_type",
            "activity_typical_time",
            "activity_typical_duration_minutes",
            "activity_free_minutes",
            "activity_required_minutes",
            "activity_free_start",
            "activity_free_end",
            "activity_matching_completed_today",
            "activity_family_constraint_permitted",
            "activity_allowed_with_children",
            "activity_calendar_evidence_available",
        )

        if not all(
            facts.get(key) is not None
            for key in required
        ):
            return False

        # These are deterministic prerequisites rather
        # than matters for probabilistic judgement.
        if (
            facts["user_currently_home"]
            is not True
        ):
            return False

        if (
            facts[
                "activity_matching_completed_today"
            ]
            is not False
        ):
            return False

        if (
            facts[
                "activity_family_constraint_permitted"
            ]
            is not True
        ):
            return False

        if (
            facts[
                "activity_calendar_evidence_available"
            ]
            is not True
        ):
            return False

        if (
            facts["activity_free_minutes"]
            < facts["activity_required_minutes"]
        ):
            return False

        return True

    return True
