import base64

import os

from app.services import redis_service
from app.services.lite_llm.garment_analyzer_service import generate_dynamic_garment_des
from app.services.virtual_try_on.idm_vton_service import process_idm_vton_with_fallback
from app.services.virtual_try_on.ootd_service import process_ootd_virtual_try_on
from app.services.virtual_try_on.vto_ws_manager import vto_ws_manager
from app.utils.time_to_live_utils import random_one_week
import logging

logger = logging.getLogger(__name__)


# ==========================================
# BACKGROUND TASK: XỬ LÝ IDM-VTON NGẦM
# ==========================================
async def run_vto_background_task(request_id: str, person_path: str, garment_path: str, is_garment_temp: bool, product_name: str):
    """Hàm này chạy ngầm, không làm nghẽn API response của User."""
    try:
        # 1. Đảm bảo đã await để lấy chuỗi text chuẩn
        dynamic_prompt, category = await generate_dynamic_garment_des(garment_path, product_name)
        print(f"Generated Prompt: {dynamic_prompt} | Category: {category}")

        # ĐIỀU HƯỚNG MÔ HÌNH (ROUTING)
        if category == "Upper-body":
            logger.info(f"[{request_id}] Định tuyến tới IDM-VTON (Chuyên áo)")
            temp_result_path = await process_idm_vton_with_fallback(person_path, garment_path, dynamic_prompt)
        else:
            logger.info(f"[{request_id}] Định tuyến tới OOTDiffusion (Chuyên quần/váy) với category: {category}")
            # Truyền chính xác category (Lower-body / Dress) cho OOTD
            temp_result_path = await process_ootd_virtual_try_on(person_path, garment_path, category)

        # 2. Xử lý RAM / Base64
        if temp_result_path and os.path.exists(temp_result_path):
            with open(temp_result_path, "rb") as img_file:
                image_bytes = img_file.read()

            # Xóa file kết quả tạm
            os.remove(temp_result_path)

            # Chuyển thành dạng Data URI để Frontend dùng được như một cái link URL
            base64_encoded = base64.b64encode(image_bytes).decode('utf-8')
            result_data_uri = f"data:image/jpeg;base64,{base64_encoded}"

            # 3. Lấy dữ liệu cũ từ Redis
            old_data = await redis_service.get_vto_request(request_id) or {}

            # 4. Cập nhật trạng thái thành công
            old_data["status"] = "completed"
            old_data["result_url"] = result_data_uri  # Trả thẳng chuỗi base64 thay vì URL Fal.ai

            await redis_service.set_vto_request(request_id, old_data, ttl=random_one_week())
            print(f"[✅ Hoàn tất] Đã lưu kết quả cho request: {request_id}")

            # 5. Bắn qua WebSocket
            await vto_ws_manager.send_vto_result(request_id, old_data)

    except Exception as e:
        error_msg = str(e)
        print(f"[❌ LỖI BACKGROUND TASK] Request {request_id} thất bại: {error_msg}")

        old_data = await redis_service.get_vto_request(request_id) or {}
        old_data["status"] = "error"
        old_data["error"] = error_msg

        await redis_service.set_vto_request(request_id, old_data, ttl=random_one_week())
        await vto_ws_manager.send_vto_result(request_id, old_data)

    finally:
        # DỌN DẸP RÁC: Xóa các file ảnh đầu vào để giải phóng bộ nhớ
        if os.path.exists(person_path):
            os.remove(person_path)
        if is_garment_temp and os.path.exists(garment_path):
            os.remove(garment_path)