from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ha_url: str
    ha_token: str
    ollama_url: str = "http://127.0.0.1:11434"
    judgement_model: str = "qwen3:4b-instruct-2507-q4_K_M-8k"
    observer_mode: Literal["shadow", "live"] = "shadow"
    observer_interval_seconds: int = 60
    global_announcement_cooldown_seconds: int = 600
    model_config = SettingsConfigDict(extra="ignore")

settings = Settings()
