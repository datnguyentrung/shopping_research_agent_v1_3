import asyncio
import base64

from google.genai.types import ThinkingLevel, Schema, Type
from gradio_client import Client, handle_file
import os

from app.services import redis_service
from app.services.garment_analyzer_service import generate_garment_properties
from app.services.vto_ws_manager import vto_ws_manager
from app.utils.load_instruction_from_file import load_instruction_from_file
from app.utils.time_to_live_utils import random_one_week

# ==========================================
# CHIẾN THUẬT 1: FALLBACK (DỰ PHÒNG CHÉO)
# ==========================================
# Khai báo danh sách các Space IDM-VTON (Sắp xếp từ ưu tiên cao xuống thấp)
FALLBACK_SPACES = [
    "hysts-duplicates/IDM-VTON",
    "husam2003/IDM-VTON",
    "FcoTry/IDM-VTON",
    "yisol/IDM-VTON"  # Bản gốc để cuối vì hay bị quá tải nhất
]

# ==========================================
# 2. HÀM LẮP RÁP PROMPT (Đã chuyển sang Async & Nạp ảnh)
# ==========================================
async def generate_dynamic_garment_des(garment_image_path: str) -> str:
    """Gọi Vision LLM để đọc ảnh và tự động generate prompt chuẩn."""
    system_instruction = load_instruction_from_file("prompts/vision_agent.md")

    # 1. Đọc file ảnh để AI có cái mà nhìn
    try:
        with open(garment_image_path, "rb") as f:
            img_bytes = f.read()
    except Exception as e:
        print(f"[Error] Không thể đọc ảnh sản phẩm: {e}")
        return "A basic clothing item, clear details"

    # 2. Gọi Vision Agent (Dùng await và truyền img_bytes)
    attrs_dict = await generate_garment_properties(
        think_level=ThinkingLevel.LOW,
        prompts=system_instruction,
        properties={
            "fit": Schema(type=Type.STRING),
            "color_and_fabric": Schema(type=Type.STRING),
            "garment_type": Schema(type=Type.STRING),
            "neckline_and_sleeves": Schema(type=Type.STRING),
            "details": Schema(type=Type.STRING),
        },
        image_bytes=img_bytes # Đã thêm ảnh vào đây!
    )

    # 3. Lắp ráp theo Công Thức Vàng (Lấy thẳng từ Dict, KHÔNG dùng json.loads)
    if not attrs_dict:
        return "A basic clothing item, clear details"

    base_prompt = f"A {attrs_dict.get('fit', '')} {attrs_dict.get('color_and_fabric', '')} {attrs_dict.get('garment_type', '')}, featuring {attrs_dict.get('neckline_and_sleeves', '')}"

    details = attrs_dict.get('details', '')
    if details:
        return f"{base_prompt}, with {details.strip()}."

    return f"{base_prompt}."


async def process_virtual_try_on_with_fallback(person_img_path, garment_img_path):
    """
    Hàm này sẽ đi qua từng Space trong danh sách.
    Nếu gọi thành công, lập tức trả về file.
    Nếu thất bại (do mạng, do timeout, do sập), tự động nhảy sang Space tiếp theo.
    """
    for space_id in FALLBACK_SPACES:
        try:
            print(f"\n[🔄 Đang thử gọi API] Space: {space_id}...")
            client = Client(space_id)

            # 1. Đảm bảo đã await để lấy chuỗi text chuẩn
            dynamic_prompt = await generate_dynamic_garment_des(garment_img_path)
            print(f"Generated Prompt for IDM-VTON: {dynamic_prompt}")

            # 2. Gom toàn bộ tham số vào 1 dictionary để tránh xung đột từ khóa 'dict' của Python
            predict_kwargs = {
                "dict": {"background": handle_file(person_img_path), "layers": [], "composite": None},
                "garm_img": handle_file(garment_img_path),
                "garment_des": dynamic_prompt,  # Lúc này chắc chắn là String
                "is_checked": True,
                "denoise_steps": 30,
                "seed": 42,
                "api_name": "/tryon"
            }

            # 3. Giải nén tham số bằng dấu **
            result = await asyncio.to_thread(client.predict, **predict_kwargs)

            print(f"[✅ Thành công] Đã xử lý xong bằng Space: {space_id}")
            return result[0]  # Trả về đường dẫn file tạm do Gradio tạo

        except Exception as e:
            print(f"[⚠️ Thất bại] Space {space_id} gặp lỗi: {str(e)}")
            print(">>> Đang tự động chuyển sang Server dự phòng tiếp theo...")
            continue  # Bỏ qua lỗi và tiếp tục vòng lặp

    # Nếu chạy hết vòng lặp mà không thành công cái nào
    raise Exception("Toàn bộ server dự phòng đều đã quá tải hoặc không khả dụng!")

# ==========================================
# BACKGROUND TASK: XỬ LÝ IDM-VTON NGẦM
# ==========================================
async def run_vto_background_task(request_id: str, person_path: str, garment_path: str, is_garment_temp: bool):
    """Hàm này chạy ngầm, không làm nghẽn API response của User."""
    try:
        # 1. Gọi hàm fallback Gradio của bạn
        temp_result_path = await process_virtual_try_on_with_fallback(person_path, garment_path)

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