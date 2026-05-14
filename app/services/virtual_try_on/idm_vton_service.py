import asyncio

from gradio_client import Client, handle_file

from app.core.config import settings


HF_TOKEN = settings.HF_TOKEN

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

async def process_idm_vton_with_fallback(person_img_path, garment_img_path, dynamic_prompt: str):
    """
    Hàm này sẽ đi qua từng Space trong danh sách.
    Nếu gọi thành công, lập tức trả về file.
    Nếu thất bại (do mạng, do timeout, do sập), tự động nhảy sang Space tiếp theo.
    """
    for space_id in FALLBACK_SPACES:
        try:
            print(f"\n[🔄 Đang thử gọi API] Space: {space_id}...")
            client = Client(space_id, token=HF_TOKEN)

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