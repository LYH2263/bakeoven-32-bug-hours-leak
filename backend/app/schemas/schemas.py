from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class ProductOut(BaseModel):
    id: int
    name: str
    ferment_min: int
    bake_min: int
    model_config = {"from_attributes": True}


class OvenOut(BaseModel):
    id: int
    label: str
    capacity_note: str
    open_min: int
    close_min: int
    model_config = {"from_attributes": True}


class OvenHoursUpdate(BaseModel):
    open_min: int = Field(ge=0, le=24 * 60)
    close_min: int = Field(ge=0, le=24 * 60)

    @model_validator(mode="after")
    def _door_must_be_half_open(self) -> "OvenHoursUpdate":
        # 半开营业 [open_min, close_min)：开门必须严格早于打烊
        if self.open_min >= self.close_min:
            raise ValueError("开门时间必须早于打烊时间（打烊分钟本身不可排）")
        return self


class BatchOut(BaseModel):
    id: int
    product_id: int
    oven_id: int
    code: str
    start_min: int
    status: str
    product_name: str | None = None
    oven_label: str | None = None
    ferment_end: int | None = None
    bake_end: int | None = None
    model_config = {"from_attributes": True}


class BatchCreate(BaseModel):
    product_id: int
    oven_id: int
    start_min: int = Field(ge=0, le=24 * 60 - 1)
    code: str | None = None


class GanttBlock(BaseModel):
    batch_id: int
    code: str
    oven_id: int
    oven_label: str
    phase: str
    start_min: int
    end_min: int


class ConflictOut(BaseModel):
    id: int
    batch_code: str
    oven_id: int
    detail: str
    created_at: datetime
    model_config = {"from_attributes": True}


class WindowOut(BaseModel):
    oven_id: int
    oven_label: str
    start_min: int
    end_min: int
    duration_min: int
