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

@pytest.mark.asyncio
@pytest.mark.parametrize('text,spoken', [
    (' How many calories have I consumed today?', '300 calories'),
    ('HOW MUCH PROTEIN HAVE I CONSUMED TODAY?', '12 grams of protein'),
    ('How many calories do I have left today?', '1,700 calories remaining'),
    ('What is my daily calorie target?', '2,000 calories'),
])
async def test_echomuse_reads_have_actual_spoken_values(text, spoken, monkeypatch):
    async def native(name, arguments, **kwargs):
        assert not kwargs.get('write')
        return {'calories':2000} if name=='sparky_get_goal_snapshot' else [{'calories':300,'protein':12,'carbs':40,'fat':10}]
    monkeypatch.setattr(service.sparky,'call',native)
    result=(await nutrition_capability.handle(VoiceRequest(text=text,conversation_id='voice-session'))).as_dict()
    assert result['domain']=='nutrition' and result['operation_status']=='read'
    assert spoken in result['speech'] and result['speech']!='Done.'
    assert result['conversation_id']=='voice-session'

@pytest.mark.asyncio
async def test_echomuse_yesterday_spoken_diary(monkeypatch):
    async def native(name, arguments, **kwargs):
        assert name=='sparky_get_food_diary'
        return {'food_entries':[{'food_name':'Fixture toast','quantity':2,'unit':'slice'}]}
    monkeypatch.setattr(service.sparky,'call',native)
    result=(await nutrition_capability.handle(VoiceRequest(text='What did I eat yesterday?'))).as_dict()
    assert '2 slice of Fixture toast' in result['speech']

@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['Can you add 750ml of water to my food diary?', 'Log 0.75 litres of water today'])
async def test_hydration_native_confirmed_once(text,monkeypatch):
    writes=[]
    async def native(name,arguments,**kwargs):
        assert kwargs.get('write') and name=='sparky_manage_food'
        writes.append(arguments)
        return {'message':'✅ Logged 750ml water.'}
    monkeypatch.setattr(service.sparky,'call',native)
    request=VoiceRequest(text=text,conversation_id='water-session',request_id='water-request')
    first=(await nutrition_capability.handle(request)).as_dict()
    assert first['operation_status']=='confirmation_required' and not writes
    assert '750 millilitres' in first['speech'] and first['continue_conversation']
    confirm=VoiceRequest(text='Yes.',conversation_id='water-session')
    done=(await nutrition_capability.handle(confirm)).as_dict()
    assert done['operation_status']=='completed' and 'Logged 750 millilitres' in done['speech']
    duplicate=confirm.model_copy(update={'nutrition_confirmation':first['result']['confirmation_id']})
    assert (await nutrition_capability.handle(duplicate)).result['status']=='already_completed'
    assert writes==[{'action':'log_water','amount_ml':750.0,'entry_date':datetime.now(service.TZ).date().isoformat()}]

@pytest.mark.asyncio
@pytest.mark.parametrize('text',['Log -750ml water','Log 0ml water','Log 750ml and 500ml water','Log 100 litres water'])
async def test_hydration_ambiguous_amount_never_writes(text,monkeypatch):
    async def forbidden(*args,**kwargs): pytest.fail('Invalid water amount reached MCP')
    monkeypatch.setattr(service.sparky,'call',forbidden)
    assert (await nutrition_capability.handle(VoiceRequest(text=text))).result['status']=='clarification_required'

@pytest.mark.asyncio
async def test_unprefixed_clarification_session_and_other_domains(monkeypatch):
    request=VoiceRequest(text='I had biscuits',conversation_id='session-one',user_context='owner')
    first=(await nutrition_capability.handle(request)).as_dict()
    assert first['continue_conversation']
    follow=request.model_copy(update={'text':'lunch'})
    assert (await nutrition_capability.handle(follow)).claimed
    for text in ['Turn on the kitchen light','Play jazz','Who wrote Hamlet?']:
        assert not (await nutrition_capability.handle(request.model_copy(update={'text':text}))).claimed
    assert not (await nutrition_capability.handle(follow.model_copy(update={'conversation_id':'other'}))).claimed
    assert not (await nutrition_capability.handle(follow.model_copy(update={'user_context':'other'}))).claimed

