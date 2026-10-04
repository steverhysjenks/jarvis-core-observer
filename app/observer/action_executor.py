import logging

from app.storage.deliveries import (
    record_delivery,
)
from app.storage.ledger import (
    mark_announced,
)
from app.voice.announcements import (
    announce_to_user,
)


logger = logging.getLogger(__name__)


async def execute_action(
    policy: dict,
    candidate_key: str,
    candidate_type: str | None = None,
) -> dict:
    """
    Execute an action that has already been approved by
    the deterministic action policy.

    The executor does not decide whether an action should
    happen. It only performs an explicitly permitted
    capability.

    Successful voice delivery is recorded in the
    attention ledger immediately after Home Assistant
    accepts the announcement.

    Delivery history is supplementary. Failure to write
    notification history must never cause an already
    delivered proactive announcement to be repeated.
    """

    if policy.get("allowed") is not True:
        return {
            "executed": False,
            "reason": "action_not_allowed",
        }

    interaction = policy.get(
        "interaction"
    )

    if interaction != "announce":
        return {
            "executed": False,
            "reason":
                "unsupported_interaction",
        }

    message = policy.get(
        "message"
    )

    result = await announce_to_user(
        message,
        preannounce=policy.get(
            "preannounce",
            True,
        ),
    )

    if result.get("announced") is not True:
        return {
            "executed": False,
            "reason":
                result.get(
                    "reason",
                    "announcement_failed",
                ),
            "voice": result,
        }

    # Safety-critical lifecycle write.
    #
    # Once HA has accepted the announcement, ensure the
    # situation cannot be proactively announced again.
    ledger = mark_announced(
        candidate_key
    )

    delivery = None
    delivery_history_error = None

    try:
        location = result.get(
            "location",
            {},
        )

        target = result.get(
            "target",
            {},
        )

        delivery = record_delivery(
            candidate_key=candidate_key,
            candidate_type=candidate_type,
            message=message,
            delivery_type="proactive",
            area=location.get(
                "area"
            ),
            target_entity=target.get(
                "entity_id"
            ),
            metadata={
                "preannounce":
                    policy.get(
                        "preannounce",
                        True,
                    ),
            },
        )

    except Exception as exc:
        # History is useful but must not compromise the
        # anti-repeat safety lifecycle.
        delivery_history_error = (
            f"{type(exc).__name__}: {exc}"
        )

        logger.exception(
            "Announcement delivered but delivery "
            "history could not be recorded."
        )

    return {
        "executed": True,
        "reason": "announcement_delivered",
        "interaction": interaction,
        "voice": result,
        "ledger": {
            "candidate_key":
                candidate_key,
            "announced_at":
                ledger.get(
                    "announced_at"
                ),
            "announcement_count":
                ledger.get(
                    "announcement_count"
                ),
        },
        "delivery": delivery,
        "delivery_history_error":
            delivery_history_error,
    }
