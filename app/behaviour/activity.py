from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import median, pstdev

from app.context.activity import (
    get_activity_history,
)


ACTIVITY_LOOKBACK_DAYS = 90

# Exploratory clustering only.
CLUSTER_GAP_MINUTES = 45

# Qualification rules describe the strength of
# evidence required before Jarvis calls something
# a learned temporal behaviour.
MIN_QUALIFIED_SAMPLES = 5
MIN_DISTINCT_DATES = 5
MIN_WEEKDAYS_REPRESENTED = 3
QUALIFICATION_WINDOW_MINUTES = 60
MIN_WINDOW_RETENTION = 0.60
MAX_TIME_STDDEV_MINUTES = 30


def _format_minutes(
    value: float,
) -> str:
    minutes = int(round(value))

    hour = (minutes // 60) % 24
    minute = minutes % 60

    return f"{hour:02d}:{minute:02d}"


def _day_type(
    weekday: str,
) -> str:
    if weekday in (
        "Saturday",
        "Sunday",
    ):
        return "weekend"

    return "weekday"


def _cluster_by_time(
    activities: list[dict],
) -> list[list[dict]]:
    if not activities:
        return []

    ordered = sorted(
        activities,
        key=lambda item:
            item["minutes_after_midnight"],
    )

    clusters = []
    current = [ordered[0]]

    for activity in ordered[1:]:
        previous = current[-1]

        gap = (
            activity["minutes_after_midnight"]
            - previous["minutes_after_midnight"]
        )

        if gap <= CLUSTER_GAP_MINUTES:
            current.append(activity)
        else:
            clusters.append(current)
            current = [activity]

    clusters.append(current)

    return clusters


def _metric_summary(
    values: list[float | int | None],
) -> dict:
    usable = [
        value
        for value in values
        if value is not None
    ]

    if not usable:
        return {
            "samples": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
        }

    return {
        "samples": len(usable),
        "minimum": round(min(usable), 2),
        "median": round(median(usable), 2),
        "maximum": round(max(usable), 2),
    }


def _describe_time_cluster(
    activities: list[dict],
) -> dict:
    times = [
        activity["minutes_after_midnight"]
        for activity in activities
    ]

    weekdays = Counter(
        activity["weekday"]
        for activity in activities
    )

    dates = sorted(
        {
            activity["date"]
            for activity in activities
        }
    )

    centre = median(times)

    deviation = (
        pstdev(times)
        if len(times) > 1
        else 0
    )

    return {
        "samples": len(activities),
        "distinct_dates": len(dates),
        "typical_time":
            _format_minutes(centre),
        "typical_minutes":
            centre,
        "observed_range": {
            "earliest":
                _format_minutes(min(times)),
            "latest":
                _format_minutes(max(times)),
        },
        "standard_deviation_minutes":
            round(deviation, 1),
        "weekday_distribution":
            dict(weekdays),
        "duration_minutes":
            _metric_summary(
                [
                    activity.get(
                        "duration_minutes"
                    )
                    for activity in activities
                ]
            ),
        "distance_miles":
            _metric_summary(
                [
                    activity.get(
                        "distance_miles"
                    )
                    for activity in activities
                ]
            ),
        "dates": dates,
    }


def _eligible_days_between(
    start_date: date,
    end_date: date,
    day_type: str,
) -> int:
    count = 0
    current = start_date

    while current <= end_date:
        is_weekend = (
            current.weekday() >= 5
        )

        if (
            day_type == "weekday"
            and not is_weekend
        ):
            count += 1

        elif (
            day_type == "weekend"
            and is_weekend
        ):
            count += 1

        current += timedelta(days=1)

    return count


def _qualify_cluster(
    activity_type: str,
    day_type: str,
    activities: list[dict],
) -> dict | None:
    if len(activities) < MIN_QUALIFIED_SAMPLES:
        return None

    original_dates = {
        activity["date"]
        for activity in activities
    }

    if len(original_dates) < MIN_DISTINCT_DATES:
        return None

    times = [
        activity["minutes_after_midnight"]
        for activity in activities
    ]

    centre = median(times)

    qualified = [
        activity
        for activity in activities
        if abs(
            activity["minutes_after_midnight"]
            - centre
        ) <= QUALIFICATION_WINDOW_MINUTES
    ]

    retention = (
        len(qualified) / len(activities)
    )

    if retention < MIN_WINDOW_RETENTION:
        return None

    qualified_dates = {
        activity["date"]
        for activity in qualified
    }

    if (
        len(qualified_dates)
        < MIN_DISTINCT_DATES
    ):
        return None

    weekdays = {
        activity["weekday"]
        for activity in qualified
    }

    if (
        day_type == "weekday"
        and len(weekdays)
        < MIN_WEEKDAYS_REPRESENTED
    ):
        return None

    qualified_times = [
        activity["minutes_after_midnight"]
        for activity in qualified
    ]

    centre = median(qualified_times)

    deviation = (
        pstdev(qualified_times)
        if len(qualified_times) > 1
        else 0
    )

    if deviation > MAX_TIME_STDDEV_MINUTES:
        return None

    duration = _metric_summary(
        [
            activity.get(
                "duration_minutes"
            )
            for activity in qualified
        ]
    )

    distance = _metric_summary(
        [
            activity.get(
                "distance_miles"
            )
            for activity in qualified
        ]
    )

    distribution = Counter(
        activity["weekday"]
        for activity in qualified
    )

    first_observed = min(
        qualified_dates
    )

    last_observed = max(
        qualified_dates
    )

    eligible_days = (
        _eligible_days_between(
            date.fromisoformat(
                first_observed
            ),
            date.fromisoformat(
                last_observed
            ),
            day_type,
        )
    )

    observed_prevalence = (
        len(qualified_dates)
        / eligible_days
        if eligible_days
        else None
    )

    return {
        "activity_type":
            activity_type,
        "day_type":
            day_type,
        "typical_time":
            _format_minutes(centre),
        "typical_minutes":
            centre,
        "window": {
            "start":
                _format_minutes(
                    centre
                    - QUALIFICATION_WINDOW_MINUTES
                ),
            "end":
                _format_minutes(
                    centre
                    + QUALIFICATION_WINDOW_MINUTES
                ),
            "radius_minutes":
                QUALIFICATION_WINDOW_MINUTES,
        },
        "evidence": {
            "samples":
                len(qualified),
            "distinct_dates":
                len(qualified_dates),
            "source_cluster_samples":
                len(activities),
            "window_retention":
                round(retention, 2),
            "weekdays_represented":
                sorted(weekdays),
            "weekday_distribution":
                dict(distribution),
            "standard_deviation_minutes":
                round(deviation, 1),
            "first_observed":
                first_observed,
            "last_observed":
                last_observed,
            "eligible_days_in_observation_span":
                eligible_days,
            "observed_prevalence":
                (
                    round(
                        observed_prevalence,
                        2,
                    )
                    if observed_prevalence
                    is not None
                    else None
                ),
        },
        "typical_activity": {
            "duration_minutes":
                duration["median"],
            "distance_miles":
                distance["median"],
        },
    }


def _describe_activity_type(
    activity_type: str,
    activities: list[dict],
) -> tuple[dict, list[dict]]:
    weekday_activities = [
        activity
        for activity in activities
        if _day_type(
            activity["weekday"]
        ) == "weekday"
    ]

    weekend_activities = [
        activity
        for activity in activities
        if _day_type(
            activity["weekday"]
        ) == "weekend"
    ]

    weekday_raw_clusters = (
        _cluster_by_time(
            weekday_activities
        )
    )

    weekend_raw_clusters = (
        _cluster_by_time(
            weekend_activities
        )
    )

    weekday_clusters = [
        _describe_time_cluster(cluster)
        for cluster in weekday_raw_clusters
    ]

    weekend_clusters = [
        _describe_time_cluster(cluster)
        for cluster in weekend_raw_clusters
    ]

    qualified_behaviours = []

    for cluster in weekday_raw_clusters:
        qualified = _qualify_cluster(
            activity_type,
            "weekday",
            cluster,
        )

        if qualified is not None:
            qualified_behaviours.append(
                qualified
            )

    for cluster in weekend_raw_clusters:
        qualified = _qualify_cluster(
            activity_type,
            "weekend",
            cluster,
        )

        if qualified is not None:
            qualified_behaviours.append(
                qualified
            )

    description = {
        "activity_type":
            activity_type,
        "samples":
            len(activities),
        "distinct_dates":
            len(
                {
                    activity["date"]
                    for activity
                    in activities
                }
            ),
        "weekday_samples":
            len(weekday_activities),
        "weekend_samples":
            len(weekend_activities),
        "weekday_distribution":
            dict(
                Counter(
                    activity["weekday"]
                    for activity
                    in activities
                )
            ),
        "duration_minutes":
            _metric_summary(
                [
                    activity.get(
                        "duration_minutes"
                    )
                    for activity in activities
                ]
            ),
        "distance_miles":
            _metric_summary(
                [
                    activity.get(
                        "distance_miles"
                    )
                    for activity in activities
                ]
            ),
        "weekday_time_clusters":
            weekday_clusters,
        "weekend_time_clusters":
            weekend_clusters,
    }

    return (
        description,
        qualified_behaviours,
    )


async def analyse_activity_behaviour(
    days: int = ACTIVITY_LOOKBACK_DAYS,
) -> dict:
    history = await get_activity_history(
        days=days
    )

    if not history["available"]:
        return {
            "available": False,
            "window_days": days,
            "error": history.get(
                "error"
            ),
            "activity_types": [],
            "qualified_behaviours": [],
        }

    activities = history["activities"]

    grouped = defaultdict(list)

    for activity in activities:
        grouped[
            activity["activity_type"]
        ].append(activity)

    type_analysis = []
    qualified_behaviours = []

    for (
        activity_type,
        type_activities,
    ) in sorted(grouped.items()):
        (
            description,
            qualified,
        ) = _describe_activity_type(
            activity_type,
            type_activities,
        )

        type_analysis.append(
            description
        )

        qualified_behaviours.extend(
            qualified
        )

    very_short = [
        {
            "activity_type":
                activity["activity_type"],
            "date":
                activity["date"],
            "time":
                activity["local_time"],
            "duration_minutes":
                activity.get(
                    "duration_minutes"
                ),
            "distance_miles":
                activity.get(
                    "distance_miles"
                ),
            "activity_id":
                activity.get(
                    "activity_id"
                ),
        }
        for activity in activities
        if (
            activity.get(
                "duration_minutes"
            ) is not None
            and activity[
                "duration_minutes"
            ] < 5
        )
    ]

    return {
        "available": True,
        "window_days": days,
        "activity_count":
            len(activities),
        "settings": {
            "cluster_gap_minutes":
                CLUSTER_GAP_MINUTES,
            "qualification": {
                "minimum_samples":
                    MIN_QUALIFIED_SAMPLES,
                "minimum_distinct_dates":
                    MIN_DISTINCT_DATES,
                "minimum_weekdays_represented":
                    MIN_WEEKDAYS_REPRESENTED,
                "window_radius_minutes":
                    QUALIFICATION_WINDOW_MINUTES,
                "minimum_window_retention":
                    MIN_WINDOW_RETENTION,
                "maximum_time_stddev_minutes":
                    MAX_TIME_STDDEV_MINUTES,
            },
        },
        "very_short_activities":
            very_short,
        "today_activities":
            (
                history
                .get("today", {})
                .get("activities", [])
            ),
        "qualified_behaviours":
            qualified_behaviours,
        "activity_types":
            type_analysis,
    }
