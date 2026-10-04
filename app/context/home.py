from datetime import datetime, timezone

from app.adapters.homeassistant import ha_client


HOME_MODE_ENTITY = "input_select.home_security_status"


async def build_home_context() -> dict:
    home_mode = await ha_client.get_state(HOME_MODE_ENTITY)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "home": {
            "mode": home_mode["state"],
            "mode_last_changed": home_mode["last_changed"],
        },
    }
