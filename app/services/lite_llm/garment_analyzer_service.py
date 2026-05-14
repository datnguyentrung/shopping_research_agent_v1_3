from typing import Optional

from google import genai
from google.genai.types import Part, ThinkingLevel, GenerateContentConfig, Content, ThinkingConfig, Schema, Type

# Import module tái sử dụng vừa tạo
from app.utils.fallback_service import generate_with_fallback_async, _safe_json_loads
from app.utils.load_instruction_from_file import load_instruction_from_file


async def generate_garment_properties(
        think_level: ThinkingLevel,
        prompts: str,
        properties: dict,
        image_bytes: Optional[bytes] = None) -> dict:
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


# ==========================================
# 2. HÀM LẮP RÁP PROMPT (Đã chuyển sang Async & Nạp ảnh)
# ==========================================
async def generate_dynamic_garment_des(garment_image_path: str, product_name: str) -> str | tuple[str, str]:
    """Gọi Vision LLM để đọc ảnh và tự động generate prompt chuẩn."""
    system_instruction = load_instruction_from_file("prompts/vision_agent.md")

    # ==========================================
    # DYNAMIC PROMPTING: Bơm tên sản phẩm vào System Prompt
    # ==========================================
    if product_name:
        system_instruction = system_instruction.replace("{{product_name}}", product_name)
    else:
        system_instruction = system_instruction.replace("{{product_name}}", "Unknown Product")

    # 1. Đọc file ảnh để AI có cái mà nhìn
    try:
        with open(garment_image_path, "rb") as f:
            img_bytes = f.read()
    except Exception as e:
        print(f"[Error] Không thể đọc ảnh sản phẩm: {e}")
        return "A basic clothing item, clear details", "Upper-body"  # Mặc định an toàn

    # 2. Gọi Vision Agent
    attrs_dict = await generate_garment_properties(
        think_level=ThinkingLevel.LOW,
        prompts=system_instruction,
        properties={
            "category": Schema(type=Type.STRING),
            "fit": Schema(type=Type.STRING),
            "color_and_fabric": Schema(type=Type.STRING),
            "garment_type": Schema(type=Type.STRING),
            "structure": Schema(type=Type.STRING),
            "details": Schema(type=Type.STRING),
        },
        image_bytes=img_bytes,
    )

    # 3. Lắp ráp theo Công Thức Vàng
    if not attrs_dict:
        return "A basic clothing item, clear details", "Upper-body"

    base_prompt = f"A {attrs_dict.get('fit', '')} {attrs_dict.get('color_and_fabric', '')} {attrs_dict.get('garment_type', '')}, featuring {attrs_dict.get('structure', '')}"

    details = attrs_dict.get('details', '')
    if details:
        prompt_result = f"{base_prompt}, with {details.strip()}."
    else:
        prompt_result = f"{base_prompt}."

    # Trả về cả prompt để đưa cho IDM-VTON và category để quyết định luồng
    return prompt_result, attrs_dict.get('category', 'Upper-body')