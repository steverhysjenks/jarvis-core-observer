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


@pytest.mark.parametrize("text,title,explicit", [
    ("Play Babe", "Babe", False),
    ("Play Babe on TV", "Babe", True),
    ("Put on Babe", "Babe", False),
    ("Put on The Goonies on the TV", "The Goonies", True),
    ("Play the movie Descendants", "Descendants", True),
    ("Put the film Babe on", "Babe", True),
    ("Could you put on Descendants on TV?", "Descendants", True),
    ("Play Friday the 13th on TV", "Friday the 13th", True),
])
def test_campaign_play_phrases(text, title, explicit):
    intent = recognise(text, allow_unknown=True)
    assert (intent.title, intent.explicit, intent.operation) == (title, explicit, "play")


@pytest.mark.parametrize("text", ["Put Babe on the TV", "Hit the Goonies on TV", "Put on some music",
    "Play the Descendants soundtrack", "Play Babe on the office speaker", "Play the song Frozen"])
def test_malformed_speech_and_explicit_music_do_not_enter_video_ownership(text):
    assert recognise(text, allow_unknown=True) is None


@pytest.fixture
def coordination(monkeypatch):
    from app.adapters.jellyfin import Movie
    from app.capabilities import dispatcher, media
    from app.music.models import ResolvedMusicCandidate

    film = Movie("a" * 32, "Frozen", 2013, "109445")
    song = ResolvedMusicCandidate("m1", "library://track/1", "track", "Frozen")
    lookup = AsyncMock(return_value=("resolved", film, []))
    search = AsyncMock(return_value=(None, song))
    music = AsyncMock(return_value={"name": "Frozen", "target_name": "Office Echo"})
    video = AsyncMock(return_value=media.response("test_video", "Video executed"))
    coordinator = media.MediaCoordinator()
    monkeypatch.setenv("VIDEO_ENABLED", "true")
    monkeypatch.setattr(dispatcher, "media_coordinator", coordinator)
    monkeypatch.setattr(media.video_capability.catalogue, "lookup", lookup)
    monkeypatch.setattr(media.video_capability, "handle", video)
    monkeypatch.setattr(media.music, "probe_exact", search)
    monkeypatch.setattr(media.music, "play_candidate", music)
    return coordinator, film, song, lookup, search, music, video


def media_request(text, request_id, **changes):
    fields = dict(conversation_id="one", origin="home_assistant", user_context="user-one",
                  area="Office area", satellite=None)
    fields.update(changes)
    return VoiceRequest(text=text, request_id=request_id, **fields)


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,expected", [("The film", "test_video"), ("The movie", "test_video"),
    ("The music", "music"), ("The song", "music"), ("Cancel", "cancelled")])
async def test_media_choice_consumes_only_one_capability(coordination, answer, expected):
    from app.capabilities.dispatcher import dispatch_capabilities

    _, film, _, _, _, music, video = coordination
    first = await dispatch_capabilities(media_request("Play Frozen", "original"))
    assert first.metadata["operation_status"] == "clarification_required"
    assert first.metadata["continue_conversation"] is True
    music.assert_not_awaited()
    video.assert_not_awaited()
    reply = media_request(answer, "answer")
    result = await dispatch_capabilities(reply)
    assert result.metadata.get("operation_status", result.domain) == expected
    duplicate = await dispatch_capabilities(reply)
    assert duplicate.metadata["operation_status"] == "already_processed"
    assert video.await_count == int(expected == "test_video")
    assert music.await_count == int(expected == "music")
    if expected == "music":
        assert music.await_args.args[-1] == "office"
    if expected == "test_video":
        assert video.await_args.kwargs["expected_movie"] == film


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"user_context": "other"}, {"conversation_id": "other"},
    {"satellite": "assist_satellite.kitchen"}, {"user_context": None}, {"origin": "different"}])
async def test_short_choice_cannot_cross_context(coordination, changes):
    from app.capabilities.dispatcher import dispatch_capabilities

    *_, music, video = coordination
    await dispatch_capabilities(media_request("Play Frozen", "original"))
    denied = await dispatch_capabilities(media_request("The film", "other", **changes))
    assert denied.metadata["operation_status"] == "choice_required"
    video.assert_not_awaited()
    music.assert_not_awaited()
    await dispatch_capabilities(media_request("The film", "allowed"))
    video.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("user_context", [None, "device-account"])
