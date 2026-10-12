from collections import defaultdict
from datetime import datetime
from typing import Any


VERY_BRIEF_SECONDS = 60
SUBSTANTIAL_DWELL_SECONDS = 300

MIN_RECURRING_OBSERVATIONS = 3
MIN_RECURRING_DAYS = 2


def interpret_place_visits(
    visits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Interpret semantic place observations without discarding evidence.

    History tells us what HA observed.
    This layer assigns deterministic confidence to those observations.

    This is intentionally place-agnostic. No special rules exist for
    School, Gym, Lou's, Theatre, etc.
    """

    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "completed_observations": 0,
            "observed_days": set(),
        }
    )

    # First pass: establish recurrence evidence.
    for visit in visits:
        place_id = visit["place"]["id"]

        if not (
            visit.get("arrival_observed")
            and visit.get("departure_observed")
        ):
            continue

        arrival = datetime.fromisoformat(
            visit["arrival"]
        )

        stats[place_id][
            "completed_observations"
        ] += 1

        stats[place_id][
            "observed_days"
        ].add(arrival.date())

    interpreted = []

    # Second pass: classify each observation.
    for visit in visits:
        result = dict(visit)

        place_id = visit["place"]["id"]
        duration = float(
            visit.get("duration_seconds", 0)
        )

        place_stats = stats[place_id]

        completed_observations = place_stats[
            "completed_observations"
        ]
        observed_days = len(
            place_stats["observed_days"]
        )

        boundaries_observed = bool(
            visit.get("arrival_observed")
            and visit.get("departure_observed")
        )

        recurring = (
            completed_observations
            >= MIN_RECURRING_OBSERVATIONS
            and observed_days
            >= MIN_RECURRING_DAYS
        )

        very_brief = (
            boundaries_observed
            and duration < VERY_BRIEF_SECONDS
        )

        substantial_dwell = (
            boundaries_observed
            and duration >= SUBSTANTIAL_DWELL_SECONDS
        )

        evidence = {
            "boundaries_observed":
                boundaries_observed,
            "duration_seconds":
                round(duration, 1),
            "very_brief":
                very_brief,
            "substantial_dwell":
                substantial_dwell,
            "place_completed_observations":
                completed_observations,
            "place_observed_days":
                observed_days,
            "recurring_place":
                recurring,
        }

        reasons = []

        if not boundaries_observed:
            classification = "probable"
            reasons.append(
                "observation_boundary_incomplete"
            )

        elif very_brief:
            classification = "transient"
            reasons.append(
                "very_brief_observation"
            )

        elif substantial_dwell:
            classification = "established"
            reasons.append(
                "substantial_dwell"
            )

        elif recurring:
            classification = "probable"
            reasons.append(
                "recurring_place_support"
            )

        else:
            classification = "probable"
            reasons.append(
                "limited_corroboration"
            )

        result["interpretation"] = {
            "classification": classification,
            "reasons": reasons,
            "evidence": evidence,
        }

        interpreted.append(result)

    return interpreted
