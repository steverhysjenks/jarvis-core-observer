"""Synthetic fixtures only, under the mandatory network/process audit hook."""
from unittest.mock import AsyncMock
import pytest
from app.video.intents import recognise
from app.capabilities.video import video_capability
from app.voice.requests import VoiceRequest


@pytest.mark.parametrize("text,operation,title,year,room", [
    ("Play Forrest Gump on the living room TV.", "play", "Forrest Gump", None, "living room"),
    ("Ask Jarvis to play KPop Demon Hunters.", "play", "KPop Demon Hunters", None, None),
    ("Get Forrest Gump ready on the TV.", "prepare", "Forrest Gump", None, "living room"),
    ("Play the film Dune (2021) on the bedroom TV", "play", "Dune", 2021, "bedroom"),
    ("Play the movie Dune 1984 on the TV", "play", "Dune", 1984, "living room"),
    ("Play the movie On the Waterfront.", "play", "On the Waterfront", None, None),
    ("Play the movie The Girl on the Train.", "play", "The Girl on the Train", None, None),
    ("Play the movie On the Waterfront on the living room TV.", "play", "On the Waterfront", None, "living room"),
    ("Play the movie The Girl on the Train (2016) on the TV.", "play", "The Girl on the Train", 2016, "living room"),
    ("Play Captain America on the TV.", "play", "Captain America", None, "living room"),
    ("Play Shawshank Redemption.", "play", "Shawshank Redemption", None, None),
])
def test_recognition(text, operation, title, year, room):
    intent = recognise(text)
    assert (intent.operation, intent.title, intent.year, intent.room) == (operation, title, year, room)


@pytest.mark.parametrize("text", ["Play jazz", "Ask Jarvis to play Taylor Swift", "Pause music",
    "Play jazz on Spotify", "Play music on the living room speaker",
    "Play music on the TV", "Play the song On the Radio on the living room TV",
    "Get dinner ready", "Get jazz ready",
    "What is two plus two?", "Find my pasta recipe", "How many calories have I had today?"])
def test_unclaimed(text):
    assert recognise(text) is None


@pytest.mark.asyncio
async def test_disabled_claim_skips_music_and_semantic(monkeypatch):
    from app.capabilities import dispatcher
    from app.voice.orchestrator import handle_voice_request
    music = AsyncMock(side_effect=AssertionError("video fell through to music"))
    monkeypatch.setattr(dispatcher.music_capability, "handle", music)
    result = await handle_voice_request(VoiceRequest(text="Play Forrest Gump on the TV"))
    assert result["domain"] == "video" and result["operation_status"] == "disabled"
    assert not result["handled"] and result["path"] != "semantic"
    music.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Play the movie On the Waterfront.", "Play the movie The Girl on the Train.",
    "Play Captain America on the TV.", "Play Shawshank Redemption.", "Confirm video takeover", "Cancel video takeover"])
async def test_disabled_ownership_cannot_reach_dependencies(text, monkeypatch):
    from app.voice.orchestrator import handle_voice_request
    from app.adapters.homeassistant import ha_client
    from app.adapters.jellyfin import jellyfin_client
    from app.capabilities.music import music_capability
    forbidden = AsyncMock(side_effect=AssertionError("disabled video dependency access"))
    monkeypatch.delenv("VIDEO_ENABLED", raising=False)
    monkeypatch.setattr(ha_client, "get_state", forbidden)
    monkeypatch.setattr(ha_client, "call_service", forbidden)
    monkeypatch.setattr(jellyfin_client, "lookup", forbidden)
    monkeypatch.setattr(music_capability, "handle", forbidden)
    result = await handle_voice_request(VoiceRequest(text=text))
    assert result["domain"] == "video" and result["operation_status"] == "disabled"
    forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticated_request_envelope_and_no_lifespan(monkeypatch):
    import httpx
    from app.main import app
    from app.observer.runner import get_observer_status
    from app.adapters.homeassistant import ha_client
    from app.adapters.jellyfin import jellyfin_client
    service = AsyncMock(side_effect=AssertionError("real HA action attempted"))
    lookup = AsyncMock(side_effect=AssertionError("disabled catalogue accessed"))
    monkeypatch.setattr(ha_client, "call_service", service)
    monkeypatch.setattr(jellyfin_client, "lookup", lookup)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
        unauthorised = await client.post("/request", json={"text": "Play Forrest Gump on the TV"})
        assert unauthorised.status_code == 401
        response = await client.post("/request", headers={"Authorization": "Bearer isolated-test-placeholder"},
                                     json={"text": "Play Forrest Gump on the TV", "request_id": "fixture-api"})
    assert response.status_code == 200
    value = response.json()
    assert value["domain"] == "video" and value["operation_status"] == "disabled"
    assert value["handled"] is False and isinstance(value["speech"], str)
    assert value["continue_conversation"] is False and value["path"] != "semantic"
    assert not get_observer_status()["running"]
    service.assert_not_awaited()
    lookup.assert_not_awaited()