async def test_shared_satellite_requires_fresh_explicit_command(coordination, user_context):
    from app.capabilities.dispatcher import dispatch_capabilities

    *_, music, video = coordination
    context = {"user_context": user_context, "satellite": "assist_satellite.office"}
    result = await dispatch_capabilities(media_request("Play Frozen", "bare", **context))
    assert result.metadata["operation_status"] == "choice_required"
    assert not result.metadata["continue_conversation"]
    result = await dispatch_capabilities(media_request("The film", "answer", **context))
    assert result.metadata["operation_status"] == "choice_required"
    video.assert_not_awaited()
    music.assert_not_awaited()
    await dispatch_capabilities(media_request("Play the movie Frozen", "explicit", **context))
    video.assert_awaited_once()
    music.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_unrelated_turn_and_fresh_explicit_command(coordination, monkeypatch):
    from app.capabilities import dispatcher, media

    _, _, _, _, _, play_music, video = coordination
    ticks = [0]
    monkeypatch.setattr(media, "time", type("Clock", (), {"monotonic": staticmethod(lambda: ticks[0])}))
    monkeypatch.setattr(dispatcher.music_capability, "handle",
                        AsyncMock(return_value=media.CapabilityResult(False, False, None, "not_claimed")))
    await dispatcher.dispatch_capabilities(media_request("Play Frozen", "original"))
    assert await dispatcher.dispatch_capabilities(media_request("What time is it?", "unrelated")) is None
    video.assert_not_awaited()
    play_music.assert_not_awaited()
    ticks[0] = 61
    result = await dispatcher.dispatch_capabilities(media_request("The film", "expired"))
    assert result.metadata["operation_status"] == "choice_required"
    video.assert_not_awaited()
    await dispatcher.dispatch_capabilities(media_request("Play Frozen", "another"))
    await dispatcher.dispatch_capabilities(media_request("Play the movie Frozen", "explicit"))
    result = await dispatcher.dispatch_capabilities(media_request("The film", "old-answer"))
    assert result.metadata["operation_status"] == "choice_required"
    video.assert_awaited_once()
    play_music.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["film_only", "music_only", "neither", "editions", "film_down", "music_down"])
async def test_generic_media_uses_both_catalogues(coordination, case, monkeypatch):
    from app.adapters.jellyfin import CatalogueUnavailable
    from app.capabilities import dispatcher, media

    _, _, _, lookup, search, music, video = coordination
    if case in {"music_only", "neither"}:
        lookup.return_value = ("not_found", None, [])
    if case in {"film_only", "neither"}:
        search.return_value = (None, None)
    if case == "editions":
        lookup.return_value = ("ambiguous", None, [{"year": 2013}, {"year": 2019}])
    if case == "film_down":
        lookup.side_effect = CatalogueUnavailable
    if case == "music_down":
        search.side_effect = ValueError
    fallback = AsyncMock(return_value=media.CapabilityResult(False, False, None, "not_claimed"))
    monkeypatch.setattr(dispatcher.music_capability, "handle", fallback)
    request = media_request("Play Frozen", "original")
    result = await dispatcher.dispatch_capabilities(request)
    assert video.await_count == int(case == "film_only")
    assert music.await_count == int(case == "music_only")
    if case == "neither":
        assert result is None
        fallback.assert_awaited_once_with(request, catalogue_checked=True)
    elif case in {"film_down", "music_down", "editions"}:
        assert result.metadata["operation_status"] == (
            "clarification_required" if case == "editions" else "unavailable")
        fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_music_choice_is_not_played(coordination):
    from dataclasses import replace
    from app.capabilities.dispatcher import dispatch_capabilities

    _, _, song, _, search, music, video = coordination
    await dispatch_capabilities(media_request("Play Frozen", "original"))
    search.return_value = (None, replace(song, uri="library://track/other"))
    result = await dispatch_capabilities(media_request("The music", "changed"))
    assert result.metadata["operation_status"] == "candidate_changed"
    music.assert_not_awaited()
    video.assert_not_awaited()


@pytest.mark.asyncio
async def test_clarified_video_handoff_is_bound_and_single_use(coordination):
    from app.capabilities import dispatcher, media, video as video_module

    _, film, _, _, _, music, video = coordination
    intent = recognise("Play Frozen", allow_unknown=True)
    video.side_effect = [
        video_module.reply("video_deadline_required", "Wake budget.", intent, request_id="answer"),
        media.response("test_video", "Video executed"),
    ]
    await dispatcher.dispatch_capabilities(media_request("Play Frozen", "original"))
    reply = media_request("The film", "answer")
    reply._video_deadline = "negotiate-v1"
    offer = await dispatcher.dispatch_capabilities(reply)
    assert offer.domain == "video" and offer.result["request_id"] == "answer"
    reply._video_deadline = "extended-v1"
    assert (await dispatcher.dispatch_capabilities(reply)).metadata["operation_status"] == "test_video"
    assert (await dispatcher.dispatch_capabilities(reply)).metadata["operation_status"] == "already_processed"
    assert video.await_count == 2
    assert video.await_args.kwargs["expected_movie"] == film
    music.assert_not_awaited()
