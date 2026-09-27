from app.adapters.homeassistant import ha_client

HOME_MODE_ENTITY = "input_select.home_security_status"

async def build_home_context() -> dict:
    state = await ha_client.get_state_optional(HOME_MODE_ENTITY)
    return {"home_mode": state.get("state") if state else None}
