from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median, pstdev

from app.behaviour.departures import build_departure_observations


MIN_CLUSTER_SAMPLES = 3
CLUSTER_GAP_MINUTES = 20

# Minimum recurrence before we consider an individual
# weekday to be meaningfully associated with a routine.
MIN_WEEKDAY_RECURRENCE = 0.50

# Require at least two separate occurrences on that weekday.
MIN_WEEKDAY_OBSERVATIONS = 2


ROUTINE_CACHE_HOURS = 6

_routine_cache = {
    "generated_at": None,
    "days": None,
    "model": None,
}



def minutes_after_midnight(value: str) -> int:
    timestamp = datetime.fromisoformat(value)

    return (
        timestamp.hour * 60
        + timestamp.minute
    )


def format_minutes(value: float) -> str:
    minutes = int(round(value))

    hour = (minutes // 60) % 24
    minute = minutes % 60

    return f"{hour:02d}:{minute:02d}"


def day_type(weekday: str) -> str:
    if weekday in ("Saturday", "Sunday"):
        return "weekend"

    return "weekday"


def cluster_times(
    observations: list[dict],
) -> list[list[dict]]:
    if not observations:
        return []

    ordered = sorted(
        observations,
        key=lambda item: item["minutes"],
    )

    clusters = []
    current = [ordered[0]]

    for observation in ordered[1:]:
        previous = current[-1]

        gap = (
            observation["minutes"]
            - previous["minutes"]
        )

        if gap <= CLUSTER_GAP_MINUTES:
            current.append(observation)
        else:
            clusters.append(current)
            current = [observation]

    clusters.append(current)

    return clusters


def count_weekday_opportunities(
    weekday: str,
    window_start: datetime,
    window_end: datetime,
) -> int:
    count = 0
    cursor = window_start.date()
    end_date = window_end.date()

    while cursor <= end_date:
        if cursor.strftime("%A") == weekday:
            count += 1

        cursor += timedelta(days=1)

    return count


def calculate_weekday_recurrence(
    cluster: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> dict:
    results = {}

    weekdays_present = sorted(
        {
            item["weekday"]
            for item in cluster
        }
    )

    for weekday in weekdays_present:
        observations = [
            item
            for item in cluster
            if item["weekday"] == weekday
        ]

        # Count distinct dates, not raw observations.
        # This prevents multiple same-day departures
        # artificially inflating recurrence.
        observed_dates = {
            item["date"]
            for item in observations
        }

        opportunities = count_weekday_opportunities(
            weekday,
            window_start,
            window_end,
        )

        observed = len(observed_dates)

        recurrence = (
            observed / opportunities
            if opportunities
            else 0
        )

        weekday_times = [
            item["minutes"]
            for item in observations
        ]

        results[weekday] = {
            "observed_days": observed,
            "opportunities": opportunities,
            "recurrence": round(
                recurrence,
                2,
            ),
            "typical_time": format_minutes(
                median(weekday_times)
            ),
            "qualifies": (
                observed >= MIN_WEEKDAY_OBSERVATIONS
                and recurrence
                >= MIN_WEEKDAY_RECURRENCE
            ),
        }

    return results


def classify_routine_confidence(
    sample_count: int,
    deviation: float,
    qualifying_weekdays: list[dict],
) -> str:
    if not qualifying_weekdays:
        return "weak"

    best_recurrence = max(
        item["recurrence"]
        for item in qualifying_weekdays
    )

    if (
        sample_count >= 4
        and deviation <= 7
        and best_recurrence >= 0.75
    ):
        return "strong"

    if (
        sample_count >= 3
        and deviation <= 15
        and best_recurrence >= 0.50
    ):
        return "moderate"

    return "weak"


def describe_cluster(
    cluster: list[dict],
    category: str,
    window_start: datetime,
    window_end: datetime,
) -> dict:
    times = [
        item["minutes"]
        for item in cluster
    ]

    centre = median(times)

    deviation = (
        pstdev(times)
        if len(times) > 1
        else 0
    )

    weekday_distribution = defaultdict(int)

    for item in cluster:
        weekday_distribution[
            item["weekday"]
        ] += 1

    recurrence = calculate_weekday_recurrence(
        cluster,
        window_start,
        window_end,
    )

    qualifying_weekdays = [
        {
            "weekday": weekday,
            **details,
        }
        for weekday, details
        in recurrence.items()
        if details["qualifies"]
    ]

    confidence = classify_routine_confidence(
        len(cluster),
        deviation,
        qualifying_weekdays,
    )

    return {
        "day_type": category,
        "typical_time": format_minutes(
            centre
        ),
        "observed_range": {
            "earliest": format_minutes(
                min(times)
            ),
            "latest": format_minutes(
                max(times)
            ),
        },
        "samples": len(cluster),
        "standard_deviation_minutes": round(
            deviation,
            1,
        ),
        "weekday_distribution": dict(
            weekday_distribution
        ),
        "weekday_recurrence": recurrence,
        "qualifying_weekdays": [
            item["weekday"]
            for item in qualifying_weekdays
        ],
        "confidence": confidence,
        "observations": [
            {
                "date": item["date"],
                "weekday": item["weekday"],
                "time": item["time"],
            }
            for item in cluster
        ],
    }


async def learn_departure_routines(
    days: int = 28,
) -> dict:
    history = await build_departure_observations(
        days=days
    )

    departures = [
        departure
        for departure in history["departures"]
        if departure["confidence"] == "high"
    ]

    if not departures:
        return {
            "window_days": days,
            "settings": {
                "cluster_gap_minutes":
                    CLUSTER_GAP_MINUTES,
                "minimum_samples":
                    MIN_CLUSTER_SAMPLES,
                "minimum_weekday_recurrence":
                    MIN_WEEKDAY_RECURRENCE,
                "minimum_weekday_observations":
                    MIN_WEEKDAY_OBSERVATIONS,
            },
            "routines": [],
        }

    timestamps = [
        datetime.fromisoformat(
            departure["time"]
        )
        for departure in departures
    ]

    window_end = max(timestamps)

    window_start = (
        window_end
        - timedelta(days=days - 1)
    )

    grouped = {
        "weekday": [],
        "weekend": [],
    }

    for departure in departures:
        category = day_type(
            departure["weekday"]
        )

        grouped[category].append(
            {
                "date": departure["date"],
                "weekday": departure["weekday"],
                "time": departure["local_time"],
                "minutes": minutes_after_midnight(
                    departure["time"]
                ),
            }
        )

    routines = []

    for category, observations in grouped.items():
        clusters = cluster_times(
            observations
        )

        for cluster in clusters:
            if len(cluster) < MIN_CLUSTER_SAMPLES:
                continue

            routines.append(
                describe_cluster(
                    cluster,
                    category,
                    window_start,
                    window_end,
                )
            )

    routines.sort(
        key=lambda item: (
            item["day_type"],
            item["typical_time"],
        )
    )

    return {
        "window_days": days,
        "window_start": (
            window_start.isoformat()
        ),
        "window_end": (
            window_end.isoformat()
        ),
        "settings": {
            "cluster_gap_minutes":
                CLUSTER_GAP_MINUTES,
            "minimum_samples":
                MIN_CLUSTER_SAMPLES,
            "minimum_weekday_recurrence":
                MIN_WEEKDAY_RECURRENCE,
            "minimum_weekday_observations":
                MIN_WEEKDAY_OBSERVATIONS,
        },
        "routines": routines,
    }


def build_actionable_routines(
    routines: list[dict],
) -> list[dict]:
    actionable = []

    for routine in routines:
        for weekday, details in (
            routine["weekday_recurrence"].items()
        ):
            recurrence = details["recurrence"]
            observed = details["observed_days"]

            # Proactive behaviour should be conservative.
            # For now, require:
            #
            # - at least 3 separate observed days
            # - recurrence on at least 75% of opportunities
            #
            # We can relax this later as Jarvis gains
            # calendar/context awareness.
            if observed < 3:
                continue

            if recurrence < 0.75:
                continue

            if recurrence >= 0.90:
                confidence = "strong"
            else:
                confidence = "moderate"

            actionable.append(
                {
                    "type": "departure_routine",
                    "weekday": weekday,
                    "typical_time": details[
                        "typical_time"
                    ],
                    "recurrence": recurrence,
                    "observed_days": observed,
                    "opportunities": details[
                        "opportunities"
                    ],
                    "confidence": confidence,
                    "source_cluster": {
                        "typical_time": routine[
                            "typical_time"
                        ],
                        "range": routine[
                            "observed_range"
                        ],
                        "deviation_minutes": routine[
                            "standard_deviation_minutes"
                        ],
                    },
                }
            )

    actionable.sort(
        key=lambda item: (
            [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ].index(item["weekday"]),
            item["typical_time"],
        )
    )

    return actionable


async def get_departure_routine_model(
    days: int = 28,
    force_refresh: bool = False,
) -> dict:
    now = datetime.now().astimezone()

    generated_at = _routine_cache[
        "generated_at"
    ]

    cache_valid = (
        not force_refresh
        and _routine_cache["model"]
        is not None
        and _routine_cache["days"] == days
        and generated_at is not None
        and (
            now - generated_at
        ) < timedelta(
            hours=ROUTINE_CACHE_HOURS
        )
    )

    if cache_valid:
        return _routine_cache["model"]

    learned = await learn_departure_routines(
        days=days
    )

    model = {
        "generated_at": now.isoformat(),
        "window_days": days,
        "actionable_routines":
            build_actionable_routines(
                learned["routines"]
            ),
        "learned_routines":
            learned["routines"],
    }

    _routine_cache["generated_at"] = now
    _routine_cache["days"] = days
    _routine_cache["model"] = model

    return model
