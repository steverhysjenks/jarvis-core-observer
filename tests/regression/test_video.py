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
])
def test_recognition(text, operation, title, year, room):
    intent = recognise(text)
    assert (intent.operation, intent.title, intent.year, intent.room) == (operation, title, year, room)


@pytest.mark.parametrize("text", ["Play jazz", "Ask Jarvis to play Taylor Swift", "Pause music",
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
