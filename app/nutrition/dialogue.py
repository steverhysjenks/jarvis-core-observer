"""Bounded, explicit nutrition follow-ups. No language model or guessed portions."""
import json
import re
import time
from datetime import date, datetime, timedelta, timezone

from pydantic import ValidationError

from app.nutrition import service
from app.voice.requests import NutritionSelection

NUMBERS = {'a': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
           'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'half': 0.5,
           'whole': 1, 'full': 1}


def number(value):
    return NUMBERS[value] if value in NUMBERS else float(value)


def store(context, draft):
    with service.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS nutrition_drafts (context TEXT PRIMARY KEY, payload TEXT NOT NULL, expires REAL NOT NULL)')
        db.execute('DELETE FROM nutrition_drafts WHERE expires < ?', (time.time(),))
        db.execute('INSERT OR REPLACE INTO nutrition_drafts VALUES (?,?,?)', (context, json.dumps(draft), time.time()+600))


def load(context):
    with service.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS nutrition_drafts (context TEXT PRIMARY KEY, payload TEXT NOT NULL, expires REAL NOT NULL)')
        row = db.execute('SELECT payload FROM nutrition_drafts WHERE context=? AND expires>?', (context, time.time())).fetchone()
    return json.loads(row[0]) if row else None


def extract(draft, text):
    text = text.lower().strip().rstrip('.?!')
    today = datetime.now(service.TZ).date()
    explicit_date = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if explicit_date:
        draft['date'] = date.fromisoformat(explicit_date[1]).isoformat()
    elif 'yesterday' in text:
        draft['date'] = (today-timedelta(days=1)).isoformat()
    elif 'today' in text or 'just now' in text:
        draft['date'] = today.isoformat()
    if 'just now' in text:
        draft['clock'] = datetime.now(service.TZ).strftime('%H:%M')
    clock = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\s*(am|pm)?\b', text)
    if clock:
        hour = int(clock[1])
        if clock[3]:
            if hour > 12: raise ValueError('invalid 12-hour clock')
            hour = hour % 12 + (12 if clock[3] == 'pm' else 0)
        draft['clock'] = f'{hour:02}:{clock[2]}'
    if re.search(r'\bdinner\b', text): draft['meal'] = 'dinner'
    for pattern, meal in [('breakfast','breakfast'), ('lunch','lunch'), ('evening meal','evening meal'), ('snack','snack')]:
        if re.search(r'\b'+pattern+r'\b', text): draft['meal'] = meal
    # Explicit correction grammar: the new total is the amount, never an increment.
    corrected = re.search(r'\bto (\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\b', text)
    if draft['action'] == 'update_entry' and corrected:
        draft['quantity'] = number(corrected[1])
    pack = re.search(r'\bpack(?:et)? (?:weight |weighs )?(\d+(?:\.\d+)?)\s*g\b', text)
    if pack: draft['pack_weight_g'] = float(pack[1])
    amount_text = text[:pack.start()]+text[pack.end():] if pack else text
    amount = re.search(r'\b(\d+(?:\.\d+)?|a|one|two|three|four|five|six|seven|eight|nine|ten|half|whole|full)\s+(?:a\s+)?(grams?|g|ml|slices?|servings?|packets?)\b', amount_text)
    if amount:
        draft['quantity'] = number(amount[1])
        draft['unit'] = {'gram':'g','grams':'g'}.get(amount[2], amount[2].rstrip('s'))
    if draft['action'] == 'update_entry' and 'unit' not in draft:
        unit = re.search(r'\b(slices?|servings?|grams?|g|ml)\b', text)
        if unit: draft['unit'] = {'gram':'g','grams':'g'}.get(unit[1],unit[1].rstrip('s'))
    product = re.search(r'\bproduct\s+"([^"]+)"', text) or re.search(r'\bproduct\s+([^;]+)', text)
    if product:
        draft['query'] = product[1].strip()
        draft.pop('food_id',None); draft.pop('variant_id',None); draft.pop('entry_id',None)
        draft.pop('choices',None)
        draft.pop('variant_choices',None)
    choice = re.search(r'\b(?:choice|entry)\s+(\d+)\b',text)
    if choice:
        options = draft.get('choices',[])
        index = int(choice[1])-1
        if not 0 <= index < len(options): raise ValueError('invalid choice')
        selected = options[index]
        draft['entry_id' if draft['action'] != 'log_food' else 'food_id'] = selected['id']
    if draft['action'] == 'update_entry' and corrected:
        draft['quantity'] = number(corrected[1])
    variant = re.search(r'\bvariant\s+(\d+)\b',text)
    if variant:
        options = draft.get('variant_choices',[])
        index = int(variant[1])-1
        if not 0 <= index < len(options): raise ValueError('invalid variant')
        draft['variant_id'] = options[index]['id']
    return draft


def options_message(rows, diary=False):
    return [{'choice': i+1, 'name': row.get('food_name',row.get('name','Food')),
             **({'quantity':row.get('quantity'), 'unit':row.get('unit'), 'time':row.get('entry_time')} if diary else {})}
            for i,row in enumerate(rows)]


