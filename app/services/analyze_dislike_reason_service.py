from google import genai
from google.genai import types

from app.utils.load_instruction_from_file import load_instruction_from_file
from app.utils.request_model_service import _build_user_contents
from app.utils.fallback_service import generate_with_fallback_async, _safe_json_loads

async def analyze_dislike_reason(reason: str) -> dict:
    system_instruction = load_instruction_from_file("prompts/analyze_dislike_reason.md")
    contents = _build_user_contents(reason)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.OBJECT,
            properties={
                "banned_keywords": genai.types.Schema(
                    type=genai.types.Type.ARRAY,
                    items=genai.types.Schema(type=genai.types.Type.STRING)
                ),
                "preferred_keywords": genai.types.Schema(
                    type=genai.types.Type.ARRAY,
                    items=genai.types.Schema(type=genai.types.Type.STRING)
                ),
            },
            required=["banned_keywords", "preferred_keywords"],
        )
    )

    try:
        json_string = await generate_with_fallback_async(contents=contents, config=config)
        return _safe_json_loads(json_string, {"banned_keywords": [], "preferred_keywords": []})
    except Exception as e:
        print(f"Quá trình phân tích lý do không thích thất bại: {e}")
        return {"banned_keywords": [], "preferred_keywords": []}