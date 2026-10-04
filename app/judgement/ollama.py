import json

import httpx

from app.config import settings


class OllamaError(Exception):
    pass


async def chat_json(
    *,
    system_prompt: str,
    payload: dict,
    temperature: float = 0.1,
) -> dict:
    """
    Ask the configured local model for JSON.

    Returned data remains untrusted. Domain callers must
    validate it against their own strict schema.
    """

    request = {
        "model": settings.judgement_model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    payload,
                    separators=(",", ":"),
                ),
            },
        ],
        "options": {
            "temperature": temperature,
        },
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/chat",
                json=request,
            )
            response.raise_for_status()
            result = response.json()

        content = result["message"]["content"]
        parsed = json.loads(content)

        if not isinstance(parsed, dict):
            raise OllamaError(
                "Model returned non-object JSON"
            )

        return parsed

    except (
        httpx.HTTPError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ) as exc:
        raise OllamaError(
            "Local model request failed"
        ) from exc
