from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.behaviour.activity import (
    analyse_activity_behaviour,
)


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

ACTIVITY_LOOKBACK_DAYS = 90

# Calendars which may contain commitments that
# genuinely consume the user's time.
BLOCKING_CALENDARS = {
    "calendar.main",
    "calendar.steverhysjenks_gmail_com",
    "calendar.kids",
}

# Very long timed events are treated as context rather
# than continuous blocking commitments.
MAX_BLOCKING_EVENT_HOURS = 8

# Don't require the observed median exactly. A completed
# activity satisfies the learned behaviour if it reaches
# a substantial proportion of the learned typical duration.
SATISFACTION_DURATION_RATIO = 0.50

# Small preparation/recovery allowance around the
# learned activity itself.
ACTIVITY_MARGIN_MINUTES = 5


def _minutes_today(
    value: datetime,
) -> int:
    return (
        value.hour * 60
        + value.minute
    )


def _time_today(
    now: datetime,
    minutes: float,
) -> datetime:
    total = int(round(minutes))

    return now.replace(
        hour=(total // 60) % 24,
        minute=total % 60,
        second=0,
        microsecond=0,
    )


def _day_type(
    now: datetime,
) -> str:
    if now.weekday() >= 5:
        return "weekend"

    return "weekday"


def _event_datetime(
    value: str,
) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=LOCAL_TIMEZONE
        )

    return parsed.astimezone(
        LOCAL_TIMEZONE
    )