def test_missing_results_fail_closed():
    from app.nutrition.presentation import present
    assert 'could not verify' in present({'status':'unexpected'})
    assert 'incomplete' in present({'status':'read','query':'remaining','totals':{},'remaining_calories':None})

@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected_type,continuing', [('read','query_answer',False),('clarification_required','action_done',True),('unavailable','error',False)])
async def test_ha_forwarding_boundary(status,expected_type,continuing):
    # Execute the actual integration method with isolated HA/session interfaces.
    import ast
    from pathlib import Path
    from types import SimpleNamespace as NS
    import uuid
    source=Path(__file__).resolve().parents[2]/'integrations/homeassistant/jarvis_router/conversation.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
    method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_async_handle_message')
    captured={}
    class Response:
        status=200
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def json(self): return {'speech':'Actual native answer','domain':'nutrition','operation_status':status,'continue_conversation':continuing}
    class Session:
        def post(self,*args,**kwargs): captured.update(kwargs['json']);return Response()
    class IntentResponse:
        def __init__(self,**kwargs): self.response_type='action_done'
        def async_set_speech(self,value): self.speech=value
        def async_set_error(self,code,value): self.response_type='error';self.speech=value
    namespace={'ConversationInput':object,'ChatLog':object,'ConversationResult':object,
               'dr':None,'ar':None,'_LOGGER':NS(debug=lambda *a:None),'uuid':uuid,
               'async_get_clientsession':lambda _:Session(),'aiohttp':NS(ClientTimeout=lambda **kw:kw),
               'AssistantContent':lambda **kw:kw,'conversation':NS(ConversationResult=lambda **kw:NS(**kw)),
               'intent':NS(IntentResponse=IntentResponse,IntentResponseType=NS(QUERY_ANSWER='query_answer'),IntentResponseErrorCode=NS(FAILED_TO_HANDLE='failed'))}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),namespace)
    user=NS(text='How much protein have I consumed today?',device_id=None,conversation_id='ha-session',context=NS(user_id='owner'),agent_id='conversation.jarvis_router',language='en',satellite_id='office')
    result=await namespace['_async_handle_message'](NS(hass=None,_url='http://router.invalid',_api_key='test-key'),user,NS(async_add_assistant_content_without_tools=lambda _:None))
    assert captured['conversation_id']=='ha-session' and captured['user_context']=='owner'
    assert captured['origin']=='home_assistant' and captured['request_id']
    assert result.response.speech=='Actual native answer'
    assert result.response.response_type==expected_type and result.continue_conversation==continuing

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

@pytest.mark.asyncio
async def test_confirmation_shows_serving_reference_and_corrected_total(monkeypatch):
    async def native(name,args,**kwargs):
        if name=='sparky_get_food_diary':
            return {'food_entries':[{'id':ENTRY,'food_name':'Defined toast','quantity':2,'unit':'slice','entry_time':'08:15'}]}
        return {'id':FOOD,'name':'Defined serving','is_custom':True,'variants':[{'id':VARIANT,'serving_size':35,'serving_unit':'g','calories':80,'protein':3,'carbs':15,'fat':1}]}
    monkeypatch.setattr(service.sparky,'call',native)
    serving=await service.prepare(selected(unit='serving',quantity=2,variant_id=VARIANT))
    assert 'serving reference 35 g' in serving['description']
    correction=await service.prepare(NutritionSelection(action='update_entry',entry_id=ENTRY,entry_date='2026-10-18',quantity=3,unit='slice'))
    assert 'change total to 3 slice' in correction['description']

