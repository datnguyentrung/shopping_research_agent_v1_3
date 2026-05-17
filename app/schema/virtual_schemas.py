from uuid import UUID

from pydantic import  ConfigDict
from pydantic.alias_generators import to_camel

from app.entities.virtual_try_on import VirtualTryOnStatus
from app.schema.conversation_schemas import Time

class VirtualTryOnSchema(Time):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, from_attributes=True)

    id: UUID
    product_path: str
    status: VirtualTryOnStatus
    result_base64: str | None
    error: str | None