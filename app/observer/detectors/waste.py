from datetime import datetime
from zoneinfo import ZoneInfo

from app.context.evidence import entrance_activity


LOCAL_TIMEZONE = ZoneInfo("Europe/London")


async def detect_waste_preparation(
    context: dict,
) -> list[dict]:
    """
    Detect an active waste preparation window where
    entrance activity has not been observed.

    Context acquisition is performed by Observer.
    This detector only evaluates that context and
    requests historical evidence when required.
    """

    waste = (
        context
        .get("household", {})
        .get("waste")
    )

    if not waste:
        return []

    collection = waste.get(
        "next_collection"
    )

    window = waste.get(
        "preparation_window"
    )

    if not collection or not window:
        return []

    if not window.get("active"):
        return []

    now = datetime.fromisoformat(
        context["generated_at"]
    ).astimezone(
        LOCAL_TIMEZONE
    )

    preparation_start = (
        datetime.fromisoformat(
            window["starts"]
        ).astimezone(
            LOCAL_TIMEZONE
        )
    )

    evidence = await entrance_activity(
        start=preparation_start,
        end=now,
    )

    # Unknown evidence must never be interpreted
    # as evidence that something did not happen.
    if not evidence["evidence_available"]:
        return []

    # Entrance activity is consistent with the bins
    # having been put outside. It is not proof.
    if evidence["occurred"]:
        return []

    return [
        {
            "type":
                "possible_bins_not_put_out",
            "priority":
                "candidate",
            "reason": (
                "waste_collection_tomorrow_"
                "no_entrance_activity"
            ),
            "collection_date":
                collection["date"],
            "collection_types":
                collection["types"],
            "preparation_window":
                window,
            "evidence": {
                "entrance_activity":
                    evidence,
            },
        }
    ]
