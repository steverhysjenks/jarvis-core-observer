import pytest
from pydantic import ValidationError

from app.judgement.qwen import (
    Judgement,
)


def test_valid_ignore():
    judgement = Judgement.model_validate(
        {
            "decision": "ignore",
            "confidence": 0.8,
            "reason": "Nothing useful to report.",
            "message": None,
        }
    )

    assert judgement.decision == "ignore"


def test_valid_monitor():
    judgement = Judgement.model_validate(
        {
            "decision": "monitor",
            "confidence": 0.5,
            "reason": "Situation may develop.",
            "message": None,
        }
    )

    assert judgement.decision == "monitor"


def test_valid_interrupt_requires_message():
    judgement = Judgement.model_validate(
        {
            "decision": "interrupt",
            "confidence": 0.9,
            "reason": "Timely information.",
            "message": "The bins are collected tomorrow.",
        }
    )

    assert judgement.message


def test_interrupt_without_message_rejected():
    with pytest.raises(ValidationError):
        Judgement.model_validate(
            {
                "decision": "interrupt",
                "confidence": 0.9,
                "reason": "Timely information.",
                "message": None,
            }
        )


def test_ignore_with_message_rejected():
    with pytest.raises(ValidationError):
        Judgement.model_validate(
            {
                "decision": "ignore",
                "confidence": 0.8,
                "reason": "Ignore it.",
                "message": "This must not be spoken.",
            }
        )


def test_unknown_decision_rejected():
    with pytest.raises(ValidationError):
        Judgement.model_validate(
            {
                "decision": "do_something",
                "confidence": 0.8,
                "reason": "Invalid.",
                "message": None,
            }
        )


@pytest.mark.parametrize(
    "confidence",
    [-0.1, 1.1, 99],
)
def test_invalid_confidence_rejected(confidence):
    with pytest.raises(ValidationError):
        Judgement.model_validate(
            {
                "decision": "ignore",
                "confidence": confidence,
                "reason": "Invalid confidence.",
                "message": None,
            }
        )


def test_extra_model_fields_rejected():
    with pytest.raises(ValidationError):
        Judgement.model_validate(
            {
                "decision": "ignore",
                "confidence": 0.8,
                "reason": "No action.",
                "message": None,
                "turn_off_the_house": True,
            }
        )
