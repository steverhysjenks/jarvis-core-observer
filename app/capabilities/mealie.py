"""Deterministic saved-recipe lookup. No inference, writes or cooking state."""
import asyncio
import os
import re

from app.adapters.mealie import MealieUnavailable, SEARCH_LIMIT, check_deadline, mealie_client
from app.capabilities.models import CapabilityResult

# Fixed below Router's unchanged 20s Core timeout; never reset per HA call.
MEALIE_DEADLINE_SECONDS = 15.0

LOOKUP = re.compile(r"(?:find|search for|look up|show me) (?:my |the )?(.+?) recipe", re.I)
INGREDIENTS = re.compile(
    r"(?:what ingredients do i need for|(?:show me |list )?(?:the )?ingredients for) (?:my |the )?(.+?)(?: recipe)?", re.I,
)


def recognise(text):
    text = re.sub(r"^jarvis[,:]?\s+", "", text.strip(), flags=re.I)
    text = re.sub(r"[.!?]+$", "", text).strip()
    # Only one bounded request: do not absorb another sentence/action as a name.
    if re.search(r"[.!?;\r\n]", text):
        return None
    for intent, pattern in (("ingredients", INGREDIENTS), ("lookup", LOOKUP)):
        match = pattern.fullmatch(text)
        if match and 0 < len(match[1].strip()) <= 200:
            return intent, match[1].strip()
    return None


class MealieCapability:
    async def handle(self, request):
        deadline = asyncio.get_running_loop().time() + MEALIE_DEADLINE_SECONDS
        recognised = recognise(request.text)
        if recognised is None:
            return CapabilityResult(False, False, None, "not_claimed")
        intent, query = recognised

        def reply(status, speech, **data):
            return CapabilityResult(True, status == "found", "mealie", "ha_recipe_read",
                                    {"status": status, **data}, {
                                        "speech": speech, "operation_status": status,
                                        "intent": intent, "query": query,
                                        "source": "mealie", "continue_conversation": False,
                                    })

        if os.getenv("MEALIE_ENABLED", "false").lower() != "true":
            return reply("disabled", "Saved recipe lookup is currently disabled.")
        try:
            async with asyncio.timeout_at(deadline):
                result = await self._lookup(intent, query, reply, deadline=deadline)
                # Synchronous result preparation may finish without yielding to
                # the event loop. Never return a late success/clarification.
                check_deadline(deadline)
                return result
        except TimeoutError:
            return reply("unavailable", "I can't access your saved recipes right now. Please try again later.",
                         reason="deadline_exceeded")
        except MealieUnavailable:
            return reply("unavailable", "I can't access your saved recipes right now. Please try again later.")

    async def _lookup(self, intent, query, reply, *, deadline):
        matches = await mealie_client.search(query, deadline=deadline)
        if not matches:
            return reply("not_found", "I couldn't find a saved recipe matching that name.")
        # HA's deployed response omits pagination totals. A full page is
        # potentially truncated, so never select an apparent exact match.
        if len(matches) != 1:
            choices = [{k: x[k] for k in ("recipe_id", "name", "slug")} for x in matches]
            return reply("ambiguous", "I found several recipes: " +
                         "; ".join(x["name"] for x in choices[:3]) +
                         ". Please repeat your request with the full recipe name.",
                         matches=choices, possibly_truncated=len(matches) == SEARCH_LIMIT)
        recipe = await mealie_client.recipe(matches[0]["recipe_id"], deadline=deadline)
        record = {k: recipe[k] for k in ("recipe_id", "name", "slug")}
        record["description"] = recipe.get("description")
        record["servings"] = recipe.get("recipe_servings")
        ingredients = recipe.get("ingredients")
        if not isinstance(ingredients, list) or len(ingredients) > 200:
            raise MealieUnavailable()
        displays = []
        for item in ingredients:
            if not isinstance(item, dict):
                raise MealieUnavailable()
            display = item.get("display")
            if not isinstance(display, str) or not display.strip() or len(display) > 1000:
                return reply("incomplete", "This recipe has incomplete ingredient information. Please check it in Mealie.", recipe=record)
            displays.append(display)
        record["ingredients"] = displays
        record["instructions"] = recipe.get("instructions", [])
        if intent == "ingredients":
            if not displays:
                return reply("incomplete", "No ingredients are recorded for this recipe in Mealie.", recipe=record)
            spoken = "; ".join(displays[:6])
            if len(spoken) > 700:
                speech = f"I found {recipe['name']}. The ingredient list is too long to read aloud; please check the recipe details."
            else:
                speech = f"For {recipe['name']}: {spoken}."
                if len(displays) > 6:
                    speech += f" That's the first 6 of {len(displays)} ingredients; see the recipe details for the full list."
        else:
            speech = f"I found your saved recipe: {recipe['name']}."
        return reply("found", speech, recipe=record)


mealie_capability = MealieCapability()
