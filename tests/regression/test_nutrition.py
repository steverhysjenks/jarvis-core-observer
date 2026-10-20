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

@pytest.mark.asyncio
async def test_incomplete_native_day_and_energy_units_are_not_misrepresented(monkeypatch):
    row = {'calories': 100, 'protein': 1, 'carbs': 2, 'fat': 3,
           'nutrition_warning': 'Legacy entries excluded', 'energy_unit': 'kcal'}
    async def native(name, arguments, **kwargs):
        return {'calories': 2000} if name == 'sparky_get_goal_snapshot' else [row]
    monkeypatch.setattr(service.sparky, 'call', native)
    result = await service.handle(VoiceRequest(text='How many calories do I have left today?'))
    assert result['remaining_calories'] is None and result['nutrition_warning']
    row['energy_unit'] = 'kJ'
    with pytest.raises(NutritionUnavailable):
        await service.handle(VoiceRequest(text='How much protein have I eaten?'))

@pytest.mark.asyncio
async def test_voice_packet_followups_resolve_without_guessing(monkeypatch):
    from app.nutrition import dialogue
    food = {'id': FOOD, 'name': 'Defined crisps', 'is_custom': True,
            'variants': [{'id': VARIANT, 'serving_size': 100, 'serving_unit': 'g',
                          'calories': 519, 'protein': 6.4, 'carbs': 52, 'fat': 31}]}
    async def native(name, arguments, **kwargs):
        assert not kwargs.get('write')
        return {'data':[food], 'has_more':False} if name=='sparky_search_foods' else food
    monkeypatch.setattr(service.sparky,'call',native)
    request = VoiceRequest(text='I had half a packet of biscuits.',listener='owner')
    assert (await service.handle(request))['status']=='clarification_required'
    followup = request.model_copy(update={'text':'nutrition: product Defined crisps; snack; 2026-10-18 at 08:15; packet weighs 45 g'})
    result = await service.handle(followup)
    assert result['status']=='confirmation_required'
    with service.connection() as db:
        payload = __import__('json').loads(db.execute('SELECT payload FROM receipts WHERE id=?',(result['confirmation_id'],)).fetchone()[0])
    assert payload['quantity']==22.5 and payload['unit']=='g' and payload['entry_time']=='08:15'
    # Context isolation: another listener cannot inherit the packet fraction.
    other = await service.handle(followup.model_copy(update={'listener':'other'}))
    assert other['status']=='clarification_required'

@pytest.mark.asyncio
async def test_voice_dinner_selection_does_not_infer_date_or_time(monkeypatch):
    from app.nutrition import dialogue
    request = VoiceRequest(text='Log my dinner at half past twelve.')
    first = await dialogue.resolve(request)
    assert 'lunch' in first['message']
    second = await dialogue.resolve(request.model_copy(update={'text':'nutrition: lunch'}))
    assert second['status']=='clarification_required'
    draft=dialogue.load(service.context_key(request))
    assert draft['meal']=='lunch' and 'clock' not in draft and 'date' not in draft

@pytest.mark.asyncio
async def test_voice_numbered_choice_requires_existing_options(monkeypatch):
    from app.nutrition import dialogue
    request = VoiceRequest(text='nutrition: choice 99')
    assert (await dialogue.resolve(request))['status']=='clarification_required'
    assert not (await nutrition_capability.handle(VoiceRequest(text='Play jazz'))).claimed

@pytest.mark.asyncio
async def test_explicit_native_serving_reference_is_supported(monkeypatch):
    async def native(*args,**kwargs):
        return {'id':FOOD,'name':'Defined serving','is_custom':True,
                'variants':[{'id':VARIANT,'serving_size':35,'serving_unit':'g',
                             'calories':80,'protein':3,'carbs':15,'fat':1}]}
    monkeypatch.setattr(service.sparky,'call',native)
    payload=(await service.prepare(selected(unit='serving',quantity=2,variant_id=VARIANT)))['payload']
    assert payload['quantity']==2 and payload['unit']=='serving' and payload['variant_id']==VARIANT

@pytest.mark.asyncio
async def test_voice_correction_resolves_dated_entry_and_new_total(monkeypatch):
    from app.nutrition import dialogue
    async def native(name,args,**kwargs):
        return {'food_entries':[{'id':ENTRY,'food_name':'Defined toast','quantity':2,'unit':'slice','entry_time':'08:15'}], 'has_more':False}
    monkeypatch.setattr(service.sparky,'call',native)
    request=VoiceRequest(text='Change the number of slices of toast I had for breakfast to three')
    assert (await dialogue.resolve(request))['status']=='clarification_required'
    resolved=await dialogue.resolve(request.model_copy(update={'text':'nutrition: product Defined toast; today'}))
    assert resolved.quantity==3 and resolved.unit=='slice' and str(resolved.entry_id)==ENTRY

@pytest.mark.asyncio
async def test_voice_cancel_does_not_mutate_diary(monkeypatch):
    from app.nutrition import dialogue
    request=VoiceRequest(text='nutrition cancel')
    assert (await dialogue.resolve(request))['status']=='cancelled'
    assert dialogue.load(service.context_key(request))=={}


@pytest.mark.parametrize('amount,expected',[('0.5 packet',0.5),('.5 packet',0.5),('1/2 packet',0.5),('half a packet',0.5),('two slices',2)])
def test_voice_portion_parser_never_reinterprets_fraction(amount,expected):
    from app.nutrition.dialogue import extract
    assert extract({'action':'log_food'},amount)['quantity']==expected

@pytest.mark.parametrize('amount',['-2 g','-two slices','one and a half packets','between 1 and 2 servings'])
def test_ambiguous_amounts_are_rejected(amount):
    from app.nutrition.dialogue import extract
    with pytest.raises(ValueError): extract({'action':'log_food'},amount)

@pytest.mark.asyncio
async def test_unknown_followup_cannot_reuse_complete_draft():
    from app.nutrition import dialogue
    request=VoiceRequest(text='nutrition: unrelated words')
    dialogue.store(service.context_key(request),{'action':'log_food','food_id':FOOD,'quantity':1,'unit':'g','meal':'snack','date':'2026-10-18','clock':'08:15'})
    assert (await dialogue.resolve(request))['status']=='clarification_required'

@pytest.mark.parametrize('amount',['2 slices and 3 g','0:15pm'])
def test_multiple_portions_and_invalid_am_pm_are_not_silently_selected(amount):
    from app.nutrition.dialogue import extract
    with pytest.raises(ValueError): extract({'action':'log_food'},amount)
