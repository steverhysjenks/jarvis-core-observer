from datetime import datetime
import httpx
from app.config import settings

class HomeAssistantError(Exception):
    pass

class HomeAssistantClient:
    def __init__(self):
        self.base_url = settings.ha_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.ha_token}", "Content-Type": "application/json"}

    async def _get(self, path: str, params: dict | None = None):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}{path}", headers=self.headers, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise HomeAssistantError(f"Home Assistant request failed: {path}") from exc

    async def get_state(self, entity_id: str) -> dict:
        return await self._get(f"/api/states/{entity_id}")

    async def get_state_optional(self, entity_id: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/states/{entity_id}", headers=self.headers)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise HomeAssistantError(f"Home Assistant request failed: {entity_id}") from exc

    async def get_states(self) -> list[dict]:
        return await self._get("/api/states")

    async def get_entities_by_domain(self, domain: str) -> list[dict]:
        states = await self.get_states()
        return [s for s in states if s["entity_id"].startswith(f"{domain}.")]

    async def get_calendar_events(self, entity_id: str, start: datetime, end: datetime) -> list[dict]:
        return await self._get(f"/api/calendars/{entity_id}", params={"start": start.isoformat(), "end": end.isoformat()})

    async def get_history(self, entity_id: str, start: datetime, end: datetime | None = None) -> list[dict]:
        params = {"filter_entity_id": entity_id, "minimal_response": "", "no_attributes": ""}
        if end is not None:
            params["end_time"] = end.isoformat()
        response = await self._get(f"/api/history/period/{start.isoformat()}", params=params)
        return response[0] if response else []

ha_client = HomeAssistantClient()

# Milestone 2 action boundary
async def _call_service(self, domain: str, service: str, data: dict) -> dict | list:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self.headers,
                json=data,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HomeAssistantError(f"Home Assistant service call failed: {domain}.{service}") from exc

HomeAssistantClient.call_service = _call_service
