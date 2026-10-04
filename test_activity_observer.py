from datetime import datetime
from zoneinfo import ZoneInfo

from app.observer.detectors.activity import (
    _blocking_intervals,
    _children_constraint,
    _largest_free_interval,
    _matching_activity_today,
)
from app.storage.ledger import candidate_key


TZ = ZoneInfo("Europe/London")
passed = 0
total = 0


def check(name, condition):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}")


behaviour = {
    "activity_type": "Walking",
    "typical_activity": {
        "duration_minutes": 35.5,
    },
}

check(
    "tiny walk does not satisfy behaviour",
    not _matching_activity_today(
        [{
            "activity_type": "Walking",
            "duration_minutes": 0.1,
        }],
        behaviour,
    ),
)

check(
    "meaningful walk satisfies behaviour",
    _matching_activity_today(
        [{
            "activity_type": "Walking",
            "duration_minutes": 30.0,
        }],
        behaviour,
    ),
)

family_context = {
    "household": {
        "family": {
            "children": {
                "any_with_me": True,
            },
            "capabilities": {
                "child_presence": True,
            },
        },
    },
}

check(
    "walking permitted with children",
    _children_constraint(
        family_context,
        "Walking",
    )["permitted"] is True,
)

check(
    "constrained activity rejected with children",
    _children_constraint(
        family_context,
        "Strength Training",
    )["permitted"] is False,
)

unknown_family = {
    "household": {
        "family": {
            "children": {
                "any_with_me": None,
            },
            "capabilities": {
                "child_presence": False,
            },
        },
    },
}

check(
    "constrained activity fails closed on unknown family",
    _children_constraint(
        unknown_family,
        "Strength Training",
    )["permitted"] is False,
)

start = datetime(
    2026, 10, 2, 11, 30,
    tzinfo=TZ,
)
end = datetime(
    2026, 10, 2, 12, 52,
    tzinfo=TZ,
)

events = [{
    "calendar": "calendar.main",
    "start": "2026-10-02T11:35:00+01:00",
    "end": "2026-10-02T12:30:00+01:00",
    "all_day": False,
}]

blocking = _blocking_intervals(
    events,
    start,
    end,
)

free_start, free_end, free_minutes = _largest_free_interval(
    start,
    end,
    blocking,
)

check(
    "calendar commitment leaves 22 minute largest gap",
    round(
        (free_end - free_start).total_seconds()
        / 60
    ) == 22,
)

long_event = [{
    "calendar":
        "calendar.steverhysjenks_gmail_com",
    "start":
        "2026-10-02T00:00:00+01:00",
    "end":
        "2026-10-05T20:00:00+01:00",
    "all_day": False,
}]

check(
    "long contextual event does not block",
    _blocking_intervals(
        long_event,
        start,
        end,
    ) == [],
)


def activity_candidate(date, activity_type="Walking"):
    return {
        "type": "activity_opportunity",
        "activity": {
            "type": activity_type,
            "typical_time": "11:52",
        },
        "learned_behaviour": {
            "day_type": "weekday",
        },
        "opportunity": {
            "window_start":
                f"{date}T10:52:00+01:00",
            "free_start":
                f"{date}T11:30:00+01:00",
        },
    }


first = activity_candidate("2026-10-02")
later = activity_candidate("2026-10-02")
later["opportunity"]["free_start"] = (
    "2026-10-02T11:45:00+01:00"
)

next_day = activity_candidate("2026-10-03")
cycling = activity_candidate(
    "2026-10-02",
    "Cycling",
)

check(
    "same occurrence keeps same ledger key",
    candidate_key(first) == candidate_key(later),
)

check(
    "next date gets different ledger key",
    candidate_key(first) != candidate_key(next_day),
)

check(
    "different activity gets different ledger key",
    candidate_key(first) != candidate_key(cycling),
)

print()
print("===== SUMMARY =====")
print(f"{passed}/{total} passed")

if passed != total:
    raise SystemExit(1)