async def resolve(request):
    text = request.text.strip().lower()
    context = service.context_key(request)
    if text in ('nutrition cancel','nutrition: cancel'):
        with service.connection() as db:
            db.execute("DELETE FROM receipts WHERE context=? AND state='pending'", (context,))
        store(context,{})
        return {'status':'cancelled','message':'Pending nutrition actions cancelled. No diary entry was changed.'}
    continuing = text.startswith('nutrition:') or text.startswith('nutrition ')
    draft = load(context) if continuing else None
    if not draft:
        action = 'delete_entry' if text.startswith(('remove ','delete ')) else 'update_entry' if text.startswith('change ') else 'log_food'
        draft = {'action':action}
    try:
        extract(draft, text)
    except (ValueError, OverflowError):
        return service.clarify('Please give a valid date, amount or numbered choice. Reply with nutrition: followed by the corrected detail.')
    store(context,draft)
    def ask(message, **extra):
        return dict(service.clarify(message+' Reply with nutrition: followed by the missing details.'), **extra)
    if draft.get('meal') == 'dinner':
        return ask('By dinner, do you mean lunch or your evening meal?')
    if not draft.get('query') and not draft.get('food_id') and not draft.get('entry_id'):
        if 'rest of' in text:
            return ask('Which exact product and how many grams remain? I will not assume which packet you mean.')
        return ask('Which exact saved product? Say product followed by its name; use semicolons between details.')
    action = draft['action']
    if action != 'log_food':
        if not draft.get('date'):
            return ask('Which diary date: today, yesterday, or YYYY-MM-DD?')
        if not draft.get('entry_id'):
            diary = await service.sparky.call('sparky_get_food_diary',{'date':draft['date'],'limit':50})
            rows = [r for r in diary.get('food_entries',[]) if draft['query'].casefold() in str(r.get('food_name',r.get('name',''))).casefold()]
            if not rows:
                return ask('No matching food entry was found on that date. Check the product name and date.')
            if len(rows)==1 and not diary.get('has_more'):
                draft['entry_id']=rows[0]['id']
            else:
                draft['choices']=rows; store(context,draft)
                return ask('Which exact entry? Say entry and its number. This is a page of the diary, not necessarily the complete day.',options=options_message(rows,True))
        selection={k:draft[k] for k in ('action','entry_id','quantity','unit') if k in draft}
        selection['entry_date']=draft['date']
    else:
        if not draft.get('food_id'):
            found = await service.sparky.call('sparky_search_foods',{'query':draft['query'],'limit':10})
            rows = found.get('data',[])
            if not rows: return ask('No saved product matched. Import it through SparkyFitness or give another exact saved product name.')
            if len(rows)==1 and not found.get('has_more'):
                draft['food_id']=rows[0]['id']
            else:
                draft['choices']=rows; store(context,draft)
                return ask('Which product? Say choice and its number; narrow the name if the list is incomplete.',options=options_message(rows))
        for field,prompt in [('quantity','How much did you eat, such as 2 slices, 30 g or half a packet?'),('unit','Which unit: g, ml, slice, serving or packet?'),('meal','Which meal: breakfast, lunch, evening meal or snack?'),('date','Which consumption date: today, yesterday or YYYY-MM-DD?'),('clock','What actual consumption time? Use a 24-hour time, such as 08:15.')]:
            if field not in draft:
                store(context,draft); return ask(prompt)
        if draft['unit']=='packet' and not draft.get('pack_weight_g'):
            store(context,draft); return ask('What does one packet weigh? Say packet weighs followed by its weight in g.')
        food=await service.sparky.call('sparky_get_food_details',{'food_id':draft['food_id']})
        unit='g' if draft['unit']=='packet' else draft['unit']
        variants={v['id']:v for v in [food.get('default_variant')]+(food.get('variants') or []) if isinstance(v,dict) and v.get('id')}
        matches=[v for v in variants.values() if str(v.get('serving_unit','')).rstrip('s')==unit]
        if unit=='serving' and len(variants)==1: matches=list(variants.values())
        if draft.get('variant_id'):
            matches=[v for v in variants.values() if v['id']==draft['variant_id'] and (unit=='serving' or str(v.get('serving_unit','')).rstrip('s')==unit)]
        if len(matches)!=1:
            draft['variant_choices']=list(variants.values()); store(context,draft)
            return ask('Choose a defined serving reference: say variant and its number, and give the consumed amount in its unit or in servings. No slice weight or unit conversion will be guessed.',variants=[{'choice':i+1,'size':v.get('serving_size'),'unit':v.get('serving_unit')} for i,v in enumerate(variants.values())])
        draft['variant_id']=matches[0]['id']
        consumed=datetime.fromisoformat(draft['date']+'T'+draft['clock']).replace(tzinfo=service.TZ)
        # Ambiguous or skipped DST wall-clock times require a structured offset-aware selection.
        utc=consumed.astimezone(timezone.utc)
        if consumed.replace(fold=0).utcoffset()!=consumed.replace(fold=1).utcoffset() or utc.astimezone(service.TZ).replace(tzinfo=None)!=consumed.replace(tzinfo=None):
            return ask('That local clock time is ambiguous at a daylight-saving transition. Supply an explicit offset-aware consumption timestamp using the structured API.')
        selection={k:draft[k] for k in ('action','food_id','variant_id','quantity','unit','meal','pack_weight_g') if k in draft}
        selection['consumed_at']=consumed.isoformat()
    store(context,draft)
    try:
        return NutritionSelection(**selection)
    except ValidationError:
        return ask('The amount or selection is incomplete or invalid. Give a positive amount and an explicit unit.')

