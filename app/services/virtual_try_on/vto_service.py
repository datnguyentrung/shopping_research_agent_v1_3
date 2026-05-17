import os
import base64
import asyncio
import logging
from uuid import UUID

from openai import OpenAI

from app.entities.virtual_try_on import VirtualTryOnStatus
from app.repositories.virtual_try_on_repository import VirtualTryOnRepository
from app.services import redis_service
from app.services.database import SessionLocal
from app.services.virtual_try_on.vto_ws_manager import vto_ws_manager
from app.core.config import settings

# ---> THÊM IMPORT HÀM VISION AGENT CỦA BẠN VÀO ĐÂY <---
from app.services.lite_llm.garment_analyzer_service import generate_dynamic_garment_des

logger = logging.getLogger(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY,
)


def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')


# ==========================================
# BACKGROUND TASK: FLUX.2 KLEIN + VISION AGENT
# ==========================================
async def run_vto_background_task(
        request_id: str,
        try_on_id: UUID,
        person_path: str,
        garment_path: str,
        is_garment_temp: bool,
        product_name: str):
    try:
        logger.info(f"[{request_id}] Bắt đầu xử lý với FLUX.2 Klein 4B qua OpenRouter")

        # 1. GỌI VISION AGENT ĐỂ BÓC TÁCH CHI TIẾT (TÁI SỬ DỤNG LUỒNG CŨ)
        logger.info(f"[{request_id}] Đang phân tích thuộc tính trang phục...")
        # Giả sử bạn lấy được category từ hàm phân tích
        dynamic_prompt, category = await generate_dynamic_garment_des(garment_path, product_name)
        logger.info(f"[{request_id}] AI đã hiểu sản phẩm: {dynamic_prompt}")

        # 2. Chuyển đổi cả 2 ảnh sang định dạng Base64
        person_b64 = encode_image_to_base64(person_path)
        garment_b64 = encode_image_to_base64(garment_path)

        # 3. KẾT HỢP LỆNH GHÉP ĐỒ + MÔ TẢ TỪ VISION AGENT
        # Logic chỉ định vùng thay thế
        if category == "Upper-body":
            change_instruction = "Chỉ thay thế phần ÁO, tuyệt đối GIỮ NGUYÊN QUẦN và phụ kiện hiện có của người mẫu."
        elif category == "Lower-body":
            change_instruction = "Chỉ thay thế phần QUẦN/VÁY, tuyệt đối GIỮ NGUYÊN ÁO và phụ kiện hiện có của người mẫu."
        else:
            change_instruction = "Thay thế trang phục phù hợp."

        flux_instruction = (
            f"Bạn là một chuyên gia Virtual Try-On cao cấp. Nhiệm vụ: Mặc sản phẩm ở ảnh 2 cho người ở ảnh 1.\n"
            f"Yêu cầu nghiêm ngặt:\n"
            f"1. {change_instruction}\n"
            f"2. GIỮ NGUYÊN khuôn mặt, kiểu tóc, làn da, hình xăm (nếu có) và bối cảnh.\n"
            f"3. TUYỆT ĐỐI GIỮ NGUYÊN TỈ LỆ KHUNG HÌNH (ASPECT RATIO) và kích thước của người trong ảnh 1. Không bóp méo hay làm lùn người.\n"  # <-- Thêm dòng này
            f"4. Sản phẩm mới cần được render chính xác: '{dynamic_prompt}'.\n"
            f"5. Đảm bảo nếp gấp vải và bóng đổ tự nhiên trên cơ thể người mẫu."
        )

        prompt_content = [
            {
                "type": "text",
                "text": flux_instruction
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{person_b64}"}
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{garment_b64}"}
            }
        ]

        def call_openrouter():
            return client.chat.completions.create(
                model="black-forest-labs/flux.2-klein-4b",
                messages=[
                    {"role": "user", "content": prompt_content}
                ],
                extra_body={
                    "modalities": ["image"]
                }
            )

        # 4. Đẩy ra thread để không block API
        response = await asyncio.to_thread(call_openrouter)

        # 5. Trích xuất Base64 Data URI
        result_data_uri = None
        response_message = response.choices[0].message

        message_dict = response_message.model_dump()
        if "images" in message_dict and message_dict["images"]:
            result_data_uri = message_dict["images"][0].get('image_url', {}).get('url')
        elif getattr(response_message, 'images', None):
            result_data_uri = response_message.images[0]['image_url']['url']

        if not result_data_uri:
            raise ValueError("API OpenRouter trả về thành công nhưng không tìm thấy dữ liệu ảnh.")

        # ==========================================
        # 6. CẬP NHẬT DATABASE
        # ==========================================
        with SessionLocal() as db:
            repo = VirtualTryOnRepository(db)
            repo.update_status(
                try_on_id=try_on_id,
                status=VirtualTryOnStatus.COMPLETED,
                result_base64=result_data_uri
            )
        logger.info(f"[✅ Hoàn tất DB] Đã cập nhật database COMPLETED cho try_on_id: {try_on_id}")

        # ==========================================
        # 7. CẬP NHẬT REDIS VÀ BẮN WEBSOCKET
        # ==========================================
        # Update 1 chạm và nhận lại dict mới nhất
        updated_data = await redis_service.update_vto_hash(
            request_id=request_id,
            updates={
                "status": "completed",
                "result_url": result_data_uri
            }
        )

        logger.info(f"[✅ Redis] Đã cập nhật Hash Cache cho request: {request_id}")
        await vto_ws_manager.send_vto_result(request_id, updated_data)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[❌ LỖI BACKGROUND TASK] Request {request_id} thất bại: {error_msg}")

        # Cập nhật lỗi xuống DB
        try:
            with SessionLocal() as db:
                repo = VirtualTryOnRepository(db)
                repo.update_status(
                    try_on_id=try_on_id,
                    status=VirtualTryOnStatus.REJECTED,
                    error=error_msg
                )
        except Exception as db_err:
            logger.error(f"[❌ LỖI DATABASE] Không thể cập nhật lỗi cho DB: {db_err}")

            # Cập nhật lỗi lên Redis & Bắn WebSocket
        updated_data = await redis_service.update_vto_hash(
            request_id=request_id,
            updates={
                "status": "error",
                "error": error_msg
            }
        )
        await vto_ws_manager.send_vto_result(request_id, updated_data)

    finally:
        if os.path.exists(person_path):
            os.remove(person_path)
        if is_garment_temp and os.path.exists(garment_path):
            os.remove(garment_path)
