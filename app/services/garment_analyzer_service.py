from typing import Optional

from google import genai
from google.genai.types import Part, ThinkingLevel, GenerateContentConfig, Content, ThinkingConfig

# Import module tái sử dụng vừa tạo
from app.utils.fallback_service import generate_with_fallback_async, _safe_json_loads


async def generate_garment_properties(think_level: ThinkingLevel, prompts: str, properties: dict, image_bytes: Optional[bytes] = None) -> dict:
    """
    Trích xuất thuộc tính quần áo bằng JSON Schema kết hợp cơ chế Fallback.
    """
    # Chỉ thêm Part ảnh nếu thực sự có ảnh truyền vào
    parts = [Part.from_text(text=prompts)]
    if image_bytes:
        parts.append(Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

    contents = [Content(role="user", parts=parts)]

    config = GenerateContentConfig(
        thinking_config=ThinkingConfig(thinking_level=think_level),
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.OBJECT,
            properties=properties,
        ),
    )

    try:
        json_string = await generate_with_fallback_async(contents=contents, config=config)
        # Trả về DICT (không phải string)
        return _safe_json_loads(json_string, default_val={})
    except Exception as e:
        print(f"[Error] generate_garment_properties thất bại: {e}")
        return {}