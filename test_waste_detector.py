import asyncio
from unittest.mock import AsyncMock, patch

from app.observer.detectors.waste import (
    detect_waste_preparation,
)


BASE_CONTEXT = {
    "generated_at": "2026-09-30T20:30:00+01:00",
    "household": {
        "waste": {
            "next_collection": {
                "date": "2026-10-01",
                "types": ["Black Bin"],
            },
            "preparation_window": {
                "starts": "2026-09-30T19:00:00+01:00",
                "ends": "2026-10-01T00:00:00+01:00",
                "active": True,
                "put_out_from": "19:00",
            },
        },
    },
}


async def run_tests():
    passed = 0
    total = 5

    # 1. No waste context.
    result = await detect_waste_preparation(
        {
            "generated_at":
                "2026-09-30T20:30:00+01:00",
        }
    )

    ok = result == []
    print(
        f"{'PASS' if ok else 'FAIL'} "
        "no waste context"
    )
    passed += int(ok)

    # 2. Inactive preparation window.
    inactive = {
        **BASE_CONTEXT,
        "household": {
            "waste": {
                **BASE_CONTEXT["household"]["waste"],
                "preparation_window": {
                    **BASE_CONTEXT[
                        "household"
                    ]["waste"][
                        "preparation_window"
                    ],
                    "active": False,
                },
            },
        },
    }

    result = await detect_waste_preparation(
        inactive
    )

    ok = result == []
    print(
        f"{'PASS' if ok else 'FAIL'} "
        "inactive preparation window"
    )
    passed += int(ok)

    # 3. Evidence unavailable -> fail closed.
    with patch(
        "app.observer.detectors.waste."
        "entrance_activity",
        new=AsyncMock(
            return_value={
                "evidence_available": False,
                "occurred": False,
            }
        ),
    ):
        result = await detect_waste_preparation(
            BASE_CONTEXT
        )

    ok = result == []
    print(
        f"{'PASS' if ok else 'FAIL'} "
        "unknown evidence fails closed"
    )
    passed += int(ok)

    # 4. Entrance activity observed.
    with patch(
        "app.observer.detectors.waste."
        "entrance_activity",
        new=AsyncMock(
            return_value={
                "evidence_available": True,
                "occurred": True,
            }
        ),
    ):
        result = await detect_waste_preparation(
            BASE_CONTEXT
        )

    ok = result == []
    print(
        f"{'PASS' if ok else 'FAIL'} "
        "entrance activity suppresses candidate"
    )
    passed += int(ok)

    # 5. Active window + known absence of activity.
    evidence = {
        "evidence_available": True,
        "occurred": False,
        "count": 0,
    }

    with patch(
        "app.observer.detectors.waste."
        "entrance_activity",
        new=AsyncMock(
            return_value=evidence
        ),
    ):
        result = await detect_waste_preparation(
            BASE_CONTEXT
        )

    ok = (
        len(result) == 1
        and result[0]["type"]
            == "possible_bins_not_put_out"
        and result[0]["collection_date"]
            == "2026-10-01"
        and result[0]["evidence"][
            "entrance_activity"
        ] == evidence
    )

    print(
        f"{'PASS' if ok else 'FAIL'} "
        "candidate produced when evidence supports it"
    )
    passed += int(ok)

    print()
    print("===== SUMMARY =====")
    print(f"{passed}/{total} passed")

    if passed != total:
        raise SystemExit(1)


asyncio.run(run_tests())
