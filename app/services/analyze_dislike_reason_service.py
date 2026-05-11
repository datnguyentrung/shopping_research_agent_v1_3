
from google.genai import types

from google import genai

from app.core.llm_models import MODELS_TO_TRY
from app.utils.load_instruction_from_file import load_instruction_from_file
from app.utils.request_model_service import _build_user_contents, generate_with_fallback_async, get_client, _safe_json_loads


async def analyze_dislike_reason(reason: str) -> dict:
    """
    Nhan ly do khach hang khong thich mot san pham va tra ve dict gom:
    - banned_keywords: tu khoa can loai bo
    - preferred_keywords: tu khoa mong muon thay the
    """
    system_instruction = load_instruction_from_file("prompts/analyze_dislike_reason.md")

    contents = _build_user_contents(reason)

    generate_content_config = types.GenerateContentConfig(
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
        response = await generate_with_fallback_async(
            client_instance=get_client(),
            models=MODELS_TO_TRY,
            contents=contents,
            config=generate_content_config,
        )

        return _safe_json_loads(response, {"banned_keywords": [], "preferred_keywords": []})

    except Exception as e:
        print(f"Qua trinh phan tich ly do khong thich that bai: {e}")
        return {"banned_keywords": [], "preferred_keywords": []}