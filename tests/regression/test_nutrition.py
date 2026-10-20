"""Reviewed offline nutrition boundaries; no network or production data."""
from datetime import datetime
from uuid import UUID

import pytest

from app.adapters.sparky_mcp import NutritionUnavailable, SparkyMCP
from app.capabilities.nutrition import nutrition_capability
from app.nutrition import service
from app.voice.requests import NutritionSelection, VoiceRequest

FOOD = '11111111-1111-4111-8111-111111111111'
VARIANT = '22222222-2222-4222-8222-222222222222'
ENTRY = '33333333-3333-4333-8333-333333333333'

@pytest.fixture(autouse=True)
def state(monkeypatch, tmp_path):
    monkeypatch.setattr(service, 'STATE_PATH', tmp_path / 'nutrition.sqlite')
    monkeypatch.setenv('NUTRITION_ENABLED', 'true')

@pytest.mark.asyncio
@pytest.mark.parametrize('text', [
    "I've eaten two slices of toast for breakfast.",
    'I had half a packet of biscuits.',
    'Log my dinner at half past twelve.',
    'Log the rest of that packet as a snack.',
    'Remove the chocolate bar I logged by mistake.',
    'Change the number of slices of toast I had for breakfast to three',
])
async def test_ambiguous_requests_never_write(text, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail('Ambiguous request reached native API')
    monkeypatch.setattr(service.sparky, 'call', forbidden)
    result = await nutrition_capability.handle(VoiceRequest(text=text))
    assert result.claimed
    assert result.result['status'] == 'clarification_required'

@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['How many calories do I have left today?', 'How much protein have I eaten?'])
async def test_totals_use_native_goal_and_never_assert_missing_nutrients(text, monkeypatch):
    async def native(name, arguments, **kwargs):
        assert not kwargs.get('write')
        if name == 'sparky_get_goal_snapshot':
            return {'calories': 2000}
        return [{'calories': 300, 'protein': 12, 'carbs': 40, 'fat': 10}]
    monkeypatch.setattr(service.sparky, 'call', native)
    result = (await nutrition_capability.handle(VoiceRequest(text=text))).result
    assert result['totals']['protein'] == 12
    assert result['remaining_calories'] == 1700
    assert all(v is None for v in result['unsupported_nutrients'].values())

@pytest.mark.asyncio
async def test_history_preserves_pagination_and_unknown_times(monkeypatch):
    async def native(name, arguments, **kwargs):
        return {'food_entries': [{'entry_time': '18:15', 'iron': 0}, {'entry_time': None}], 'has_more': True, 'next_offset': 50}
    monkeypatch.setattr(service.sparky, 'call', native)
    result = await service.handle(VoiceRequest(text='What did I eat yesterday evening?'))
    assert len(result['diary']['food_entries']) == 1
    assert result['diary']['food_entries'][0]['iron'] is None
    assert result['diary']['unclassified_time_count'] == 1
    assert result['diary']['has_more'] is True

@pytest.mark.asyncio
async def test_other_capabilities_and_disabled_mode_preserved(monkeypatch):
    assert not (await nutrition_capability.handle(VoiceRequest(text='Play jazz'))).claimed
    monkeypatch.setenv('NUTRITION_ENABLED', 'false')
    assert not (await nutrition_capability.handle(VoiceRequest(text='I had toast'))).claimed


def selected(**updates):
    data = dict(food_id=FOOD, quantity=0.5, unit='packet', pack_weight_g=45,
                meal='snack', consumed_at='2026-10-18T12:30:00+01:00')
    data.update(updates)
    return NutritionSelection(**data)

@pytest.mark.asyncio
async def test_packet_requires_explicit_reference_and_time(monkeypatch):
    async def native(*args, **kwargs):
        return {'id': FOOD, 'name': 'Test crisps', 'is_custom': True,
                'variants': [{'id': VARIANT, 'serving_unit': 'g', 'serving_size': 100,
                              'calories': 519, 'protein': 6.4, 'carbs': 52, 'fat': 31}]}
    monkeypatch.setattr(service.sparky, 'call', native)
    assert (await service.prepare(selected(pack_weight_g=None)))['status'] == 'clarification_required'
    assert (await service.prepare(selected(meal='dinner')))['status'] == 'clarification_required'
    assert (await service.prepare(selected(consumed_at='2026-10-18T12:30:00')))['status'] == 'clarification_required'
    payload = (await service.prepare(selected()))['payload']
    assert payload['quantity'] == 22.5 and payload['unit'] == 'g'
    assert payload['entry_time'] == '12:30' and payload['entry_date'] == '2026-10-18'

