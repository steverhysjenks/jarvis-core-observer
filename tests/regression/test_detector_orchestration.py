import pytest

import app.observer.detectors as detectors


@pytest.mark.asyncio
async def test_all_detector_outputs_are_accumulated(
    monkeypatch,
):
    monkeypatch.setattr(
        detectors,
        "detect_upcoming_departure",
        lambda context: {
            "type": "calendar_departure",
        },
    )

    async def routine(context):
        return [
            {
                "type":
                    "routine_departure_deviation"
            }
        ]

    async def waste(context):
        return [
            {
                "type":
                    "possible_bins_not_put_out"
            }
        ]

    async def activity(context):
        return [
            {
                "type":
                    "activity_opportunity"
            }
        ]

    monkeypatch.setattr(
        detectors,
        "detect_routine_departure_deviation",
        routine,
    )
    monkeypatch.setattr(
        detectors,
        "detect_waste_preparation",
        waste,
    )
    monkeypatch.setattr(
        detectors,
        "detect_activity_opportunities",
        activity,
    )

    result = await detectors.run_detectors({})

    assert [
        item["type"]
        for item in result
    ] == [
        "calendar_departure",
        "routine_departure_deviation",
        "possible_bins_not_put_out",
        "activity_opportunity",
    ]


@pytest.mark.asyncio
async def test_calendar_detector_legacy_list_supported(
    monkeypatch,
):
    monkeypatch.setattr(
        detectors,
        "detect_upcoming_departure",
        lambda context: [
            {"type": "one"},
            {"type": "two"},
        ],
    )

    async def empty(context):
        return []

    monkeypatch.setattr(
        detectors,
        "detect_routine_departure_deviation",
        empty,
    )
    monkeypatch.setattr(
        detectors,
        "detect_waste_preparation",
        empty,
    )
    monkeypatch.setattr(
        detectors,
        "detect_activity_opportunities",
        empty,
    )

    result = await detectors.run_detectors({})

    assert [x["type"] for x in result] == [
        "one",
        "two",
    ]
