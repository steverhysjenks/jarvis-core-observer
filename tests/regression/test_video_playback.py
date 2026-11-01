"""All HA calls are mocks; global audit hooks additionally prohibit network/process I/O."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.adapters.homeassistant import HomeAssistantError
from app.adapters.jellyfin import CatalogueUnavailable, Movie
from app.capabilities.video import VideoCapability, context
from app.video import playback
from app.voice.requests import VoiceRequest

MOVIE = Movie("a" * 32, "Forrest Gump", 1994, "13")


def request(text="Play Forrest Gump on the living room TV", identity="initial", **kwargs):
    values = dict(text=text, request_id=identity, origin="fixture-assist", user_context="fixture-user",
                  conversation_id="fixture-conversation")
    values.update(kwargs)
    return VoiceRequest(**values)


@pytest.fixture
def workflow(monkeypatch):
    monkeypatch.setenv("VIDEO_ENABLED", "true")
    monkeypatch.setattr(playback, "POLL_SECONDS", 0)
    state = {"launched": False, "position": 0, "apple_state": "idle", "source": "fixture-hdmi"}
    async def get_state(entity):
        assert entity in {playback.APPLE_TV, playback.SONY_TV}
        if entity == playback.SONY_TV:
            return {"entity_id": entity, "state": "on", "attributes": {"source": state["source"]}}
        attrs = {}
        current = state["apple_state"]
        if state["launched"]:
            current = "playing"
            state["position"] += 1
            attrs = {"app_name": "Infuse", "media_content_id": "infuse://movie/13?play",
                     "media_position": state["position"]}
        return {"entity_id": entity, "state": current, "attributes": attrs}
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
async def test_occupied_requires_explicit_confirmation_and_actual_verification(workflow):
    cap, client, catalogue, _ = workflow
    first = await cap.handle(request())
    assert first.result["status"] == "confirmation_required" and not first.handled
    client.call_service.assert_not_awaited()
    result = await cap.handle(request("Confirm video takeover", "confirm"))
    assert result.handled and result.result["status"] == "playing"
    assert client.call_service.await_count == 1
    assert not cap.uncertain


@pytest.mark.asyncio
async def test_duplicate_confirmation_concurrently_sends_exactly_one_command(workflow):
    cap, client, _, _ = workflow
    await cap.handle(request())
    confirm = request("Confirm video takeover", "confirm")
    a, b = await asyncio.gather(cap.handle(confirm), cap.handle(confirm))
    assert a.result["status"] == b.result["status"] == "playing"
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
    assert client.get_state.await_count == 6
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
@pytest.mark.parametrize("changes", [
    {"media_content_id": "infuse://movie/999?play"}, {"app_name": "Other app"},
    {"media_position": 0}, {"media_position": float("nan")}, {"media_content_id": None},
])
async def test_never_reports_playing_without_identity_and_progress(changes, workflow):
    cap, client, _, _ = workflow
    await cap.handle(request())
    original = client.get_state.side_effect
    async def changed(entity):
        state = await original(entity)
        if entity == playback.APPLE_TV:
            state["attributes"].update(changes)
        return state
    client.get_state.side_effect = changed
    # Changes also alter the confirmation snapshot: first re-establish its evidence.
    await cap.handle(request(identity="new-view"))
    result = await cap.handle(request("Confirm video takeover", "confirm"))
    assert result.result["status"] == "uncertain" and not result.handled
    assert client.call_service.await_count == 1


@pytest.mark.parametrize("identifier", [None, 13, "0", "-1", "1?play&url=bad", "https://bad.invalid"])
def test_no_arbitrary_deep_links(identifier):
    with pytest.raises(ValueError):
        playback.deep_link(identifier, play=True)


def test_prepare_and_play_links_are_distinct():
    assert playback.deep_link("13", play=False) == "infuse://movie/13"
    assert playback.deep_link("13", play=True) == "infuse://movie/13?play"
