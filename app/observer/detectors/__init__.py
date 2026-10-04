from app.observer.detectors.departure import (
    detect_upcoming_departure,
)
from app.observer.detectors.routine_departure import (
    detect_routine_departure_deviation,
)
from app.observer.detectors.waste import (
    detect_waste_preparation,
)
from app.observer.detectors.activity import (
    detect_activity_opportunities,
)


async def run_detectors(
    context: dict,
) -> list[dict]:
    candidates = []

    # Calendar-based departure detector.
    # Legacy interface: may return candidate/list/None.
    calendar_result = detect_upcoming_departure(
        context
    )

    if calendar_result:
        if isinstance(calendar_result, list):
            candidates.extend(calendar_result)
        else:
            candidates.append(calendar_result)

    # Learned routine deviation detector.
    routine_results = (
        await detect_routine_departure_deviation(
            context
        )
    )

    if routine_results:
        candidates.extend(routine_results)

    # Explicit household-knowledge detector.
    waste_results = await detect_waste_preparation(
        context
    )

    if waste_results:
        candidates.extend(waste_results)

    # Learned physical-activity opportunity detector.
    activity_results = await detect_activity_opportunities(
        context
    )

    if activity_results:
        candidates.extend(activity_results)

    return candidates
