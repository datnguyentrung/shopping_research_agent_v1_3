from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from datetime import datetime
from uuid import UUID

class Time(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, from_attributes=True)
    created_at: datetime | None
    updated_at: datetime | None


class ConversationResponse(Time):
    # from_attributes=True là BẮT BUỘC để Pydantic tự động map từ SQLAlchemy model
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, from_attributes=True)

    id: str
    user_id: UUID | None  # Đổi thành UUID | None vì DB của bạn định nghĩa thế
    title: str