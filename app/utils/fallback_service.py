import json
import logging
from typing import AsyncGenerator
from google.genai import types
import base64
from app.core.llm_models import MODELS_TO_TRY
from app.utils.request_model_service import get_client, get_client_cloud

# Danh sách các mã lỗi liên quan đến quá tải mạng/hết Quota để kích hoạt Fallback
RETRY_ERRORS = ["503", "UNAVAILABLE", "529", "429", "RESOURCE_EXHAUSTED"]
logger = logging.getLogger(__name__)

def _safe_json_loads(json_str: str, default_val: dict) -> dict:
    """Helper: Parse JSON an toàn, cắt bỏ các markdown code block thừa nếu có."""
    try:
        cleaned_str = json_str.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_str)
    except Exception as e:
        print(f"[Warning] Parse JSON thất bại: {e}")
        return default_val

def _save_binary_file(file_name, data):
    f = open(file_name, "wb")
    f.write(data)
    f.close()
    print(f"File saved to to: {file_name}")


async def generate_image_with_fallback_async(
        contents: list,
        config: types.GenerateContentConfig,
        vto_instruction: str,  # Truyền thêm prompt thô để dùng cho Imagen
        garment_path: str  # Truyền thêm path để Imagen đọc nếu cần
) -> str | None:
    client = get_client_cloud()

    # Tách danh sách model theo kiến trúc API của Google
    gemini_models = [
        "gemini-3.1-flash-image-preview",
        "gemini-3-pro-image-preview",
        "gemini-2.5-flash-image",
    ]
    imagen_models = [
        "imagen-4.0-generate-001",
        "imagen-4.0-ultra-generate-001",
        "imagen-4.0-fast-generate-001",
    ]

    # 1. CHẠY VÒNG LẶP CÁC MODEL GEMINI (Dùng generate_content_stream)
    for model in gemini_models:
        try:
            logger.info(f"🎨 [Gemini Ecosystem] Đang gọi model: {model}")
            image_bytes = bytearray()
            mime_type = "image/jpeg"

            stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )

            async for chunk in stream:
                if chunk.parts:
                    part = chunk.parts[0]
                    if part.inline_data and part.inline_data.data:
                        image_bytes.extend(part.inline_data.data)
                        if part.inline_data.mime_type:
                            mime_type = part.inline_data.mime_type

            if image_bytes:
                logger.info(f"✅ [Gemini Thành công] Đã sinh ảnh bằng: {model}")
                base64_str = base64.b64encode(image_bytes).decode('utf-8')
                return f"data:{mime_type};base64,{base64_str}"

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"⚠️ [Lỗi Model {model}]: {error_msg}")
            continue

    # 2. FALLBACK SANG CÁC MODEL IMAGEN (Dùng cấu trúc generate_images đặc thù)
    for model in imagen_models:
        try:
            logger.info(f"🎨 [Imagen Ecosystem] Đang gọi model chuyên dụng: {model}")

            # Đọc file ảnh trang phục làm thẻ hướng dẫn ảnh đầu vào cho Imagen (nếu cần)
            with open(garment_path, "rb") as f:
                raw_bytes = f.read()

            # Chú ý: Cấu trúc API cho Imagen trong SDK mới sử dụng generate_images
            result = await client.aio.models.generate_images(
                model=model,
                prompt=vto_instruction,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    aspect_ratio="1:1",
                    # Nếu model hỗ trợ ảnh tham chiếu (Image-to-Image / Editing)
                    person_generation="DONT_ALLOW"
                )
            )

            if result.generated_images:
                generated_img = result.generated_images[0]
                # Lấy trực tiếp byte dữ liệu từ ảnh được trả về
                img_base64 = base64.b64encode(generated_img.image.image_bytes).decode('utf-8')
                logger.info(f"✅ [Imagen Thành công] Đã sinh ảnh bằng: {model}")
                return f"data:image/jpeg;base64,{img_base64}"

        except Exception as e:
            logger.warning(f"⚠️ [Lỗi Model {model}]: {str(e)}")
            continue

    return None

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