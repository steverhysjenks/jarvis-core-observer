import app.storage.ledger as ledger


def candidate(date="2026-10-05"):
    return {
        "type": "routine_departure_deviation",
        "routine": {
            "weekday": "Monday",
            "typical_time": "08:00",
        },
        "current": {
            "time": (
                f"{date}T08:05:00+01:00"
            ),
            "minutes_from_expected": 5.0,
            "user_home": True,
            "user_area": "Office area",
        },
    }


def test_repeated_candidate_is_one_situation(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        ledger,
        "DATABASE_PATH",
        tmp_path / "ledger.db",
    )

    first = ledger.record_candidate(
        candidate(),
        mode="shadow",
    )

    second = ledger.record_candidate(
        candidate(),
        mode="shadow",
    )

    assert first["candidate_key"] == second["candidate_key"]
    assert first["ledger_status"] == "new"
    assert second["ledger_status"] == "existing"

    entry = ledger.get_entry(first["candidate_key"])

    assert entry["seen_count"] == 2
    assert entry["status"] == "open"


def test_every_observation_is_retained(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        ledger,
        "DATABASE_PATH",
        tmp_path / "ledger.db",
    )

    ledger.record_candidate(candidate())
    ledger.record_candidate(candidate())

    observations = ledger.recent_observations()

    assert len(observations) == 2
    assert (
        observations[0]["candidate_key"]
        == observations[1]["candidate_key"]
    )


def test_next_occurrence_is_new_situation(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        ledger,
        "DATABASE_PATH",
        tmp_path / "ledger.db",
    )

    first = ledger.record_candidate(
        candidate("2026-10-05")
    )

    second = ledger.record_candidate(
        candidate("2026-10-12")
    )

    assert first["candidate_key"] != second["candidate_key"]

    entries = ledger.recent_entries()

    assert len(entries) == 2


def test_announced_does_not_mean_resolved(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        ledger,
        "DATABASE_PATH",
        tmp_path / "ledger.db",
    )

    result = ledger.record_candidate(candidate())
    key = result["candidate_key"]

    announced = ledger.mark_announced(key)

    assert announced["announced_at"] is not None
    assert announced["announcement_count"] == 1
    assert announced["status"] == "open"
    assert announced["resolved_at"] is None


def test_resolution_preserves_announcement_history(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        ledger,
        "DATABASE_PATH",
        tmp_path / "ledger.db",
    )

    result = ledger.record_candidate(candidate())
    key = result["candidate_key"]

    ledger.mark_announced(key)

    resolved = ledger.mark_resolved(
        key,
        "primary_user_no_longer_home",
    )

    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert (
        resolved["resolution_reason"]
        == "primary_user_no_longer_home"
    )
    assert resolved["announcement_count"] == 1


def test_resolved_situation_not_returned_as_open(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        ledger,
        "DATABASE_PATH",
        tmp_path / "ledger.db",
    )

    result = ledger.record_candidate(candidate())
    key = result["candidate_key"]

    assert len(ledger.open_entries()) == 1

    ledger.mark_resolved(key, "test")

    assert ledger.open_entries() == []
