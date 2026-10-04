from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.storage.ledger import (
    get_entry,
    latest_announcement,
)
from app.voice.routing import (
    resolve_voice_target,
)


LOCAL_TIMEZONE = ZoneInfo(
    "Europe/London"
)

GLOBAL_ANNOUNCEMENT_COOLDOWN_SECONDS = (
    settings.global_announcement_cooldown_seconds
)


def evaluate_action_policy(
    evaluation: dict,
    user: dict,
    mode: str,
    candidate_key: str | None = None,
) -> dict:
    """
    Decide whether an evaluated attention candidate is
    eligible for a proactive voice action.

    This function has no external action side effects.
    It cannot announce or call Home Assistant.
    """

    judgement = evaluation.get(
        "judgement",
        {},
    )

    decision = judgement.get(
        "decision"
    )

    message = judgement.get(
        "message"
    )

    location = user.get(
        "location",
        {},
    )

    area = location.get("area")

    # Gate 1:
    # External action is structurally unavailable unless
    # the observer has explicitly been placed in live mode.
    if mode != "live":
        return {
            "allowed": False,
            "reason": "observer_not_live",
        }

    # Gate 2:
    # Only an explicit interrupt judgement can proceed
    # towards an external action.
    if decision != "interrupt":
        return {
            "allowed": False,
            "reason": "judgement_not_interrupt",
        }

    # Gate 3:
    # An announcement requires a usable message.
    if not isinstance(message, str):
        return {
            "allowed": False,
            "reason": "announcement_message_missing",
        }

    if not message.strip():
        return {
            "allowed": False,
            "reason": "announcement_message_missing",
        }

    # Gate 4:
    # Situation lifecycle is authoritative. Resolved
    # situations cannot act and an already-announced
    # occurrence must not nag repeatedly.
    if candidate_key:
        ledger_entry = get_entry(
            candidate_key
        )

        if ledger_entry is not None:
            if (
                ledger_entry.get("status")
                == "resolved"
            ):
                return {
                    "allowed": False,
                    "reason":
                        "situation_resolved",
                }

            if ledger_entry.get(
                "announced_at"
            ):
                return {
                    "allowed": False,
                    "reason":
                        "situation_already_announced",
                    "announced_at":
                        ledger_entry.get(
                            "announced_at"
                        ),
                    "announcement_count":
                        ledger_entry.get(
                            "announcement_count",
                            0,
                        ),
                }

    # Gate 5:
    # Cross-situation cooldown is secondary to situation
    # lifecycle. It prevents several different valid
    # interruptions arriving in rapid succession.
    latest = latest_announcement()

    if latest is not None:
        latest_key = latest.get(
            "candidate_key"
        )

        latest_at = latest.get(
            "announced_at"
        )

        if (
            latest_at
            and latest_key != candidate_key
        ):
            try:
                announced_at = (
                    datetime.fromisoformat(
                        latest_at
                    )
                )

                now = datetime.now(
                    LOCAL_TIMEZONE
                )

                elapsed_seconds = (
                    now - announced_at
                ).total_seconds()

                if (
                    elapsed_seconds
                    < GLOBAL_ANNOUNCEMENT_COOLDOWN_SECONDS
                ):
                    return {
                        "allowed": False,
                        "reason":
                            "global_announcement_cooldown",
                        "seconds_since_last_announcement":
                            round(
                                elapsed_seconds,
                                1,
                            ),
                        "cooldown_seconds":
                            GLOBAL_ANNOUNCEMENT_COOLDOWN_SECONDS,
                    }

            except (
                TypeError,
                ValueError,
            ):
                # Malformed historical timestamps must
                # not accidentally create a permanent
                # cooldown.
                pass

    # Gate 6:
    # The primary user must currently be home.
    if user.get("home") is not True:
        return {
            "allowed": False,
            "reason": "primary_user_not_home",
        }

    # Gate 7:
    # Room-level routing currently trusts Bermuda only.
    if location.get("source") != "bermuda":
        return {
            "allowed": False,
            "reason": "room_location_unavailable",
        }

    # Gate 8:
    # Never route speech from an instantaneous/noisy room
    # transition.
    if location.get("stable") is not True:
        return {
            "allowed": False,
            "reason": "user_location_not_stable",
            "area": area,
            "stable_for_seconds":
                location.get(
                    "stable_for_seconds"
                ),
        }

    # Gate 9:
    # Areas without an explicitly configured voice
    # endpoint fail closed.
    target = resolve_voice_target(
        area
    )

    if not target["available"]:
        return {
            "allowed": False,
            "reason": target["reason"],
            "area": area,
            "target": target,
        }

    return {
        "allowed": True,
        "reason": "voice_action_eligible",
        "interaction": "announce",
        "audience": "primary_user",
        "message": message.strip(),
        "preannounce": True,
        "area": area,
        "target": target,
    }
