import json
from typing import AsyncGenerator
from google.genai import types

from app.core.llm_models import MODELS_TO_TRY
from app.utils.request_model_service import get_client

# Danh sách các mã lỗi liên quan đến quá tải mạng/hết Quota để kích hoạt Fallback
RETRY_ERRORS = ["503", "UNAVAILABLE", "529", "429", "RESOURCE_EXHAUSTED"]


def _safe_json_loads(json_str: str, default_val: dict) -> dict:
    """Helper: Parse JSON an toàn, cắt bỏ các markdown code block thừa nếu có."""
    try:
        cleaned_str = json_str.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_str)
    except Exception as e:
        print(f"[Warning] Parse JSON thất bại: {e}")
        return default_val


async def generate_with_fallback_async(
        contents: list,
        config: types.GenerateContentConfig,
) -> str:
    """
    Sử dụng cho các tác vụ trả về 1 cục Text hoặc JSON (Không stream).
    """
    client = get_client()

    for model in MODELS_TO_TRY:
        try:
            # Lưu ý: Dùng generate_content thay vì stream cho output dạng JSON
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response.text

        except Exception as e:
            error_msg = str(e)
            print(f"-> [Chi tiết lỗi của {model}]: {error_msg}")

            if any(err in error_msg for err in RETRY_ERRORS):
                print(f"[Warning] Model '{model}' lỗi (Quá tải/Hết Quota). Đang chuyển sang model tiếp theo...")
                continue

            print(f"[Error] Lỗi nghiêm trọng từ '{model}': {error_msg}")
            raise e

    raise RuntimeError("Tất cả các model trong MODELS_TO_TRY đều thất bại hoặc hết Quota.")


async def generate_stream_with_fallback_async(
        contents: list,
        config: types.GenerateContentConfig,
) -> AsyncGenerator[str, None]:
    """
    Sử dụng cho các tác vụ cần stream Text ra UI (ví dụ: Final Summary).
    """
    client = get_client()

    for model in MODELS_TO_TRY:
        try:
            stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if text := getattr(chunk, "text", None):
                    yield text
            return  # Trả về thành công -> Thoát generator

        except Exception as e:
            error_msg = str(e)
            print(f"-> [Chi tiết lỗi của {model}]: {error_msg}")

            if any(err in error_msg for err in RETRY_ERRORS):
                print(f"[Warning] Model '{model}' lỗi (Quá tải/Hết Quota). Đang chuyển sang model tiếp theo...")
                continue

            print(f"[Error] Lỗi nghiêm trọng từ '{model}': {error_msg}")
            raise e

    # Nếu chạy hết vòng lặp mà vẫn lỗi
    yield "\n\n*Hệ thống đang quá tải, không thể xử lý yêu cầu lúc này. Bạn vui lòng thử lại sau nhé!*"