from typing import Literal

import logging
import uuid

import aiohttp

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    AssistantContent,
    ChatLog,
    ConversationEntity,
    ConversationInput,
    ConversationResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_API_KEY, CONF_URL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Jarvis Router conversation entity."""

    async_add_entities(
        [
            JarvisRouterConversationEntity(
                hass,
                entry,
            )
        ]
    )


class JarvisRouterConversationEntity(ConversationEntity):
    """Jarvis Router conversation agent."""

    _attr_name = "Jarvis Router"
    _attr_unique_id = "jarvis_router_conversation"
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self.hass = hass
        self._url = entry.data[CONF_URL].rstrip("/")
        self._api_key = entry.data[CONF_API_KEY]

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return MATCH_ALL

    async def _async_handle_message(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
    ) -> ConversationResult:
        """Send request to Jarvis Router."""

        device_id = getattr(user_input, "device_id", None)
        area_id = None
        area_name = None

        if device_id:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get(device_id)
            if device and device.area_id:
                area_id = device.area_id
                area_registry = ar.async_get(self.hass)
                area = area_registry.async_get_area(area_id)
                if area:
                    area_name = area.name

        _LOGGER.debug(
            "Jarvis resolved origin: device_id=%r area_id=%r area_name=%r",
            device_id,
            area_id,
            area_name,
        )

        session = async_get_clientsession(self.hass)

        try:
            async with session.post(
                f"{self._url}/route",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "text": user_input.text,
                    "origin_area": area_name,
                    "origin_satellite": getattr(user_input, "satellite_id", None),
                    "conversation_id": user_input.conversation_id,
                    "user_context": getattr(user_input.context, "user_id", None),
                    "origin": "home_assistant",
                    "request_id": uuid.uuid4().hex,
                },
                timeout=aiohttp.ClientTimeout(total=90),
            ) as response:

                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(
                        f"Jarvis Router returned "
                        f"HTTP {response.status}: {body}"
                    )

                data = await response.json()
                if not isinstance(data, dict):
                    raise RuntimeError('Malformed router response')

        except Exception as err:
            speech = (
                "Sorry, the Jarvis router is unavailable."
            )

            chat_log.async_add_assistant_content_without_tools(
                AssistantContent(
                    agent_id=user_input.agent_id,
                    content=speech,
                )
            )

            result = intent.IntentResponse(
                language=user_input.language
            )
            result.async_set_speech(speech)
            result.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, speech)

            return conversation.ConversationResult(
                conversation_id=user_input.conversation_id,
                response=result,
                continue_conversation=False,
            )

        speech = data.get("speech")

        if not isinstance(speech, str) or not speech.strip():
            speech = "Sorry, I didn't receive a response."

        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(
                agent_id=user_input.agent_id,
                content=speech,
            )
        )

        result = intent.IntentResponse(
            language=user_input.language
        )
        result.async_set_speech(speech)

        if data.get('domain') == 'nutrition':
            status=data.get('operation_status')
            if status in ('unavailable','invalid_response','reconciliation_required','unknown'):
                result.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, speech)
            elif status == 'read':
                result.response_type=intent.IntentResponseType.QUERY_ANSWER

        return conversation.ConversationResult(
            conversation_id=user_input.conversation_id,
            response=result,
            continue_conversation=data.get('continue_conversation') is True,
        )
