
from google.genai import types

from app.core.llm_models import MODELS_TO_TRY
from app.utils.load_instruction_from_file import load_instruction_from_file
from app.utils.request_model_service import _build_user_contents, get_client


async def generate_final_summary_stream(prompt: str):
    """
    Async generator: stream Markdown report using genai.Client with model fallback.
    Used by final_summary.py and adk_client.py (replaces ADK Runner).
    """
    system_instruction = load_instruction_from_file("prompts/interactive_agent.md")
    contents = _build_user_contents(prompt)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.HIGH,
        ),
        temperature=1,
    )

    for model in MODELS_TO_TRY:
        try:
            stream = await get_client().aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if text := getattr(chunk, "text", None):
                    yield text
            return  # success — exit generator

        except Exception as e:
            error_msg = str(e)

            # IN RA LỖI CHI TIẾT ĐỂ DEBUG
            print(f"-> [Chi tiết lỗi của {model}]: {error_msg}")

            if any(err in error_msg for err in ["503", "UNAVAILABLE", "529", "429", "RESOURCE_EXHAUSTED"]):
                print(f"[Warning] Model '{model}' loi (Qua tai/Het Quota). Dang chuyen sang model tiep theo...")
                continue
            print(f"[Error] Loi nghiem trong tu '{model}': {error_msg}")
            raise e

    # All models failed
    yield "\n\n*Hệ thống đang quá tải, không thể tạo báo cáo tóm tắt lúc này. Bạn vui lòng xem lại danh sách ở trên nhé!*"