@pytest.mark.asyncio
async def test_protein_product_names_are_not_daily_total_questions(monkeypatch):
    calls=[]
    async def native(name,args,**kwargs):
        calls.append(name)
        assert name=='sparky_search_foods'
        return {'data':[],'has_more':False}
    monkeypatch.setattr(service.sparky,'call',native)
    assert (await service.handle(VoiceRequest(text='Search food protein bar')))['status']=='read'
    assert calls==['sparky_search_foods']
    calls.clear()
    assert (await service.handle(VoiceRequest(text="I've eaten a protein bar")))['status']=='clarification_required'
    assert not calls
    result=await service.handle(VoiceRequest(text='nutrition: product protein bar; 20 g; snack; today at 08:15'))
    assert result['status']=='clarification_required' and calls==['sparky_search_foods']

@pytest.mark.asyncio
async def test_zero_denominator_is_a_clarification_not_a_write():
    from app.nutrition import dialogue
    result=await dialogue.resolve(VoiceRequest(text='nutrition: 1/0 packet'))
    assert result['status']=='clarification_required'

@pytest.mark.asyncio
async def test_history_explicit_date_range_and_pagination(monkeypatch):
    calls=[]
    async def native(name,args,**kwargs):
        calls.append((name,args))
        return {'food_entries':[],'meal_entries':[{'entry_time':'08:00'},{'entry_time':'19:00'}],'has_more':True,'next_offset':100}
    monkeypatch.setattr(service.sparky,'call',native)
    result=await service.handle(VoiceRequest(text='What did I eat 2026-10-01 to 2026-10-20 evening page 2?'))
    assert calls[0][1]=={'start_date':'2026-10-01','end_date':'2026-10-20','limit':50,'offset':50}
    assert len(result['diary']['meal_entries'])==1 and result['diary']['has_more']
    calls.clear()
    assert (await service.handle(VoiceRequest(text='What did I eat last Monday?')))['status']=='clarification_required'
    assert not calls
    result=await service.handle(VoiceRequest(text='History',nutrition_history={'start_date':'2026-10-18','end_date':'2026-10-19','offset':50}))
    assert result['status']=='read' and calls[0][1]['offset']==50

@pytest.mark.asyncio
async def test_history_rejects_unbounded_or_reversed_range(monkeypatch):
    async def forbidden(*args,**kwargs): pytest.fail('Invalid range reached server')
    monkeypatch.setattr(service.sparky,'call',forbidden)
    for start,end in [('2026-01-01','2026-10-20'),('2026-10-20','2026-10-01')]:
        assert (await service.handle(VoiceRequest(text='History',nutrition_history={'start_date':start,'end_date':end})))['status']=='clarification_required'

@pytest.mark.asyncio
async def test_yesterdays_totals_do_not_silently_return_today(monkeypatch):
    calls=[]
    async def native(name,args,**kwargs):
        calls.append((name,args))
        return {'calories':2000} if name=='sparky_get_goal_snapshot' else [{'calories':100,'protein':1,'carbs':2,'fat':3}]
    monkeypatch.setattr(service.sparky,'call',native)
    day=(service.datetime.now(service.TZ).date()-service.timedelta(days=1)).isoformat()
    result=await service.handle(VoiceRequest(text='How much protein did I eat yesterday?'))
    assert result['date']==day and calls[0][1]['date']==day and calls[1][1]['target_date']==day

@pytest.mark.parametrize('label',['2 slices white bread','Breakfast dinner bar 2026-01-01','Packet weighs 100 g','Minus -2 g product'])
def test_product_labels_cannot_supply_consumption_fields(label):
    from app.nutrition.dialogue import extract
    draft={'action':'log_food','quantity':1,'unit':'slice','meal':'snack','date':'2026-10-18','clock':'08:15'}
    result=extract(draft.copy(),'nutrition: product "'+label+'"')
    assert result['query']==label.lower()
    assert all(result[k]==v for k,v in draft.items())


def test_explicit_fields_override_portion_without_reading_label_numbers():
    from app.nutrition.dialogue import extract
    result=extract({'action':'log_food'},'nutrition: product "Breakfast 2 slices 2026-01-01"; 1 slice; snack; 2026-10-18 at 08:15')
    assert result['quantity']==1 and result['unit']=='slice' and result['meal']=='snack' and result['date']=='2026-10-18'
