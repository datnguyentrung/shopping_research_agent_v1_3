import httpx
import tempfile
from fastapi import HTTPException


# ==========================================
# HELPER: TẢI ẢNH TỪ URL (Shopee, Tiki)
# ==========================================
async def download_image_from_url(url: str, suffix=".jpg") -> str:
    """Tải ảnh từ URL về file tạm vì Vision Agent và Gradio cần đọc file vật lý."""

    # 1. Thêm Header giả lập trình duyệt thật để không bị tường lửa Shopee/Tiki chặn
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # 2. Set timeout lên 30 giây (thay vì 5s mặc định)
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Tạo file tạm và lưu bytes vào
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(response.content)
                return temp_file.name

    except httpx.TimeoutException:
        # Bắt lỗi timeout và báo về cho Frontend biết thay vì sập server (Lỗi 500)
        raise HTTPException(status_code=408, detail="Quá thời gian tải ảnh sản phẩm từ link. Vui lòng thử lại!")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể tải ảnh sản phẩm: {str(e)}")