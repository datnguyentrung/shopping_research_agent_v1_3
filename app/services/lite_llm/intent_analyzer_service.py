from google import genai
from google.genai import types

from app.utils.load_instruction_from_file import load_instruction_from_file
from app.utils.request_model_service import _build_user_contents
from app.utils.fallback_service import generate_with_fallback_async, _safe_json_loads


async def analyze_user_intent(user_message: str) -> dict:
    """
    LLM tổng phân tích ý định của người dùng và điều hướng.
    """
    system_instruction = load_instruction_from_file("prompts/intent_analyzer.md")

    contents = _build_user_contents(user_message)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.1,  # Nhiệt độ thấp để phân luồng chính xác
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.OBJECT,
            properties={
                "intent": genai.types.Schema(
                    type=genai.types.Type.STRING,
                    enum=["start_new_search", "general_chat"],
                    description="Ý định của người dùng."
                ),
                "keyword": genai.types.Schema(
                    type=genai.types.Type.STRING,
                    description="Từ khóa sản phẩm (vd: 'áo khoác nam', 'giày thể thao'). Bỏ trống nếu không phải tìm kiếm."
                ),
                "reply_text": genai.types.Schema(
                    type=genai.types.Type.STRING,
                    description="Câu trả lời thân thiện. Bỏ trống nếu là start_new_search."
                )
            },
            required=["intent"]
        )
    )

    try:
        json_string = await generate_with_fallback_async(contents=contents, config=config)
        return _safe_json_loads(json_string,
                                {"intent": "general_chat", "reply_text": "Xin lỗi, mình chưa hiểu ý bạn lắm."})
    except Exception as e:
        print(f"[Error] LLM Phân luồng thất bại: {e}")
        return {"intent": "general_chat",
                "reply_text": "Hệ thống đang quá tải một chút. Bạn muốn tìm mua sản phẩm gì nhỉ?"}