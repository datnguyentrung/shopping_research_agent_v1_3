import asyncio
from gradio_client import Client, handle_file

from app.core.config import settings

# ==========================================
# KHAI BÁO SERVER DỰ PHÒNG CHO OOTD
# ==========================================
OOTD_FALLBACK_SPACES = [
    "levihsu/OOTDiffusion",  # Bản gốc
    "Nymbo/OOTDiffusion",  # Các bản duplicate cộng đồng
    "Kvikontent/OOTDiffusion",
    "eduardo4547/OOTDiffusion",
]

HF_TOKEN = settings.HF_TOKEN

# ==========================================
# HÀM XỬ LÝ API OOTDIFFUSION
# ==========================================
async def process_ootd_virtual_try_on(person_img_path: str, garment_img_path: str, category: str = "Lower-body"):
    """
    Gọi API OOTDiffusion.
    :param category: Bắt buộc chọn 1 trong 3: "Upper-body", "Lower-body", "Dress"
    """
    for space_id in OOTD_FALLBACK_SPACES:
        try:
            print(f"\n[🔄 Đang thử gọi API OOTD] Space: {space_id}...")
            client = Client(space_id, token=HF_TOKEN)

            # Tham số dành riêng cho mô hình Full-body (DC Model) của OOTDiffusion
            # Có thể xử lý được cả quần (Lower-body) và váy (Dress)
            predict_kwargs = {
                "vton_img": handle_file(person_img_path),  # Ảnh người mẫu
                "garm_img": handle_file(garment_img_path),  # Ảnh quần áo
                "category": category,  # Phân loại đồ
                "n_samples": 1,  # Số lượng ảnh sinh ra
                "n_steps": 20,  # Số bước khử nhiễu (20 là chuẩn)
                "image_scale": 2.0,  # Mức độ bám sát ảnh gốc (1.0 - 3.0)
                "seed": -1,  # -1 là random
                "api_name": "/process_dc"  # Endpoint gọi model Full-body
            }

            # Giải nén tham số và gọi API bất đồng bộ
            result = await asyncio.to_thread(client.predict, **predict_kwargs)

            print(f"[✅ Thành công] Đã xử lý xong bằng Space: {space_id}")

            # OOTDiffusion thường trả về một mảng chứa file ảnh đầu tiên hoặc tuple
            # Tuỳ thuộc vào output của Space, thường result[0] là ảnh kết quả
            if isinstance(result, tuple) or isinstance(result, list):
                return result[0]
            return result

        except Exception as e:
            print(f"[⚠️ Thất bại] Space {space_id} gặp lỗi: {str(e)}")
            print(">>> Đang tự động chuyển sang Server dự phòng tiếp theo...")
            continue  # Bỏ qua lỗi và thử Space tiếp theo

    raise Exception("Toàn bộ server OOTD dự phòng đều đã quá tải hoặc không khả dụng!")