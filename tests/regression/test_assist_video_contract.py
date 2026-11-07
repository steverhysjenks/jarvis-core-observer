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


def agent_method(session, native_handler=None, origin_area=None):
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
                 "dr": NS(async_get=lambda _: NS(async_get=lambda _: NS(area_id="fixture-area"))),
                 "ar": NS(async_get=lambda _: NS(async_get_area=lambda _: NS(name=origin_area))), "_LOGGER": NS(debug=lambda *a: None), "uuid": uuid,
                 "async_get_clientsession": lambda _: session, "aiohttp": NS(ClientTimeout=lambda **kw: kw),
                 "AssistantContent": lambda **kw: kw, "conversation": NS(ConversationResult=lambda **kw: NS(**kw), HOME_ASSISTANT_AGENT="home_assistant",
                    async_handle_intents=native_handler or AsyncMock(return_value=None)),
                 "intent": NS(INTENT_GET_STATE="HassGetState", IntentResponse=IntentResponse, IntentResponseType=NS(QUERY_ANSWER="query_answer"),
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
        if entity == playback.WAKE_AUTOMATION:
            return {"state": "on", "attributes": {"current": 0}}
        if entity == playback.SONY_TV:
            return deepcopy(OBSERVED["sony"])
        assert entity == playback.APPLE_TV
        if calls["launched"]:
            calls["reads_after_launch"] += 1
        return deepcopy(OBSERVED["playing"])
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
                  agent_id="conversation.jarvis_router", language="en", satellite_id="fixture-satellite", extra_system_prompt=None)
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
@pytest.mark.parametrize("text,expected", [("Could you play Moana?","ambiguous"),("Can you play Top Gun: Maverick (2022)?","confirmation_required"),("Play Top Gun","not_found"),("Play Moana","ambiguous"),
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


def ha_ownership_stage(c, native_intent=None, *, features=None, native_error=False, origin_area=None):
    """Execute pinned installed HA dispatch + actual agent/Router/Core.

    Sentence recognition and native services are interface mocks, not a live HA
    framework. Native media matching mirrors the retained TV-alias traces.
    """
    fixture = ROOT / "tests/fixtures/ha-local-first-2026.10.4.py.txt"
    raw = fixture.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == "764256e391ef0680ef18f24871d252a35c110ad2cd9affff8a84162ede4a43cb"
    class RecognizeResult:
        def __init__(self, name):
            self.intent = NS(name=name)
    response = NS(speech={"plain": {"speech": "Native answer"}},
                  response_type="error" if native_error else "action_done", error_code="failed")
    native = NS(async_recognize_intent=AsyncMock(return_value=RecognizeResult(native_intent) if native_intent else None),
                _async_process_intent_result=AsyncMock(return_value=response))
    conversation = NS(HOME_ASSISTANT_AGENT="home_assistant", ConversationEntityFeature=NS(CONTROL=1),
                      ConversationResult=lambda **kw: NS(**kw), AssistantContent=lambda **kw: kw,
                      async_handle_sentence_triggers=AsyncMock(return_value=None))
    namespace = {"Callable": object, "RecognizeResult": RecognizeResult, "ConversationInput": object,
                 "ChatLog": object, "conversation": conversation,
                 "media_player": NS(INTENT_MEDIA_SEARCH_AND_PLAY="HassMediaSearchAndPlay"),
                 "EntityStateAttribute": NS(SUPPORTED_FEATURES="supported_features"),
                 "intent": NS(INTENT_GET_STATE="HassGetState", IntentResponse=object,
                              IntentResponseType=NS(ERROR="error"),
                              IntentResponseErrorCode=NS(FAILED_TO_HANDLE="failed", UNKNOWN="unknown"))}
    # Avoid evaluating HA type annotations without importing the HA framework.
    exec(compile("from __future__ import annotations\n" + raw.decode(), str(fixture), "exec"), namespace)
    async def handle(hass, user, chat, *, intent_filter=None):
        return await namespace["async_handle_intents"](native, user, chat, intent_filter=intent_filter)
    conversation.async_handle_intents = handle
    method = agent_method(c.transport, handle, origin_area)
    async def converse(**kwargs):
        return await method(c.agent, user, chat)
    conversation.async_converse = converse
    tree = ast.parse((ROOT / "integrations/homeassistant/jarvis_router/conversation.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    assignment = next(n for n in cls.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "_attr_supported_features" for t in n.targets))
    advertised = eval(compile(ast.Expression(assignment.value), "agent features", "eval"),
                      {"ConversationEntityFeature": conversation.ConversationEntityFeature})
    assert advertised == 1
    host = NS(hass=NS(states=NS(get=lambda _: NS(attributes={"supported_features": advertised if features is None else features}))),
              pipeline=NS(prefer_local_intents=True, conversation_language="en"))
    runner = NS(intent_agent=NS(id="conversation.jarvis_router"), host=host, _intent_agent_only=False)
    user, chat = None, None
    async def run(text):
        nonlocal user, chat
        user, chat = c.user(text), c.chat()
        if origin_area:
            user.device_id = "fixture-device"
        return await namespace["run_intent_stage"](runner, user, chat, NS(conversation_id=CANONICAL_ID))
    return NS(run=run, native=native, response=response)


@pytest.mark.asyncio
@pytest.mark.parametrize("text,native_intent", [
    ("Play Top Gun Maverick on the TV", "HassMediaSearchAndPlay"),
    ("Can you play Barbie on the TV?", "HassMediaSearchAndPlay"),
    ("Could you play Moana?", None), ("Play Moana", None),
    ("Could you play Top Gun: Maverick (2022) on the TV?", "HassMediaSearchAndPlay"),
])
async def test_assist_media_interception_is_excluded_through_disabled_core(text, native_intent, chain, monkeypatch):
    c = chain
    monkeypatch.setenv("VIDEO_ENABLED", "false")
    stage = ha_ownership_stage(c, native_intent)
    result, local = await stage.run(text)
    assert not local and result.conversation_id == CANONICAL_ID
    assert c.transport.requests[0]["text"] == text
    assert c.transport.responses[-1]["domain"] == "video"
    assert c.transport.responses[-1]["operation_status"] == "disabled"
    assert not c.transport.semantic
    stage.native._async_process_intent_result.assert_not_awaited()
    c.catalogue.lookup.assert_not_awaited()
    c.ha.get_state.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()
    c.forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_pinned_assist_reproduces_pre_control_interception(chain):
    c = chain
    stage = ha_ownership_stage(c, "HassMediaSearchAndPlay", features=0, native_error=True)
    result, local = await stage.run("Can you play Barbie on the TV?")
    assert local and result.response is stage.response and result.response.error_code == "failed"
    stage.native._async_process_intent_result.assert_awaited_once()
    assert not c.transport.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("text,name", [
    ("Turn on the office light", "HassTurnOn"),
    ("Pause the office speaker", "HassMediaPause"),
    ("Set the office speaker volume to 20 percent", "HassSetVolume"),
    ("Is the office light on?", "HassGetState"),
])
async def test_control_preserves_native_controls_and_state_queries(text, name, chain):
    c = chain
    stage = ha_ownership_stage(c, name)
    result, local = await stage.run(text)
    assert local is (name != "HassGetState")
    assert result.response is stage.response and result.conversation_id == CANONICAL_ID
    stage.native._async_process_intent_result.assert_awaited_once()
    assert not c.transport.requests
    c.catalogue.lookup.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_get_state_failure_is_not_retried_through_router(chain):
    c = chain
    stage = ha_ownership_stage(c, "HassGetState", native_error=True)
    result, local = await stage.run("Is the office light on?")
    assert not local and result.response.response_type == "error"
    assert not c.transport.requests
    stage.native._async_process_intent_result.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("text,query", [("Play Moa", "Moa"), ("play Stereophonics", "Stereophonics"),
                                       ("Play the song Moana on the office speaker", "Moana")])
async def test_assist_music_keeps_origin_area_and_music_assistant_path(text, query, chain, monkeypatch):
    from app.capabilities import music
    c = chain
    classifier = AsyncMock(return_value=NS(retrieval_type="explicit", query=query, intent="play"))
    play = AsyncMock(return_value={"handled": True, "name": query, "target_entity_id": "media_player.office"})
    monkeypatch.setattr(music, "classify_music_request", classifier)
    monkeypatch.setattr(music, "play_explicit", play)
    monkeypatch.setattr(dispatcher.music_capability, "handle", music.MusicCapability().handle)
    stage = ha_ownership_stage(c, "HassMediaSearchAndPlay", origin_area="Office")
    result, local = await stage.run(text)
    assert not local and result.conversation_id == CANONICAL_ID
    classifier.assert_awaited_once_with(text)
    play.assert_awaited_once_with(query, "office")
    assert c.transport.requests[0]["origin_area"] == "Office" and not c.transport.semantic
    stage.native._async_process_intent_result.assert_not_awaited()
    c.catalogue.lookup.assert_not_awaited()
    c.ha.call_service.assert_not_awaited()
