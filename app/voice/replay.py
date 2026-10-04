from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.storage.deliveries import (
    latest_proactive_delivery,
    record_delivery,
)
from app.voice.announcements import (
    announce_to_satellite,
    announce_to_user,
)


LOCAL_TIMEZONE = ZoneInfo(
    "Europe/London"
)


async def repeat_last_announcement(
    source_satellite: str | None = None,
) -> dict:
    """
    Replay the most recent successful proactive Jarvis
    announcement.

    A valid originating interaction endpoint is preferred.
    Otherwise, replay falls back to Jarvis's normal stable
    semantic user-location routing.

    Replay is reactive and does not create an Observer
    candidate, invoke judgement, modify the attention
    ledger or participate in proactive cooldown.
    """

    original = latest_proactive_delivery()

    if original is None:
        return {
            "replayed": False,
            "reason": "no_recent_announcement",
        }

    try:
        delivered_at = datetime.fromisoformat(
            original["delivered_at"]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return {
            "replayed": False,
            "reason":
                "invalid_delivery_timestamp",
        }

    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(
            tzinfo=LOCAL_TIMEZONE
        )

    now = datetime.now(
        LOCAL_TIMEZONE
    )

    age_seconds = (
        now - delivered_at
    ).total_seconds()

    if (
        age_seconds < 0
        or age_seconds
        > settings.replay_max_age_seconds
    ):
        return {
            "replayed": False,
            "reason": "no_recent_announcement",
            "age_seconds":
                max(0, int(age_seconds)),
            "max_age_seconds":
                settings.replay_max_age_seconds,
        }

    message = original["message"]

    delivery_route = (
        "semantic_user_location"
    )

    if source_satellite:
        result = await announce_to_satellite(
            message,
            source_satellite,
            preannounce=True,
        )

        if result.get("announced") is True:
            delivery_route = (
                "interaction_endpoint"
            )

        elif (
            result.get("reason")
            == "invalid_source_satellite"
        ):
            result = await announce_to_user(
                message,
                preannounce=True,
            )

        else:
            return {
                "replayed": False,
                "reason":
                    result.get(
                        "reason",
                        "announcement_failed",
                    ),
                "original": original,
                "voice": result,
            }

    else:
        result = await announce_to_user(
            message,
            preannounce=True,
        )

    if result.get("announced") is not True:
        return {
            "replayed": False,
            "reason":
                result.get(
                    "reason",
                    "announcement_failed",
                ),
            "original": original,
            "voice": result,
        }

    location = result.get(
        "location",
        {},
    )

    target = result.get(
        "target",
        {},
    )

    replay_delivery = record_delivery(
        candidate_key=original.get(
            "candidate_key"
        ),
        candidate_type=original.get(
            "candidate_type"
        ),
        message=message,
        delivery_type=
            "user_requested_replay",
        area=location.get(
            "area"
        ),
        target_entity=target.get(
            "entity_id"
        ),
        metadata={
            "original_delivery_id":
                original.get("id"),
            "original_delivered_at":
                original.get(
                    "delivered_at"
                ),
            "delivery_route":
                delivery_route,
        },
    )

    return {
        "replayed": True,
        "reason": "announcement_replayed",
        "message": message,
        "original_delivery_id":
            original.get("id"),
        "original_delivered_at":
            original.get(
                "delivered_at"
            ),
        "age_seconds":
            int(age_seconds),
        "area":
            location.get("area"),
        "target_entity":
            target.get("entity_id"),
        "delivery_route":
            delivery_route,
        "delivery":
            replay_delivery,
    }
