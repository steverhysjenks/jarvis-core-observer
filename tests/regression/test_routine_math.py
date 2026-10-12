from datetime import datetime
from zoneinfo import ZoneInfo

from app.behaviour.routines import (
    cluster_times,
    calculate_weekday_recurrence,
    classify_routine_confidence,
)

TZ = ZoneInfo("Europe/London")


def observation(
    date,
    weekday,
    minutes,
):
    return {
        "date": date,
        "weekday": weekday,
        "minutes": minutes,
    }


def test_nearby_departures_cluster():
    data = [
        observation(
            "2026-09-07",
            "Monday",
            480,
        ),
        observation(
            "2026-09-14",
            "Monday",
            485,
        ),
        observation(
            "2026-09-21",
            "Monday",
            490,
        ),
    ]

    clusters = cluster_times(data)

    assert len(clusters) == 1
    assert len(clusters[0]) == 3


def test_separated_departures_form_different_clusters():
    data = [
        observation(
            "2026-09-07",
            "Monday",
            480,
        ),
        observation(
            "2026-09-14",
            "Monday",
            485,
        ),
        observation(
            "2026-09-21",
            "Monday",
            600,
        ),
    ]

    clusters = cluster_times(data)

    assert len(clusters) == 2


def test_recurrence_counts_distinct_dates_not_samples():
    start = datetime(
        2026, 9, 7,
        tzinfo=TZ,
    )

    end = datetime(
        2026, 9, 28,
        23, 59,
        tzinfo=TZ,
    )

    cluster = [
        observation(
            "2026-09-07",
            "Monday",
            480,
        ),
        observation(
            "2026-09-07",
            "Monday",
            482,
        ),
        observation(
            "2026-09-14",
            "Monday",
            481,
        ),
        observation(
            "2026-09-21",
            "Monday",
            483,
        ),
    ]

    result = calculate_weekday_recurrence(
        cluster,
        start,
        end,
    )

    monday = result["Monday"]

    # Four Monday opportunities in the window,
    # but only three distinct observed dates.
    assert monday["observed_days"] == 3
    assert monday["opportunities"] == 4
    assert monday["recurrence"] == 0.75


def test_strong_routine_contract():
    qualifying = [
        {
            "recurrence": 0.75,
        }
    ]

    assert classify_routine_confidence(
        sample_count=4,
        deviation=5,
        qualifying_weekdays=qualifying,
    ) == "strong"


def test_no_qualifying_weekday_is_weak():
    assert classify_routine_confidence(
        sample_count=20,
        deviation=1,
        qualifying_weekdays=[],
    ) == "weak"
