"""Actual HA-agent method, pinned Router renderer and Core ASGI; no sockets/lifespan."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest

from app.adapters.jellyfin import Movie
from app.capabilities import dispatcher
from app.capabilities.models import CapabilityResult
from app.capabilities.video import VideoCapability
from app.main import app
from app.nutrition import dialogue, service
from app.video import playback
from app.voice.requests import VoiceRequest

ROOT = Path(__file__).resolve().parents[2]
OBSERVED = json.loads((ROOT / "tests/fixtures/ha-infuse-20261101.json").read_text())
CANONICAL_ID = "01J000000000000000000000000"


def router_contract():
    path = ROOT / "tests/fixtures/router-capability-bc2fe946.py.txt"
    source = path.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(source).hexdigest() == "4a89ba99a54e3910c010235cf8ec5c5eb8c55fec145e49721e75f0806e5d6c1b"
    namespace = {}
    exec(compile(source, str(path), "exec"), namespace)
    return namespace["capability_response"]


def agent_method(session):
    # Same isolated HA interface technique as existing nutrition forwarding tests.
    # Execute the committed integration method, not a duplicate implementation.
    source = ROOT / "integrations/homeassistant/jarvis_router/conversation.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_async_handle_message")
    class IntentResponse:
        def __init__(self, **kwargs):
            self.response_type = "action_done"
        def async_set_speech(self, value):
            self.speech = value
        def async_set_error(self, code, value):
            self.response_type, self.speech = "error", value
    namespace = {"ConversationInput": object, "ChatLog": object, "ConversationResult": object,
                 "dr": None, "ar": None, "_LOGGER": NS(debug=lambda *a: None), "uuid": uuid,
                 "async_get_clientsession": lambda _: session, "aiohttp": NS(ClientTimeout=lambda **kw: kw),
                 "AssistantContent": lambda **kw: kw, "conversation": NS(ConversationResult=lambda **kw: NS(**kw)),
                 "intent": NS(IntentResponse=IntentResponse, IntentResponseType=NS(QUERY_ANSWER="query_answer"),
                              IntentResponseErrorCode=NS(FAILED_TO_HANDLE="failed"))}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["_async_handle_message"]


class RouterTransport:
    """Mock HTTP hop; forwarding keys mirror accepted Router do_POST lines 187–223."""
    def __init__(self):
        self.requests, self.responses, self.semantic = [], [], []
        self.render = router_contract()

    def post(self, url, *, json, headers, timeout):
        assert url == "http://router.invalid/route"
        assert headers["Authorization"] == "Bearer isolated-router-key"
        assert timeout == {"total": 90}
        self.requests.append(json)
        transport = self
        class Response:
            status = 200
            async def __aenter__(self):
                # The real Core authentication, schema, dispatcher and capability execute.
                fields = {key: json[key] for key in ("conversation_id", "user_context", "request_id", "origin")
                          if json.get(key) is not None}
                fields.update(text=json["text"], area=json.get("origin_area"), satellite=json.get("origin_satellite"))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
                    response = await client.post("/request", json=fields,
                                                 headers={"Authorization": "Bearer isolated-test-placeholder"})
                assert response.status_code == 200
                self.value = transport.render(response.json(), json)
                if self.value is None:
                    transport.semantic.append(json["text"])
                    self.value = {"speech": "Isolated semantic answer", "continue_conversation": False}
                transport.responses.append(self.value)
                return self
            async def __aexit__(self, *args):
                pass
            async def json(self):
                return self.value
        return Response()


@pytest.fixture
def chain(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEO_ENABLED", "true")
    monkeypatch.setenv("VIDEO_TV_SOURCE", "HDMI 1")
    monkeypatch.setenv("NUTRITION_ENABLED", "true")
    monkeypatch.setattr(service, "STATE_PATH", tmp_path / "nutrition.sqlite")
    monkeypatch.setattr(playback, "POLL_SECONDS", 0)
    calls = {"launched": False, "reads_after_launch": 0}
    async def get_state(entity):
        if entity == playback.SONY_TV:
            return deepcopy(OBSERVED["sony"])
        assert entity == playback.APPLE_TV
        if calls["launched"]:
            calls["reads_after_launch"] += 1
        return deepcopy(OBSERVED["playing"] if calls["reads_after_launch"] > 1 else OBSERVED["idle"])
    async def launch(domain, action, data):
        assert (domain, action, data) == ("media_player", "play_media", {
            "entity_id": playback.APPLE_TV, "media_content_type": "url", "media_content_id": "infuse://movie/13?play"})
        calls["launched"] = True
    ha = AsyncMock()
    ha.get_state.side_effect, ha.call_service.side_effect = get_state, launch
    catalogue = AsyncMock()
    catalogue.lookup.return_value = "resolved", Movie("a" * 32, "Forrest Gump", 1994, "13"), []
    cap = VideoCapability(catalogue, playback.VideoPlayback(ha))
    monkeypatch.setattr(dispatcher.video_capability, "handle", cap.handle)
    forbidden = AsyncMock(side_effect=AssertionError("Video fell through to music or a nutrition write"))
    monkeypatch.setattr(dispatcher.music_capability, "handle", forbidden)
    monkeypatch.setattr(service.sparky, "call", forbidden)
    transport = RouterTransport()
    method = agent_method(transport)
    agent = NS(hass=None, _url="http://router.invalid", _api_key="isolated-router-key")
    def user(text, incoming=None):
        return NS(text=text, device_id=None, conversation_id=incoming, context=NS(user_id="fixture-user"),
                  agent_id="conversation.jarvis_router", language="en", satellite_id="fixture-satellite")
    def chat(identity=CANONICAL_ID):
        return NS(conversation_id=identity, async_add_assistant_content_without_tools=lambda _: None)
    # A genuine isolated nutrition draft coexists with the video pending operation.
    nutrition_context = service.context_key(VoiceRequest(text="fixture", conversation_id=CANONICAL_ID,
                                                        user_context="fixture-user", satellite="fixture-satellite"))
    dialogue.store(nutrition_context, {"query": ""})
    return NS(cap=cap, ha=ha, catalogue=catalogue, transport=transport, method=method, agent=agent,
              user=user, chat=chat, nutrition_context=nutrition_context, forbidden=forbidden)


@pytest.mark.asyncio
@pytest.mark.parametrize("followup,expected", [("Confirm video takeover", "uncertain"), ("Cancel video takeover", "cancelled")])
async def test_two_turn_canonical_session_routes_to_same_video_operation(followup, expected, chain):
    c = chain
    incoming = c.user("Play Forrest Gump on the living room TV")
    assert incoming.conversation_id is None
    first = await c.method(c.agent, incoming, c.chat())
    assert first.conversation_id == CANONICAL_ID and first.continue_conversation
    assert c.transport.responses[-1]["domain"] == "video"
    assert c.transport.responses[-1]["operation_status"] == "confirmation_required"
    assert "Forrest Gump (1994)" in first.response.speech
    assert len(c.cap.pending) == 1
    second = await c.method(c.agent, c.user(followup, first.conversation_id), c.chat())
    assert second.conversation_id == CANONICAL_ID and not second.continue_conversation
    assert c.transport.responses[-1]["domain"] == "video"
    assert c.transport.responses[-1]["operation_status"] == expected
    assert not c.cap.pending and not c.transport.semantic
    assert [r["conversation_id"] for r in c.transport.requests] == [CANONICAL_ID, CANONICAL_ID]
    assert c.transport.requests[0]["request_id"] != c.transport.requests[1]["request_id"]
    assert c.ha.call_service.await_count == (1 if followup.startswith("Confirm") else 0)
    assert dialogue.load(c.nutrition_context) == {"query": ""}
    assert dialogue.is_followup(VoiceRequest(text="milk", conversation_id=CANONICAL_ID,
                                           user_context="fixture-user", satellite="fixture-satellite"))
    c.forbidden.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Get Forrest Gump ready on the TV", "Ask Jarvis to play the movie KPop Demon Hunters",
    "Play the movie On the Waterfront", "Play the movie The Girl on the Train", "Play Captain America on the TV",
    "Play Moana", "Play Top Gun", "Play Top Gun: Maverick", "Play Moana 2"])
async def test_explicit_video_bypasses_only_generic_nutrition_followup(text, chain):
    c = chain
    await c.method(c.agent, c.user(text), c.chat())
    assert c.transport.responses[-1]["domain"] == "video" and not c.transport.semantic
    assert dialogue.load(c.nutrition_context) == {"query": ""}
    c.forbidden.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["not_found", "ambiguous"])
async def test_unresolved_video_is_terminal_through_router(status, chain):
    c = chain
    c.catalogue.lookup.return_value = status, None, []
    result = await c.method(c.agent, c.user("Play the movie On the Waterfront"), c.chat())
    assert result.conversation_id == CANONICAL_ID
    assert c.transport.responses[-1]["domain"] == "video"
    assert c.transport.responses[-1]["operation_status"] == status and not c.transport.semantic
    c.ha.get_state.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_chat_cannot_confirm_original_operation(chain):
    c = chain
    await c.method(c.agent, c.user("Play Forrest Gump on the TV"), c.chat())
    await c.method(c.agent, c.user("Confirm video takeover", "other-chat"), c.chat("other-chat"))
    assert c.transport.responses[-1]["operation_status"] == "confirmation_expired"
    assert len(c.cap.pending) == 1
    c.ha.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_transport_error_still_returns_canonical_chat_id(chain):
    c = chain
    class FailingSession:
        def post(self, *args, **kwargs):
            raise RuntimeError("isolated transport failure")
    method = agent_method(FailingSession())
    result = await method(c.agent, c.user("Play Forrest Gump on the TV"), c.chat())
    assert result.conversation_id == CANONICAL_ID and not result.continue_conversation
    assert result.response.response_type == "error"
    c.ha.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_music_and_unclaimed_conversation_keep_existing_router_paths(chain, monkeypatch):
    c = chain
    async def music(request):
        if request.text == "Play jazz":
            return CapabilityResult(True, False, "music", "fixture", {})
        return CapabilityResult(False, False, None, "not_claimed")
    monkeypatch.setattr(dispatcher.music_capability, "handle", AsyncMock(side_effect=music))
    await c.method(c.agent, c.user("Play jazz"), c.chat())
    assert not c.transport.semantic
    assert "music request" in c.transport.responses[-1]["speech"]
    await c.method(c.agent, c.user("Who wrote Hamlet?"), c.chat())
    assert c.transport.semantic == ["Who wrote Hamlet?"]
    assert dialogue.load(c.nutrition_context) == {"query": ""}
    c.catalogue.lookup.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_nutrition_read_keeps_its_existing_owned_contract(chain, monkeypatch):
    c = chain
    async def native(name, arguments, **kwargs):
        assert not kwargs.get("write")
        if name == "sparky_get_goal_snapshot":
            return {"calories": 2000}
        assert name == "sparky_get_nutrition_summary"
        return [{"calories": 300, "protein": 12, "carbs": 30, "fat": 5}]
    monkeypatch.setattr(service.sparky, "call", native)
    await c.method(c.agent, c.user("How many calories have I had today?"), c.chat())
    assert c.transport.responses[-1]["domain"] == "nutrition"
    assert c.transport.responses[-1]["operation_status"] == "read" and not c.transport.semantic
    c.catalogue.lookup.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected", [("Play Top Gun","not_found"),("Play Moana","ambiguous"),
    ("Play Top Gun: Maverick","confirmation_required"),("Play Moana 2","confirmation_required")])
async def test_observed_bare_catalogue_outcomes_remain_video_owned(text,expected,chain):
    from app.adapters.jellyfin import resolve
    c=chain
    rows=json.loads((ROOT/"tests/fixtures/jellyfin-movies-20261106.json").read_text())["movies"]
    items=[{"Id":m["item_id"],"Name":m["title"],"ProductionYear":m["year"],"Type":"Movie",
            "ProviderIds":{"Tmdb":m["tmdb_id"]},"LocationType":"FileSystem","MediaSources":[{"Id":"offline-stub"}]} for m in rows]
    async def lookup(title,year=None):return resolve({"Items":items,"TotalRecordCount":len(items)},title,year)
    c.catalogue.lookup.side_effect=lookup
    await c.method(c.agent,c.user(text),c.chat())
    assert c.transport.responses[-1]["domain"]=="video"
    assert c.transport.responses[-1]["operation_status"]==expected and not c.transport.semantic
    assert dialogue.load(c.nutrition_context)=={"query":""}
    c.ha.call_service.assert_not_awaited()
    c.forbidden.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Play the song Moana","Play the album Moana 2","Ask Jarvis to play Taylor Swift"])
async def test_indexed_film_names_do_not_consume_explicit_or_unrelated_music(text,chain,monkeypatch):
    c=chain
    music=AsyncMock(return_value=CapabilityResult(True,False,"music","fixture",{}))
    monkeypatch.setattr(dispatcher.music_capability,"handle",music)
    await c.method(c.agent,c.user(text),c.chat())
    music.assert_awaited_once()
    assert dialogue.load(c.nutrition_context)=={"query":""}
    c.catalogue.lookup.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()
