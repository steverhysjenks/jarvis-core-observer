from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NutritionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    action: Literal["log_food", "update_entry", "delete_entry"] = "log_food"
    food_id: UUID | None = None
    variant_id: UUID | None = None
    quantity: float | None = Field(default=None, gt=0, le=100000)
    unit: Literal["g", "ml", "serving", "slice", "packet"] | None = None
    pack_weight_g: float | None = Field(default=None, gt=0, le=100000)
    meal: Literal["breakfast", "lunch", "evening meal", "snack", "dinner"] | None = None
    consumed_at: datetime | None = None
    entry_id: UUID | None = None
    entry_date: date | None = None


class VoiceRequest(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=500,
    )

    area: str | None = None
    satellite: str | None = None
    listener: str | None = None
    request_id: str | None = Field(default=None, min_length=1, max_length=100)
    nutrition: NutritionSelection | None = None
    nutrition_confirmation: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
