"""All HA calls are mocks; global audit hooks additionally prohibit network/process I/O."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.adapters.homeassistant import HomeAssistantError
from app.adapters.jellyfin import CatalogueUnavailable, Movie
from app.capabilities.video import VideoCapability, context
from app.video import playback
from app.voice.requests import VoiceRequest

MOVIE = Movie("a" * 32, "Forrest Gump", 1994, "13")
OBSERVED_HA = json.loads((Path(__file__).resolve().parents[1] / "fixtures/ha-infuse-20261101.json").read_text())


def request(text="Play Forrest Gump on the living room TV", identity="initial", **kwargs):
    values = dict(text=text, request_id=identity, origin="fixture-assist", user_context="fixture-user",
                  conversation_id="fixture-conversation")
    values.update(kwargs)
    return VoiceRequest(**values)


@pytest.fixture
def workflow(monkeypatch):
    monkeypatch.setenv("VIDEO_ENABLED", "true")
    monkeypatch.setenv("VIDEO_TV_SOURCE", "HDMI 1")
    monkeypatch.setattr(playback, "POLL_SECONDS", 0)
    state = {"launched": False, "post_launch_reads": 0, "apple_state": "playing", "source": "HDMI 1"}
    async def get_state(entity):
        if entity == playback.WAKE_AUTOMATION:
            return {"state": "on", "attributes": {"current": 0}}
        assert entity in {playback.APPLE_TV, playback.SONY_TV}
        if entity == playback.SONY_TV:
            value = deepcopy(OBSERVED_HA["sony"])
            value["attributes"]["source"] = state["source"]
            return value
        value = deepcopy(OBSERVED_HA["idle"])
        value["state"] = state["apple_state"]
        if state["launched"]:
            state["post_launch_reads"] += 1
            if state["post_launch_reads"] > 1:
                value = deepcopy(OBSERVED_HA["playing"])
        return value
    async def call(domain, service, data):
        assert (domain, service) == ("media_player", "play_media")
        assert data == {"entity_id": playback.APPLE_TV, "media_content_type": "url",
                        "media_content_id": "infuse://movie/13?play"}
        state["launched"] = True
    client = AsyncMock()
    client.get_state.side_effect = get_state
    client.call_service.side_effect = call
    catalogue = AsyncMock()
    catalogue.lookup.return_value = "resolved", MOVIE, []
    capability = VideoCapability(catalogue, playback.VideoPlayback(client))
    return capability, client, catalogue, state


@pytest.mark.asyncio
async def test_prepare_is_read_only_and_separate(workflow):
    cap, client, catalogue, state = workflow
    result = await cap.handle(request("Get Forrest Gump ready on the TV"))
    assert result.handled and result.result["status"] == "prepared"
    assert result.result["movie"]["tmdb_id"] == "13"
    assert "No playback" in result.metadata["speech"]
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_occupied_confirmation_launches_but_real_ha_evidence_stays_uncertain(workflow):
    cap, client, catalogue, _ = workflow
    first = await cap.handle(request())
    assert first.result["status"] == "confirmation_required" and not first.handled
    client.call_service.assert_not_awaited()
    result = await cap.handle(request("Confirm video takeover", "confirm"))
    assert not result.handled and result.result["status"] == "uncertain"
    assert client.call_service.await_count == 1
    assert cap.uncertain


@pytest.mark.asyncio
async def test_duplicate_confirmation_concurrently_sends_exactly_one_command(workflow):
    cap, client, _, _ = workflow
    await cap.handle(request())
    confirm = request("Confirm video takeover", "confirm")
    a, b = await asyncio.gather(cap.handle(confirm), cap.handle(confirm))
    assert a.result["status"] == b.result["status"] == "uncertain"
    assert b.result["receipt"] == {"recorded_outcome": "uncertain", "fresh_verification": False}
    assert client.call_service.await_count == 1


@pytest.mark.asyncio
async def test_request_id_reuse_for_different_details_is_rejected(workflow):
    cap, client, _, _ = workflow
    await cap.handle(request())
    result = await cap.handle(request("Play the movie Dune on the TV"))
    assert result.result["status"] == "request_conflict"
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("conversation_id", "other"), ("user_context", "other"),
    ("origin", "other"), ("satellite", "other"), ("listener", "other")])
async def test_confirmation_cannot_cross_context(field, value, workflow):
    cap, client, _, _ = workflow
    await cap.handle(request())
    result = await cap.handle(request("Confirm video takeover", "confirm", **{field: value}))
    assert result.result["status"] == "confirmation_expired"
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_and_cancelled_confirmations_never_launch(workflow):
    cap, client, _, _ = workflow
    original = request()
    await cap.handle(original)
    pending = cap.pending[context(original)]
    cap.pending[context(original)] = (0, *pending[1:])
    assert (await cap.handle(request("Confirm video takeover", "expired"))).result["status"] == "confirmation_expired"
    await cap.handle(request(identity="again"))
    assert (await cap.handle(request("Cancel video takeover", "cancel"))).result["status"] == "cancelled"
    assert (await cap.handle(request("Confirm video takeover", "after-cancel"))).result["status"] == "confirmation_expired"
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_viewing_or_catalogue_requires_new_request(workflow):
    cap, client, catalogue, state = workflow
    await cap.handle(request())
    state["apple_state"] = "paused"
    assert (await cap.handle(request("Confirm video takeover", "changed"))).result["status"] == "state_changed"
    await cap.handle(request(identity="again"))
    catalogue.lookup.return_value = "resolved", Movie("b" * 32, "Forrest Gump", 1994, "999"), []
    assert (await cap.handle(request("Confirm video takeover", "changed-film"))).result["status"] == "state_changed"
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("text,kwargs,status", [
    ("Play Forrest Gump on the bedroom TV", {}, "unsupported_room"),
    ("Play Forrest Gump", {"area": "media_player.other"}, "unsupported_room"),
    ("Play Forrest Gump on the TV", {"request_id": None}, "invalid_request"),
    ("Play https://unsafe.invalid on the TV", {}, "invalid_request"),
    ("Play Forrest Gump; turn off lights on the TV", {}, "invalid_request"),
])
async def test_unsafe_requests_never_contact_dependencies(text, kwargs, status, workflow):
    cap, client, catalogue, _ = workflow
    assert (await cap.handle(request(text, **kwargs))).result["status"] == status
    catalogue.lookup.assert_not_awaited()
    client.get_state.assert_not_awaited()
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["not_found", "ambiguous"])
async def test_unresolved_film_never_contacts_ha(status, workflow):
    cap, client, catalogue, _ = workflow
    catalogue.lookup.return_value = status, None, []
    result = await cap.handle(request())
    assert result.claimed and not result.handled and result.result["status"] == status
    client.get_state.assert_not_awaited()
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_ready_input_no_wake_or_source_selection(workflow):
    cap, client, _, state = workflow
    state["source"] = "some-other-input"
    result = await cap.handle(request())
    assert result.result["status"] == "unavailable"
    client.call_service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["catalogue", "ha_read", "ha_command"])
async def test_outage_before_or_during_command_fails_closed(stage, workflow):
    cap, client, catalogue, _ = workflow
    if stage == "catalogue":
        catalogue.lookup.side_effect = CatalogueUnavailable()
    elif stage == "ha_read":
        client.get_state.side_effect = HomeAssistantError("private-upstream-error")
    else:
        await cap.handle(request())
        client.call_service.side_effect = HomeAssistantError("private-upstream-error")
    result = await cap.handle(request("Confirm video takeover", "confirm") if stage == "ha_command" else request())
    assert result.result["status"] == ("uncertain" if stage == "ha_command" else "unavailable")
    assert not result.handled and "private-upstream" not in str(result.as_dict())
    if stage == "ha_command":
        assert cap.uncertain
        assert (await cap.handle(request(identity="new"))).result["status"] == "uncertain"
        assert client.call_service.await_count == 1
    else:
        client.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_command_timeout_cancels_and_blocks_automatic_retries(monkeypatch, workflow):
    from app.capabilities import video
    cap, client, _, _ = workflow
    await cap.handle(request())
    cancelled = []
    async def slow(*args):
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)
    client.call_service.side_effect = slow
    monkeypatch.setattr(video, "DEADLINE_SECONDS", 0.03)
    result = await cap.handle(request("Confirm video takeover", "confirm"))
    assert result.result["status"] == "uncertain" and cap.uncertain and cancelled
    assert (await cap.handle(request("Confirm video takeover", "confirm"))).result["status"] == "uncertain"
    assert (await cap.handle(request(identity="new"))).result["status"] == "uncertain"
    assert client.call_service.await_count == 1


@pytest.mark.asyncio
async def test_caller_cancellation_keeps_uncertain_receipt_and_no_orphan(workflow):
    cap, client, _, _ = workflow
    await cap.handle(request())
    entered = asyncio.Event()
    cancelled = []
    async def slow(*args):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)
    client.call_service.side_effect = slow
    confirm = request("Confirm video takeover", "confirm")
    task = asyncio.create_task(cap.handle(confirm))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled and cap.uncertain
    assert (await cap.handle(confirm)).result["status"] == "uncertain"
    assert client.call_service.await_count == 1


@pytest.mark.asyncio
async def test_realistic_idle_then_playing_without_identity_or_progress_never_verifies(workflow):
    cap, client, _, state = workflow
    await cap.handle(request())
    result = await cap.handle(request("Confirm video takeover", "confirm"))
    assert result.result["status"] == "uncertain" and not result.handled
    assert client.call_service.await_count == 1
    assert state["post_launch_reads"] == playback.VERIFY_ATTEMPTS
    assert "media_content_id" not in OBSERVED_HA["playing"]["attributes"]
    assert OBSERVED_HA["playing"]["attributes"]["media_position"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["playing", "prepared", "confirmation_required", "uncertain"])
async def test_cached_receipt_is_never_fresh_state_evidence(outcome, workflow):
    from app.capabilities.video import reply
    from app.video.intents import recognise
    import time
    cap, client, catalogue, _ = workflow
    original = request()
    # Synthetic historical operation result, not manufactured HA telemetry.
    historical = reply(outcome, "Historical result only", recognise(original.text))
    cap.requests[(context(original), original.request_id)] = time.monotonic() + 300, (original.text, original.area), historical
    result = await cap.handle(original)
    assert result.result["receipt"] == {"recorded_outcome": outcome, "fresh_verification": False}
    assert result.result["status"] == ("uncertain" if outcome == "uncertain" else "already_processed")
    assert not result.handled and not result.metadata["continue_conversation"]
    assert "playback was not checked again" in result.metadata["speech"]
    client.get_state.assert_not_awaited()
    client.call_service.assert_not_awaited()
    catalogue.lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_restart_discards_pending_confirmation_and_does_not_replay(workflow):
    cap, client, catalogue, _ = workflow
    await cap.handle(request())
    restarted = VideoCapability(catalogue, playback.VideoPlayback(client))
    result = await restarted.handle(request("Confirm video takeover", "confirm"))
    assert result.result["status"] == "confirmation_expired"
    client.call_service.assert_not_awaited()


@pytest.mark.parametrize("identifier", [None, 13, "0", "-1", "1?play&url=bad", "https://bad.invalid"])
def test_no_arbitrary_deep_links(identifier):
    with pytest.raises(ValueError):
        playback.deep_link(identifier, play=True)


def test_prepare_and_play_links_are_distinct():
    assert playback.deep_link("13", play=False) == "infuse://movie/13"
    assert playback.deep_link("13", play=True) == "infuse://movie/13?play"


@pytest.fixture
def cold_start(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setenv("VIDEO_ENABLED", "true")
    monkeypatch.setenv("VIDEO_TV_SOURCE", "HDMI 1")
    monkeypatch.setattr(playback, "WAKE_POLL_SECONDS", 0.001)
    monkeypatch.setattr(playback, "POLL_SECONDS", 0)
    movie = Movie("b" * 32, "Top Gun: Maverick", 2022, "361743")
    state = dict(sony="off", apple="off", source=None, watts="3", waking=None,
                 wake_reads=0, fail_wake=False, launched=False, position=0,
                 power_reported=datetime.now(timezone.utc).isoformat())
    commands = []

    async def get_state(entity):
        if entity == playback.WAKE_AUTOMATION:
            if state["waking"] and not state["fail_wake"]:
                state["wake_reads"] += 1
                if state["wake_reads"] == 3:
                    state["apple"] = "playing" if state.get("resume_media") else "idle"
                    if state["waking"] == playback.SONY_TV:
                        state.update(sony="on", source="HDMI 2")
            sony_wake = state["waking"] == playback.SONY_TV
            return {"state": "on", "attributes": {
                "current": int(sony_wake and 0 < state["wake_reads"] < 3),
                "last_triggered": "after" if sony_wake and state["wake_reads"] >= 3 else "before",
            }}
        if entity == playback.TV_POWER:
            return {"state": state["watts"], "attributes": {"unit_of_measurement": "W"},
                    "last_reported": state["power_reported"]}
        if entity == playback.SONY_TV:
            return {"entity_id": entity, "state": state["sony"],
                    "last_reported": datetime.now(timezone.utc).isoformat(),
                    "attributes": {"source": state["source"], "assumed_state": True,
                                   "source_list": ["HDMI 1", "HDMI 2"]}}
        assert entity == playback.APPLE_TV
        attributes = {}
        if state["launched"]:
            state["position"] += 1
            attributes = {"app_name": "Infuse", "media_content_id": "infuse://movie/361743?play",
                          "media_position": state["position"]}
        return {"entity_id": entity, "state": state["apple"], "attributes": attributes}

    async def call_service(domain, service, data):
        if domain == "homeassistant":
            assert (service, data) == ("update_entity", {"entity_id": playback.SONY_TV})
            commands.append((service, data))
            state["fail_wake"] = False
            return
        assert domain == "media_player"
        commands.append((service, data))
        if service == "turn_on":
            state["waking"] = data["entity_id"]
        elif service == "select_source":
            assert state["wake_reads"] >= 3
            state["source"] = data["source"]
        else:
            assert service == "play_media" and state["source"] == "HDMI 1"
            assert state["apple"] == "idle"
            state.update(apple="playing", launched=True)

    client = AsyncMock()
    client.get_state.side_effect = get_state
    client.call_service.side_effect = call_service
    catalogue = AsyncMock()
    catalogue.lookup.return_value = "resolved", movie, []
    return VideoCapability(catalogue, playback.VideoPlayback(client)), state, commands, catalogue


@pytest.mark.asyncio
@pytest.mark.parametrize("sony,apple,expected_wake", [
    ("off", "off", playback.SONY_TV), ("off", "idle", playback.SONY_TV),
    ("on", "off", playback.APPLE_TV), ("on", "idle", None),
])
async def test_cold_and_idle_play_select_correct_film(cold_start, sony, apple, expected_wake):
    cap, state, commands, catalogue = cold_start
    state.update(sony=sony, apple=apple, source="HDMI 1" if sony == "on" else None)
    result = await cap.handle(request("Play Top Gun Maverick on the living room TV"))
    assert result.result["status"] == "playing" and not cap.uncertain and not cap.pending
    catalogue.lookup.assert_awaited_once_with("Top Gun Maverick", None)
    expected = [("turn_on", {"entity_id": expected_wake})] if expected_wake else []
    if sony == "off":
        expected.append(("select_source", {"entity_id": playback.SONY_TV, "source": "HDMI 1"}))
    expected.append(("play_media", {"entity_id": playback.APPLE_TV, "media_content_type": "url",
                                   "media_content_id": "infuse://movie/361743?play"}))
    assert commands == expected


@pytest.mark.asyncio
async def test_off_prepare_never_wakes_devices(cold_start):
    cap, _, commands, _ = cold_start
    result = await cap.handle(request("Get Top Gun Maverick ready on the TV"))
    assert result.result["status"] == "unavailable" and not commands and not cap.uncertain


@pytest.mark.asyncio
@pytest.mark.parametrize("watts,reported", [("45", None), ("unknown", None), ("3", "2020-01-01T00:00:00+00:00")])
async def test_assumed_off_needs_fresh_standby_evidence(cold_start, watts, reported):
    cap, state, commands, _ = cold_start
    state["watts"] = watts
    if reported:
        state["power_reported"] = reported
    result = await cap.handle(request("Play Top Gun Maverick on the TV"))
    assert result.result["status"] == "unavailable" and not commands and not cap.uncertain


@pytest.mark.asyncio
async def test_failed_wake_latches_and_never_retries(cold_start, monkeypatch):
    from app.capabilities import video

    cap, state, commands, _ = cold_start
    state["fail_wake"] = True
    monkeypatch.setattr(video, "PLAY_DEADLINE_SECONDS", 0.05)
    monkeypatch.setattr(video, "PLAYBACK_RESERVE_SECONDS", 0.01)
    text = "Play Top Gun Maverick on the TV"
    assert (await cap.handle(request(text))).result["status"] == "uncertain"
    assert cap.uncertain
    assert (await cap.handle(request(text))).result["status"] == "uncertain"
    assert (await cap.handle(request(text, "new"))).result["status"] == "uncertain"
    assert commands == [("turn_on", {"entity_id": playback.SONY_TV})]


@pytest.mark.asyncio
async def test_unavailable_device_blocks_all_commands(cold_start):
    cap, state, commands, _ = cold_start
    state["apple"] = "unavailable"
    assert (await cap.handle(request("Play Top Gun Maverick on the TV"))).result["status"] == "unavailable"
    assert not commands


@pytest.mark.asyncio
async def test_slow_sony_refreshes_status_without_resending_power(cold_start, monkeypatch):
    cap, state, commands, _ = cold_start
    state["fail_wake"] = True
    monkeypatch.setattr(playback, "WAKE_REFRESH_DELAY_SECONDS", 0)
    result = await cap.handle(request("Play Top Gun Maverick on the TV"))
    assert result.result["status"] == "playing"
    assert [name for name, _ in commands] == ["turn_on", "update_entity", "select_source", "play_media"]


@pytest.mark.asyncio
async def test_playback_resuming_during_wake_blocks_new_film(cold_start):
    cap, state, commands, _ = cold_start
    state["resume_media"] = True
    result = await cap.handle(request("Play Top Gun Maverick on the TV"))
    assert result.result["status"] == "uncertain" and cap.uncertain
    assert commands == [("turn_on", {"entity_id": playback.SONY_TV})]
