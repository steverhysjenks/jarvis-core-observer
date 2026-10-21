"""Read-only Mealie operations through the existing HA integration."""
import asyncio
import os

from app.adapters.homeassistant import HomeAssistantError, ha_client

SEARCH_LIMIT = 6


def check_deadline(deadline):
    """Reject expired work even when an await returned without yielding."""
    if asyncio.get_running_loop().time() >= deadline:
        raise TimeoutError()


class MealieUnavailable(Exception):
    pass


class MealieClient:
    async def _read(self, service, data, key, *, deadline):
        check_deadline(deadline)
        entry = os.getenv("MEALIE_HA_CONFIG_ENTRY_ID", "").strip()
        if not entry:
            raise MealieUnavailable()
        try:
            # Both operations inherit the capability's single absolute deadline;
            # the generic HA transport's 30s timeout cannot extend this budget.
            async with asyncio.timeout_at(deadline):
                response = await ha_client.call_service(
                    "mealie", service, {"config_entry_id": entry, **data},
                    return_response=True,
                )
            check_deadline(deadline)
            return response["service_response"][key]
        except (HomeAssistantError, ValueError, KeyError, TypeError) as exc:
            raise MealieUnavailable() from exc

    async def search(self, query, *, deadline):
        result = await self._read("get_recipes", {
            "search_terms": query, "result_limit": SEARCH_LIMIT,
        }, "recipes", deadline=deadline)
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            raise MealieUnavailable()
        items = result["items"]
        if len(items) > SEARCH_LIMIT or any(not valid_recipe(x) for x in items):
            raise MealieUnavailable()
        return items

    async def recipe(self, recipe_id, *, deadline):
        result = await self._read("get_recipe", {"recipe_id": recipe_id}, "recipe", deadline=deadline)
        if not valid_recipe(result) or result["recipe_id"] != recipe_id:
            raise MealieUnavailable()
        return result


def valid_recipe(value):
    return isinstance(value, dict) and all(
        isinstance(value.get(k), str) and 0 < len(value[k].strip()) <= 500
        for k in ("recipe_id", "name", "slug")
    )


mealie_client = MealieClient()
