import httpx
import tempfile

# ==========================================
# HELPER: TẢI ẢNH TỪ URL (Shopee, Tiki)
# ==========================================
async def download_image_from_url(url: str, suffix=".jpg") -> str:
    """Tải ảnh từ URL về file tạm vì Vision Agent và Gradio cần đọc file vật lý."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()

        # Tạo file tạm và lưu bytes vào
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(response.content)
            return temp_file.name