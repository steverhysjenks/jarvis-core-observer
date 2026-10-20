"""Channel-independent spoken text from native results; never model-generated."""
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def spoken_day(value):
    """Keep historical context without handing ISO punctuation to speech."""
    try:
        day=date.fromisoformat(value)
    except (TypeError, ValueError):
        return 'for the requested day'
    today=datetime.now(ZoneInfo('Europe/London')).date()
    if day==today:
        return 'today'
    if day==today-timedelta(days=1):
        return 'yesterday'
    return 'on '+day.strftime('%d %B %Y').lstrip('0')


def water_speech(result, confirming=False):
    when=spoken_day(result.get('date'))
    # Routine current-day acknowledgements need no date suffix at all.
    period='' if when=='today' else ' '+when
    amount=number(result.get('amount_ml'))
    return f'Log {amount} millilitres of water{period}. Confirm?' if confirming else f'Logged {amount} millilitres of water{period}.'


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        return None
    return f'{value:,.1f}'.rstrip('0').rstrip('.') if value % 1 else f'{value:,.0f}'


def present(result):
    status = result.get('status')
    if status == 'read':
        query = result.get('query')
        if query == 'goal':
            value = number(result.get('effective_goal'))
            return f'Your calorie target is {value} calories.' if value else 'Your configured calorie target is unavailable in SparkyFitness.'
        if 'totals' in result:
            field = 'protein' if query == 'protein' else 'calories'
            value = number(result.get('remaining_calories') if query == 'remaining' else result['totals'].get(field))
            if value is None:
                return 'I cannot give a reliable remaining allowance or total because the native nutrition data is incomplete.'
            if query == 'remaining':
                speech = f'You have {value} calories left {spoken_day(result.get("date"))}.'
            else:
                speech = f'You have logged {value} {"grams of protein" if field == "protein" else "calories"} {spoken_day(result.get("date"))}.'
            if result.get('nutrition_warning'):
                speech += ' Some logged nutrition is incomplete, so this total may be understated.'
            return speech
        if 'diary' in result:
            diary=result['diary']
            entries=diary.get('food_entries',[])+diary.get('meal_entries',[])
            if not entries:
                return 'No matching food entries were found in your SparkyFitness diary for that period.'
            descriptions=[]
            for row in entries[:8]:
                name=row.get('food_name') or row.get('meal_name') or row.get('name') or 'an unnamed entry'
                amount=number(row.get('quantity'))
                descriptions.append(f'{amount} {row.get("unit") or "servings"} of {name}' if amount else str(name))
            speech='Your diary records '+ '; '.join(descriptions)+'.'
            if len(entries)>8 or diary.get('has_more'):
                speech+=' There are more entries; ask for a narrower date or another page.'
            if diary.get('unclassified_time_count'):
                speech+=' Entries without consumption times were not assigned to the evening.'
            return speech
        if 'foods' in result:
            rows=result['foods'].get('data',[])
            return 'Saved foods: '+ '; '.join(str(r.get('name','unnamed food')) for r in rows[:8])+'.' if rows else 'No matching saved food was found.'
    if status == 'confirmation_required' and result.get('action')=='log_water':
        return water_speech(result, confirming=True)
    if status == 'completed':
        if result.get('action') == 'log_water':
            return water_speech(result)
        return {'delete_entry':'The selected diary entry was removed.', 'update_entry':'The selected diary entry was corrected.', 'log_food':'The confirmed food was logged in your diary.'}.get(result.get('action'),'The confirmed nutrition operation completed.')
    if status == 'already_completed':
        return 'That request was already completed. I have not added or changed it again.'
    message=result.get('message')
    if isinstance(message,str) and message.strip():
        speech=message
        for option in result.get('options',[])[:8]:
            speech+=f' Choice {option["choice"]}: {option["name"]}.'
        for variant in result.get('variants',[])[:8]:
            speech+=f' Variant {variant["choice"]}: {variant.get("size")} {variant.get("unit")}.'
        return speech
    return 'I could not verify the nutrition result. Nothing will be automatically retried; please check SparkyFitness before trying again.'
