import pytest

from app.voice.routing import (
    VOICE_TARGETS,
    resolve_voice_target,
)


@pytest.mark.parametrize(
    "area",
    [
        "Office area",
        "Kitchen",
        "Master Bedroom",
    ],
)
def test_known_area_has_voice_endpoint(area):
    result = resolve_voice_target(area)

    assert result["available"] is True
    assert result["area"] == area
    assert result["entity_id"] == VOICE_TARGETS[area]
    assert result["reason"] == "exact_area_match"


@pytest.mark.parametrize(
    "area",
    [
        None,
        "",
    ],
)
def test_unknown_user_area_fails_closed(area):
    result = resolve_voice_target(area)

    assert result["available"] is False
    assert result["entity_id"] is None
    assert result["reason"] == "user_area_unknown"


def test_unmapped_room_fails_closed():
    result = resolve_voice_target(
        "Living Room"
    )

    assert result["available"] is False
    assert result["entity_id"] is None

    assert (
        result["reason"]
        == "no_voice_endpoint_for_area"
    )


def test_no_implicit_room_fallback():
    result = resolve_voice_target(
        "Joshua Room"
    )

    assert result["available"] is False
