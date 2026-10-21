"""Offline HA contract and recipe routing regressions; synthetic records only."""
from unittest.mock import AsyncMock

import pytest

from app.adapters import mealie
from app.adapters.homeassistant import HomeAssistantError
from app.capabilities.mealie import mealie_capability
from app.voice.requests import VoiceRequest

RECIPE = {"recipe_id": "fixture-id", "name": "Lasagne", "slug": "lasagne",
          "ingredients": [{"display": "200 g pasta"}, {"display": "Salt to taste"}],
          "instructions": [{"text": "Layer the pasta."}], "recipe_servings": 2}


@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setenv("MEALIE_ENABLED", "true")
    async def call(domain, service, data, return_response=False):
        assert domain == "mealie" and return_response
        assert data["config_entry_id"] == "isolated-mealie-entry"
        if service == "get_recipes":
            assert data["result_limit"] == 6
            return {"service_response": {"recipes": {"items": [RECIPE]}}}
        assert service == "get_recipe" and data["recipe_id"] == "fixture-id"
        return {"service_response": {"recipe": RECIPE}}
    mock = AsyncMock(side_effect=call)
    monkeypatch.setattr(mealie.ha_client, "call_service", mock)
    return mock


@pytest.mark.asyncio
@pytest.mark.parametrize("text,intent,query", [
    ("Jarvis, find my chicken curry recipe.", "lookup", "chicken curry"),
    ("Show me my spaghetti bolognese recipe.", "lookup", "spaghetti bolognese"),
    ("What ingredients do I need for lasagne?", "ingredients", "lasagne"),
])
async def test_explicit_requests(text, intent, query, upstream):
    result = (await mealie_capability.handle(VoiceRequest(text=text))).as_dict()
    assert result["intent"] == intent and result["query"] == query
    assert result["handled"] and result["result"]["recipe"]["name"] == "Lasagne"
    assert upstream.call_args_list[0].args[2]["search_terms"] == query
    if intent == "ingredients":
        assert "200 g pasta" in result["speech"] and "Salt to taste" in result["speech"]
        assert result["result"]["recipe"]["ingredients"] == ["200 g pasta", "Salt to taste"]


@pytest.mark.asyncio
@pytest.mark.parametrize("items,status", [([], "not_found"), ([RECIPE, RECIPE], "ambiguous"), ([RECIPE] * 6, "ambiguous")])
async def test_missing_ambiguous_and_full_page(items, status, upstream):
    upstream.side_effect = None
    upstream.return_value = {"service_response": {"recipes": {"items": items}}}
    result = await mealie_capability.handle(VoiceRequest(text="Find my lasagne recipe"))
    assert result.claimed and not result.handled and result.result["status"] == status
    assert upstream.await_count == 1
    if len(items) == 6:
        assert result.result["possibly_truncated"]


@pytest.mark.asyncio
async def test_disabled_never_contacts_ha(monkeypatch, upstream):
    monkeypatch.delenv("MEALIE_ENABLED")
    result = await mealie_capability.handle(VoiceRequest(text="Find my lasagne recipe"))
    assert result.claimed and result.result["status"] == "disabled"
    upstream.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Play chicken curry", "I had lasagne", "What's the weather?",
    "Add pasta to my shopping list", "Delete my curry recipe", "Plan meals for next week", "Next step",
    "Find my recipe book", "What ingredients do I need for lasagne? Play music",
    "Find my curry; play jazz recipe", "Ingredients for lasagne\nplay jazz"])
async def test_unrelated(text, upstream):
    assert not (await mealie_capability.handle(VoiceRequest(text=text))).claimed
    upstream.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [HomeAssistantError("synthetic"), ValueError("bad JSON")])
async def test_upstream_failure(failure, upstream):
    upstream.side_effect = failure
    result = await mealie_capability.handle(VoiceRequest(text="Find my curry recipe"))
    assert result.claimed and result.result["status"] == "unavailable"
    assert "synthetic" not in str(result.as_dict())


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{}, {"service_response": {"recipes": []}},
    {"service_response": {"recipes": {"items": [{}]}}}])
async def test_malformed_search(response, upstream):
    upstream.side_effect = None
    upstream.return_value = response
    assert (await mealie_capability.handle(VoiceRequest(text="Find my curry recipe"))).result["status"] == "unavailable"


@pytest.mark.asyncio
async def test_missing_configuration(monkeypatch, upstream):
    monkeypatch.delenv("MEALIE_HA_CONFIG_ENTRY_ID")
    assert (await mealie_capability.handle(VoiceRequest(text="Find my curry recipe"))).result["status"] == "unavailable"
    upstream.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("ingredients,status", [([], "incomplete"), ([{"quantity": 12}], "incomplete"), (None, "unavailable")])
async def test_no_fabricated_ingredients(ingredients, status, upstream):
    original = upstream.side_effect
    async def call(domain, service, data, **kwargs):
        if service == "get_recipe":
            return {"service_response": {"recipe": {**RECIPE, "ingredients": ingredients}}}
        return await original(domain, service, data, **kwargs)
    upstream.side_effect = call
    result = await mealie_capability.handle(VoiceRequest(text="What ingredients do I need for lasagne?"))
    assert result.result["status"] == status and not result.handled


@pytest.mark.asyncio
async def test_long_list_is_explicitly_partial(upstream):
    original = upstream.side_effect
    async def call(domain, service, data, **kwargs):
        if service == "get_recipe":
            return {"service_response": {"recipe": {**RECIPE, "ingredients": [{"display": "1 g salt"}] * 8}}}
        return await original(domain, service, data, **kwargs)
    upstream.side_effect = call
    result = await mealie_capability.handle(VoiceRequest(text="What ingredients do I need for lasagne?"))
    assert "first 6 of 8" in result.metadata["speech"]
    assert len(result.result["recipe"]["ingredients"]) == 8


@pytest.mark.asyncio
async def test_dispatch_preserves_other_routes(monkeypatch, upstream):
    from app.capabilities import dispatcher
    from app.capabilities.models import CapabilityResult
    from app.voice.orchestrator import handle_voice_request
    assert dispatcher.CAPABILITIES == (dispatcher.replay_capability, dispatcher.nutrition_capability,
                                       mealie_capability, dispatcher.music_capability)
    empty = CapabilityResult(False, False, None, "not_claimed")
    async def replay(request):
        return CapabilityResult(True, True, "replay", "fixture") if request.text == "Repeat that" else empty
    async def nutrition(request):
        return CapabilityResult(True, True, "nutrition", "fixture") if request.text == "Log water" else empty
    async def music(request):
        return CapabilityResult(True, True, "music", "fixture") if request.text == "Play jazz" else empty
    monkeypatch.setattr(dispatcher.replay_capability, "handle", AsyncMock(side_effect=replay))
    monkeypatch.setattr(dispatcher.nutrition_capability, "handle", AsyncMock(side_effect=nutrition))
    music_mock = AsyncMock(side_effect=music)
    monkeypatch.setattr(dispatcher.music_capability, "handle", music_mock)
    for text, domain in [("Repeat that", "replay"), ("Log water", "nutrition"), ("Play jazz", "music"), ("Weather?", None)]:
        result = await handle_voice_request(VoiceRequest(text=text))
        assert result["domain"] == domain
        if domain is None:
            assert result["path"] == "semantic"
    upstream.assert_not_awaited()
    music_mock.reset_mock()
    assert (await handle_voice_request(VoiceRequest(text="Find my lasagne recipe")))["domain"] == "mealie"
    music_mock.assert_not_awaited()
