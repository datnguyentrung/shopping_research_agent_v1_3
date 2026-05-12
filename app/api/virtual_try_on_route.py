import fal_client
from fastapi import APIRouter, Form, UploadFile, File

from app.services import redis_service
from app.utils.fal_ai_util import submit
from app.utils.time_to_live_utils import random_one_week

router = APIRouter()


@router.post("/fire")
async def fire_vto_request(
        # Lưu ý: Nếu user truyền URL thì dùng Form/Query, UploadFile để upload file vật lý
        person_image_file: UploadFile = File(...),
        product_file_path: str = Form(...),
        category: str = Form(...)
):
    # Bước 1: Đọc file người dùng đẩy lên thành mảng bytes
    file_bytes = await person_image_file.read()

    # Bước 2: Ném thẳng file bytes này lên kho lưu trữ tạm của Fal.ai
    # Fal sẽ trả về một cái link URL dạng: https://v3.fal.media/...
    uploaded_person_url = await fal_client.upload_async(
        file_bytes,
        content_type=person_image_file.content_type
    )

    print(f"🔗 Đã upload ảnh người dùng lên Fal: {uploaded_person_url}")

    # 1. Gọi hàm util (Đã sửa để có return)
    handler = await submit(
        person_image=uploaded_person_url,
        product_file_path=product_file_path,
        category=category
    )

    request_id = handler.request_id

    # 2. Lưu trạng thái 'pending' vào Redis (Đã thêm ttl)
    await redis_service.set_vto_request(
        request_id=request_id,
        data={"status": "pending", "result_url": None, "error": None},
        ttl=random_one_week()
    )

    return {"request_id": request_id}


@router.post("/webhook")
async def vto_webhook(payload: dict):
    # Lấy thông tin từ payload do Fal.ai bắn về
    request_id = payload.get("request_id")

    # Fal.ai có thể trả về lỗi thay vì ảnh
    error_msg = payload.get("error")
    result_url = payload.get("payload", {}).get("image", {}).get("url")

    if not request_id:
        return {"status": "ignored"}

    # Lấy dữ liệu cũ từ Redis ra
    old_data = await redis_service.get_vto_request(request_id)
    if not old_data:
        return {"status": "not_found"}

    # NẾU CÓ LỖI TỪ FAL.AI
    if error_msg:
        old_data["status"] = "error"
        old_data["error"] = str(error_msg)
        print(f"❌ Request {request_id} bị lỗi: {error_msg}")

    # NẾU THÀNH CÔNG
    elif result_url:
        old_data["status"] = "completed"
        old_data["result_url"] = result_url
        print(f"✅ Đã cập nhật kết quả cho request: {request_id}")

    # Ghi đè lại vào Redis với trạng thái mới
    await redis_service.set_vto_request(request_id, old_data, ttl=random_one_week())

    return {"status": "ok"}