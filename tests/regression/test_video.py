"""Synthetic fixtures only, under the mandatory network/process audit hook."""
from unittest.mock import AsyncMock
import pytest
from app.video.intents import recognise
from app.capabilities.video import video_capability
from app.voice.requests import VoiceRequest
import json
from pathlib import Path
from app.video import title_index
from app.adapters.jellyfin import normalise

EVIDENCE = json.loads((Path(__file__).resolve().parents[1] / "fixtures/jellyfin-movies-20261106.json").read_text())


@pytest.mark.parametrize("text,title,year", [
    ("Play Top Gun", "Top Gun", None),
    ("Play Top Gun: Maverick", "Top Gun: Maverick", None),
    ("Play Top Gun: Maverick (2022)", "Top Gun: Maverick", 2022),
    ("Play Moana", "Moana", None), ("Play Moana 2", "Moana 2", None),
    ("Get Moana (2026) ready", "Moana", 2026),
])
def test_catalogue_derived_bare_title_ownership(text, title, year):
    intent = recognise(text)
    assert (intent.title, intent.year) == (title, year)
    assert intent.operation in {"play", "prepare"}


@pytest.mark.parametrize("title", ["Spider-Man: Across the Spider-Verse", "Dr. Strangelove", "Who's Afraid of Virginia Woolf?", "Hello, Dolly!"])
def test_title_punctuation_is_data(title):
    assert recognise("Play the movie " + title + " on the TV").operation == "play"


@pytest.mark.parametrize("title", ["https://bad.invalid/a", "file:secret", "infuse:13", "data:payload", "www.bad.invalid", "A; turn off lights", "A then play B", "A\\B", "A\nB"])
def test_unsafe_targets_remain_claimed_invalid(title):
    assert recognise("Play the movie " + title + " on the TV").operation == "invalid"


@pytest.mark.parametrize("text", ["Play the song Moana", "Play the album Moana 2", "Play artist Moana", "Play playlist Top Gun", "Play Moana soundtrack", "Play jazz", "Ask Jarvis to play Taylor Swift"])
def test_index_does_not_consume_unrelated_music(text):
    assert recognise(text) is None


def test_index_has_no_runtime_film_allowlist(monkeypatch):
    monkeypatch.setattr("app.video.intents.catalogue_titles", lambda: frozenset({normalise("A Synthetic Film: Part Two"), normalise("A Synthetic Film")}))
    assert recognise("Play A Synthetic Film: Part Two").title == "A Synthetic Film: Part Two"
    assert recognise("Play A Synthetic Film").title == "A Synthetic Film"
    assert recognise("Play Moana") is None
    assert recognise("Play Forrest Gump") is None


def test_index_failure_retains_only_same_scope_ownership(monkeypatch):
    import os
    path = Path(os.environ["VIDEO_TITLE_INDEX_FILE"])
    assert recognise("Play Moana") is not None
    path.write_text("corrupt")
    assert recognise("Play Moana") is not None
    monkeypatch.setenv("JELLYFIN_MOVIE_LIBRARY_ID", "d" * 32)
    assert recognise("Play Moana") is None
    assert recognise("Play jazz") is None


@pytest.mark.parametrize("change", [{"schema":2}, {"titles":[]}, {"titles":[None]}, {"titles":["a\nname"]}, {"user_id":"d"*32}, {"library_id":"d"*32}])
def test_invalid_index_rejected(change):
    value = {"schema":1,"user_id":"b"*32,"library_id":"c"*32,"titles":["Fixture Movie"],**change}
    with pytest.raises((ValueError, TypeError)):
        title_index.validate_index(value,"b"*32,"c"*32)


@pytest.mark.parametrize("text,operation,title,year,room", [
    ("Play Forrest Gump on the living room TV.", "play", "Forrest Gump", None, "living room"),
    ("Ask Jarvis to play the movie KPop Demon Hunters.", "play", "KPop Demon Hunters", None, None),
    ("Get Forrest Gump ready on the TV.", "prepare", "Forrest Gump", None, "living room"),
    ("Play the film Dune (2021) on the bedroom TV", "play", "Dune", 2021, "bedroom"),
    ("Play the movie Dune 1984 on the TV", "play", "Dune", 1984, "living room"),
    ("Play the movie On the Waterfront.", "play", "On the Waterfront", None, None),
    ("Play the movie The Girl on the Train.", "play", "The Girl on the Train", None, None),
    ("Play the movie On the Waterfront on the living room TV.", "play", "On the Waterfront", None, "living room"),
    ("Play the movie The Girl on the Train (2016) on the TV.", "play", "The Girl on the Train", 2016, "living room"),
    ("Play Captain America on the TV.", "play", "Captain America", None, "living room"),
    ("Play Moana.", "play", "Moana", None, None),
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
    "Play Captain America on the TV.", "Play Moana.", "Confirm video takeover", "Cancel video takeover"])
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


@pytest.mark.parametrize("text,title,year,room", [
    ("Can you play Barbie on the TV?", "Barbie", None, "living room"),
    ("Could you play Moana?", "Moana", None, None),
    ("Could you play Top Gun: Maverick (2022) on the living room TV?", "Top Gun: Maverick", 2022, "living room"),
    ("Can you play the film The Girl on the Train?", "The Girl on the Train", None, None),
])
def test_bounded_polite_prefix_preserves_title_and_destination(text,title,year,room):
    intent=recognise(text)
    assert (intent.title,intent.year,intent.room)==(title,year,room)


@pytest.mark.parametrize("text", ["Play Moa", "Could you play Moa?", "Can you play Stereophonics?",
    "Could you play the song Moana?", "Can you play the album Moana 2?",
    "Can you tell me about Moana?", "I wonder if you could play Moana"])
def test_polite_prefix_does_not_broaden_film_ownership(text):
    assert recognise(text) is None