def _blocking_intervals(
    events: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    intervals = []

    for event in events:
        if event.get("all_day"):
            continue

        if (
            event.get("calendar")
            not in BLOCKING_CALENDARS
        ):
            continue

        start_value = event.get("start")
        end_value = event.get("end")

        if not start_value or not end_value:
            continue

        try:
            start = _event_datetime(
                start_value
            )
            end = _event_datetime(
                end_value
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if end <= start:
            continue

        duration = end - start

        if duration > timedelta(
            hours=MAX_BLOCKING_EVENT_HOURS
        ):
            continue

        if end <= window_start:
            continue

        if start >= window_end:
            continue

        intervals.append(
            (
                max(start, window_start),
                min(end, window_end),
            )
        )

    intervals.sort(
        key=lambda interval:
            interval[0]
    )

    return intervals


def _largest_free_interval(
    start: datetime,
    end: datetime,
    blocking: list[
        tuple[datetime, datetime]
    ],
) -> tuple[
    datetime | None,
    datetime | None,
    float,
]:
    cursor = start

    best_start = None
    best_end = None
    best_minutes = 0.0

    for block_start, block_end in blocking:
        if block_end <= cursor:
            continue

        if block_start > cursor:
            free_minutes = (
                block_start - cursor
            ).total_seconds() / 60

            if free_minutes > best_minutes:
                best_start = cursor
                best_end = block_start
                best_minutes = free_minutes

        cursor = max(
            cursor,
            block_end,
        )

        if cursor >= end:
            break

    if cursor < end:
        free_minutes = (
            end - cursor
        ).total_seconds() / 60

        if free_minutes > best_minutes:
            best_start = cursor
            best_end = end
            best_minutes = free_minutes

    return (
        best_start,
        best_end,
        round(best_minutes, 1),
    )


def _matching_activity_today(
    activities: list[dict],
    behaviour: dict,
) -> dict | None:
    activity_type = behaviour[
        "activity_type"
    ]

    typical_duration = (
        behaviour
        .get(
            "typical_activity",
            {},
        )
        .get(
            "duration_minutes"
        )
    )

    if typical_duration is None:
        return None

    minimum_duration = (
        typical_duration
        * SATISFACTION_DURATION_RATIO
    )

    for activity in activities:
        if (
            activity.get(
                "activity_type"
            ) != activity_type
        ):
            continue

        duration = activity.get(
            "duration_minutes"
        )

        if duration is None:
            continue

        if duration >= minimum_duration:
            return activity

    return None


def _children_constraint(
    context: dict,
    activity_type: str,
) -> dict:
    family = (
        context
        .get("household", {})
        .get("family", {})
    )

    capability = (
        family
        .get("capabilities", {})
        .get("child_presence")
    )

    children = family.get(
        "children",
        {},
    )

    any_with_me = children.get(
        "any_with_me"
    )

    allowed_with_children = (
        activity_type.lower()
        == "walking"
    )

    # Walking is explicitly possible whether or not
    # the children are present. Family state therefore
    # remains useful context, but is not a prerequisite
    # for permitting a Walking opportunity.
    if allowed_with_children:
        permitted = True

        if (
            capability is True
            and any_with_me is not None
        ):
            reason = "permitted"
        else:
            reason = (
                "permitted_family_context_optional"
            )

    elif capability is not True:
        permitted = False
        reason = (
            "family_context_unavailable"
        )

    elif any_with_me is None:
        permitted = False
        reason = (
            "family_state_unknown"
        )

    elif any_with_me:
        permitted = False
        reason = (
            "children_present_activity_constrained"
        )

    else:
        permitted = True
        reason = "permitted"

    return {
        "context_known":
            capability is True
            and any_with_me is not None,
        "children_with_me":
            any_with_me,
        "allowed_with_children":
            allowed_with_children,
        "permitted":
            permitted,
        "reason":
            reason,
    }


async def detect_activity_opportunities(
    context: dict,
    now: datetime | None = None,
) -> list[dict]:
    if now is None:
        now = datetime.now(
            LOCAL_TIMEZONE
        )
    else:
        now = now.astimezone(
            LOCAL_TIMEZONE
        )

    user = context.get(
        "user",
        {},
    )

    if user.get("home") is not True:
        return []

    analysis = (
        await analyse_activity_behaviour(
            days=ACTIVITY_LOOKBACK_DAYS
        )
    )

    if not analysis.get(
        "available"
    ):
        return []

    today_type = _day_type(now)

    activities_today = (
        analysis.get(
            "today_activities",
            []
        )
    )

    schedule = context.get(
        "schedule",
        {},
    )

    calendar_events = schedule.get(
        "events"
    )

    # Missing calendar evidence is different from a
    # known-empty calendar. Do not infer availability
    # when the evidence itself is unavailable.
    if not isinstance(
        calendar_events,
        list,
    ):
        return []

    calendar_capability = (
        context
        .get("capabilities", {})
        .get("calendar")
    )

    if calendar_capability is not True:
        return []

    candidates = []

    for behaviour in analysis.get(
        "qualified_behaviours",
        [],
    ):
        if (
            behaviour.get(
                "day_type"
            )
            != today_type
        ):
            continue

        typical_minutes = (
            behaviour
            .get(
                "typical_activity",
                {},
            )
            .get(
                "duration_minutes"
            )
        )

        if typical_minutes is None:
            continue

        window = behaviour.get(
            "window",
            {},
        )

        start_string = window.get(
            "start"
        )
        end_string = window.get(
            "end"
        )

        if not start_string or not end_string:
            continue

        start_hour, start_minute = map(
            int,
            start_string.split(":"),
        )

        end_hour, end_minute = map(
            int,
            end_string.split(":"),
        )

        window_start = now.replace(
            hour=start_hour,
            minute=start_minute,
            second=0,
            microsecond=0,
        )

        window_end = now.replace(
            hour=end_hour,
            minute=end_minute,
            second=0,
            microsecond=0,
        )

        if now < window_start:
            continue

        if now >= window_end:
            continue

        satisfied = (
            _matching_activity_today(
                activities_today,
                behaviour,
            )
        )

        if satisfied is not None:
            continue

        family_constraint = (
            _children_constraint(
                context,
                behaviour[
                    "activity_type"
                ],
            )
        )

        if not family_constraint[
            "permitted"
        ]:
            continue

        opportunity_start = max(
            now,
            window_start,
        )

        blocking = (
            _blocking_intervals(
                calendar_events,
                opportunity_start,
                window_end,
            )
        )

        (
            free_start,
            free_end,
            free_minutes,
        ) = _largest_free_interval(
            opportunity_start,
            window_end,
            blocking,
        )

        required_minutes = (
            typical_minutes
            + ACTIVITY_MARGIN_MINUTES
        )

        if (
            free_start is None
            or free_end is None
            or free_minutes
            < required_minutes
        ):
            continue

        candidates.append(
            {
                "type":
                    "activity_opportunity",
                "priority":
                    "candidate",
                "reason":
                    "learned_activity_window_available",
                "activity": {
                    "type":
                        behaviour[
                            "activity_type"
                        ],
                    "typical_time":
                        behaviour[
                            "typical_time"
                        ],
                    "typical_duration_minutes":
                        typical_minutes,
                    "typical_distance_miles":
                        behaviour[
                            "typical_activity"
                        ].get(
                            "distance_miles"
                        ),
                },
                "learned_behaviour":
                    behaviour,
                "opportunity": {
                    "window_start":
                        window_start.isoformat(),
                    "window_end":
                        window_end.isoformat(),
                    "free_start":
                        free_start.isoformat(),
                    "free_end":
                        free_end.isoformat(),
                    "free_minutes":
                        free_minutes,
                    "required_minutes":
                        round(
                            required_minutes,
                            1,
                        ),
                },
                "constraints": {
                    "user_home": True,
                    "family":
                        family_constraint,
                    "blocking_event_count":
                        len(blocking),
                },
                "today": {
                    "matching_activity_completed":
                        False,
                },
            }
        )

    return candidates
