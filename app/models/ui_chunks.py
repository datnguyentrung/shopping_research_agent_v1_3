"""
UI Chunks models - Updated version
"""

from typing import Optional, Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from typing import Literal, Union


class MessageChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    type: Literal["message"] = "message"
    content: str


class A2UIChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    type: Literal["a2ui"] = "a2ui"
    a2ui: dict[str, Any]


class DoneChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    type: Literal["done"] = "done"


class ErrorChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    type: Literal["error"] = "error"
    error: str


ChatStreamChunk = Union[MessageChunk, A2UIChunk, DoneChunk, ErrorChunk]


class HiddenEventRequest(BaseModel):
    action: str = Field(..., min_length=1)
    payload: Any = None


class ChatRequest(BaseModel):
    message: str = ""
    sessionId: str | None = None
    hidden_events: HiddenEventRequest | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "ChatRequest":
        if not self.message.strip() and self.hidden_events is None:
            raise ValueError("Either message or hidden_events is required")
        return self


class SearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1)
    category_filter: str | None = None
