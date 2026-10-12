from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import app.observer.action_policy as policy_module


TZ = ZoneInfo("Europe/London")


def evaluation(
    decision="interrupt",
    message="Test announcement.",
):
    return {
        "judgement": {
            "decision": decision,
            "confidence": 0.9,
            "reason": "Test",
            "message": message,
        }
    }


def user(
    home=True,
    source="bermuda",
    stable=True,
    area="Office area",
):
    return {
        "home": home,
        "location": {
            "area": area,
            "source": source,
            "stable": stable,
            "stable_for_seconds": 60,
        },
    }


@pytest.fixture(autouse=True)
def clean_ledger(monkeypatch):
    monkeypatch.setattr(
        policy_module,
        "get_entry",
        lambda key: None,
    )

    monkeypatch.setattr(
        policy_module,
        "latest_announcement",
        lambda: None,
    )


def test_shadow_mode_can_never_act():
    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(),
            mode="shadow",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False
    assert result["reason"] == "observer_not_live"


@pytest.mark.parametrize(
    "decision",
    [
        "ignore",
        "monitor",
    ],
)
def test_only_interrupt_can_act(decision):
    result = (
        policy_module.evaluate_action_policy(
            evaluation(
                decision=decision,
                message=None,
            ),
            user(),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "judgement_not_interrupt"
    )


@pytest.mark.parametrize(
    "message",
    [
        None,
        "",
        "   ",
    ],
)
def test_interrupt_requires_message(message):
    result = (
        policy_module.evaluate_action_policy(
            evaluation(message=message),
            user(),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "announcement_message_missing"
    )


def test_resolved_situation_cannot_act(
    monkeypatch,
):
    monkeypatch.setattr(
        policy_module,
        "get_entry",
        lambda key: {
            "status": "resolved",
            "announced_at": None,
        },
    )

    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False
    assert result["reason"] == "situation_resolved"


def test_already_announced_situation_cannot_nag(
    monkeypatch,
):
    monkeypatch.setattr(
        policy_module,
        "get_entry",
        lambda key: {
            "status": "open",
            "announced_at":
                "2026-10-05T12:00:00+01:00",
            "announcement_count": 1,
        },
    )

    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "situation_already_announced"
    )


def test_global_cooldown_blocks_different_situation(
    monkeypatch,
):
    recent = (
        datetime.now(TZ)
        - timedelta(seconds=30)
    )

    monkeypatch.setattr(
        policy_module,
        "latest_announcement",
        lambda: {
            "candidate_key": "other:key",
            "announced_at":
                recent.isoformat(),
        },
    )

    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(),
            mode="live",
            candidate_key="new:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "global_announcement_cooldown"
    )


def test_user_must_be_home():
    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(home=False),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "primary_user_not_home"
    )


def test_room_source_must_be_bermuda():
    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(source="home_assistant_zone"),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "room_location_unavailable"
    )


def test_unstable_location_blocks_speech():
    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(stable=False),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "user_location_not_stable"
    )


def test_unmapped_area_blocks_speech():
    result = (
        policy_module.evaluate_action_policy(
            evaluation(),
            user(area="Living Room"),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is False

    assert (
        result["reason"]
        == "no_voice_endpoint_for_area"
    )


def test_valid_live_action_is_allowed():
    result = (
        policy_module.evaluate_action_policy(
            evaluation(
                message="  Useful information.  "
            ),
            user(),
            mode="live",
            candidate_key="test:key",
        )
    )

    assert result["allowed"] is True
    assert result["interaction"] == "announce"
    assert result["audience"] == "primary_user"
    assert result["preannounce"] is True
    assert result["message"] == "Useful information."

    assert (
        result["target"]["available"]
        is True
    )
