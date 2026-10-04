from pydantic import BaseModel, Field


class VoiceRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=500,
    )

    area: str | None = None
    satellite: str | None = None
    listener: str | None = None