@pytest.mark.asyncio
async def test_receipts_confirm_once_and_survive_reopen(monkeypatch):
    writes = []
    async def prepare(_):
        return {'payload': {'action': 'log_food', 'food_id': FOOD, 'quantity': 22.5}, 'description': 'Test portion'}
    async def native(name, arguments, **kwargs):
        writes.append(arguments)
        return {'message': '✅ Logged. Entry ID: ' + ENTRY + '.'}
    monkeypatch.setattr(service, 'prepare', prepare)
    monkeypatch.setattr(service.sparky, 'call', native)
    request = VoiceRequest(text='Log this', request_id='retry-id', nutrition=selected(), listener='owner')
    first = await service.handle(request)
    assert not writes
    duplicate = await service.handle(request)
    assert duplicate['confirmation_id'] == first['confirmation_id']
    confirmation = VoiceRequest(text='Confirm', nutrition_confirmation=first['confirmation_id'], listener='owner')
    assert (await service.handle(confirmation))['entry_id'] == ENTRY
    assert (await service.handle(confirmation))['status'] == 'already_completed'
    assert (await service.handle(request))['status'] == 'already_completed'
    assert len(writes) == 1
    stranger = confirmation.model_copy(update={'listener': 'other'})
    assert (await service.handle(stranger))['status'] == 'clarification_required'

@pytest.mark.asyncio
async def test_uncertain_write_is_never_retried(monkeypatch):
    with service.connection() as db:
        db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?)', ('a'*64, service.context_key(VoiceRequest(text='Confirm')), 'fingerprint', '{"action":"log_food"}', 'pending', None, service.time.time()+600))
    calls = []
    async def native(*args, **kwargs):
        calls.append(1)
        raise NutritionUnavailable('timeout')
    monkeypatch.setattr(service.sparky, 'call', native)
    request = VoiceRequest(text='Confirm', nutrition_confirmation='a'*64)
    assert (await service.handle(request))['status'] == 'reconciliation_required'
    assert (await service.handle(request))['status'] == 'reconciliation_required'
    assert len(calls) == 1

@pytest.mark.asyncio
async def test_correction_requires_exact_entry_and_original_unit(monkeypatch):
    async def native(*args, **kwargs):
        return {'food_entries': [{'id': ENTRY, 'unit': 'slice', 'food_name': 'Test toast'}]}
    monkeypatch.setattr(service.sparky, 'call', native)
    selection = NutritionSelection(action='update_entry', entry_id=ENTRY, entry_date='2026-10-18', quantity=3, unit='slice')
    assert (await service.prepare(selection))['payload'] == {'action': 'update_entry', 'entry_id': ENTRY, 'quantity': 3, 'unit': 'slice'}
    assert (await service.prepare(selection.model_copy(update={'unit': 'g'})))['status'] == 'clarification_required'
    assert (await service.prepare(selection.model_copy(update={'entry_id': UUID(FOOD)})))['status'] == 'clarification_required'

@pytest.mark.asyncio
async def test_mcp_allowlist_and_error_envelopes(monkeypatch):
    client = SparkyMCP()
    with pytest.raises(NutritionUnavailable):
        await client.call('sparky_manage_goals', {})
    with pytest.raises(NutritionUnavailable):
        await client.call('sparky_manage_food', {'action': 'delete_food'}, write=True)
    client.ready = True
    async def rpc(*args, **kwargs):
        return {'content': [{'type': 'text', 'text': '❌ Invalid operation'}]}
    monkeypatch.setattr(client, 'rpc', rpc)
    with pytest.raises(NutritionUnavailable):
        await client.call('sparky_get_food_details', {'food_id': FOOD})

@pytest.mark.asyncio
async def test_wrong_mcp_server_refused(monkeypatch):
    client = SparkyMCP()
    async def rpc(*args, **kwargs):
        return {'protocolVersion': '2025-11-25', 'serverInfo': {'name': 'other'}}
    monkeypatch.setattr(client, 'rpc', rpc)
    with pytest.raises(NutritionUnavailable):
        await client.call('sparky_search_foods', {'query': 'toast'})
