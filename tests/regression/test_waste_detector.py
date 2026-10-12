import pytest

import app.observer.detectors.waste as waste


def context(active=True):
    return {
        "generated_at":
            "2026-10-05T20:00:00+01:00",
        "household": {
            "waste": {
                "next_collection": {
                    "date": "2026-10-06",
                    "types": ["Recycling"],
                },
                "preparation_window": {
                    "active": active,
                    "starts":
                        "2026-10-05T19:00:00+01:00",
                },
            }
        },
    }


@pytest.mark.asyncio
async def test_inactive_window_no_candidate():
    result = (
        await waste.detect_waste_preparation(
            context(active=False)
        )
    )

    assert result == []


@pytest.mark.asyncio
async def test_unknown_evidence_fails_closed(
    monkeypatch,
):
    async def fake_evidence(**kwargs):
        return {
            "evidence_available": False,
            "occurred": False,
        }

    monkeypatch.setattr(
        waste,
        "entrance_activity",
        fake_evidence,
    )

    result = (
        await waste.detect_waste_preparation(
            context()
        )
    )

    assert result == []


@pytest.mark.asyncio
async def test_entrance_activity_suppresses_candidate(
    monkeypatch,
):
    async def fake_evidence(**kwargs):
        return {
            "evidence_available": True,
            "occurred": True,
        }

    monkeypatch.setattr(
        waste,
        "entrance_activity",
        fake_evidence,
    )

    result = (
        await waste.detect_waste_preparation(
            context()
        )
    )

    assert result == []


@pytest.mark.asyncio
async def test_no_entrance_activity_creates_candidate(
    monkeypatch,
):
    async def fake_evidence(**kwargs):
        return {
            "evidence_available": True,
            "occurred": False,
        }

    monkeypatch.setattr(
        waste,
        "entrance_activity",
        fake_evidence,
    )

    result = (
        await waste.detect_waste_preparation(
            context()
        )
    )

    assert len(result) == 1

    assert (
        result[0]["type"]
        == "possible_bins_not_put_out"
    )
