from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .flags import FLAG_NAMES


FlagModel = dict[str, Optional[bool]]


class CreateItemRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=200)
    label: Optional[str] = Field(None, max_length=200)
    user_flags: FlagModel = Field(default_factory=dict)


class UpdateFlagsRequest(BaseModel):
    user_flags: FlagModel
