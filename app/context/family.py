import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adapters.homeassistant import ha_client


LOCAL_TIMEZONE = ZoneInfo("Europe/London")

AMELIA_WITH_ME_ENTITY = (
    "input_boolean.amelia_with_me"
)

JOSHUA_WITH_ME_ENTITY = (
    "input_boolean.joshua_with_me"
)


def _boolean_state(
    state: dict | None,
) -> bool | None:
    """
    Convert a Home Assistant input_boolean state
    to a Python boolean.

    Unknown, unavailable or missing states remain
    None rather than being interpreted as False.
    """
    if state is None:
        return None

    value = state.get("state")

    if value == "on":
        return True

    if value == "off":
        return False

    return None


async def build_family_context() -> dict:
    now = datetime.now(
        LOCAL_TIMEZONE
    )

    (
        amelia_state,
        joshua_state,
    ) = await asyncio.gather(
        ha_client.get_state_optional(
            AMELIA_WITH_ME_ENTITY
        ),
        ha_client.get_state_optional(
            JOSHUA_WITH_ME_ENTITY
        ),
    )

    amelia_with_me = _boolean_state(
        amelia_state
    )

    joshua_with_me = _boolean_state(
        joshua_state
    )

    known = (
        amelia_with_me is not None
        and joshua_with_me is not None
    )

    if known:
        any_with_me = (
            amelia_with_me
            or joshua_with_me
        )

        both_with_me = (
            amelia_with_me
            and joshua_with_me
        )

        count_with_me = sum(
            (
                amelia_with_me,
                joshua_with_me,
            )
        )
    else:
        any_with_me = None
        both_with_me = None
        count_with_me = None

    return {
        "generated_at": now.isoformat(),
        "children": {
            "amelia": {
                "with_me":
                    amelia_with_me,
                "source":
                    AMELIA_WITH_ME_ENTITY,
            },
            "joshua": {
                "with_me":
                    joshua_with_me,
                "source":
                    JOSHUA_WITH_ME_ENTITY,
            },
            "any_with_me":
                any_with_me,
            "both_with_me":
                both_with_me,
            "count_with_me":
                count_with_me,
        },
        "capabilities": {
            "child_presence": known,
        },
    }
