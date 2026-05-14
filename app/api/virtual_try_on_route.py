import os
import tempfile
import uuid

from fastapi import APIRouter, Form, UploadFile, File, BackgroundTasks

from app.services import redis_service
from app.services.virtual_try_on.vto_service import run_vto_background_task
from app.utils.download_image_from_url import download_image_from_url
from app.utils.time_to_live_utils import random_one_week

router = APIRouter()

# ==========================================
# MAIN ROUTE: KÍCH HOẠT VTO
# ==========================================
@router.post("/fire")
async def fire_vto_request(
        background_tasks: BackgroundTasks,  # Thêm BackgroundTasks
        person_image_file: UploadFile = File(...),
        product_file_path: str = Form(...),
        product_name: str = Form(...),
):
    request_id = str(uuid.uuid4())  # Tự sinh ID vì không còn lấy từ Fal.ai nữa

    # 1. Lưu file ảnh người dùng (UploadFile) xuống ổ cứng tạm
    _, ext = os.path.splitext(person_image_file.filename)
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext or ".jpg") as temp_person:
        content = await person_image_file.read()
        temp_person.write(content)
        person_path = temp_person.name

    # 2. Xử lý đường dẫn áo (Nếu là Link web thì tải về, nếu là path ổ cứng thì giữ nguyên)
    is_garment_temp = False
    garment_path = product_file_path

    if product_file_path.startswith("http://") or product_file_path.startswith("https://"):
        garment_path = await download_image_from_url(product_file_path)
        is_garment_temp = True  # Đánh dấu để lát nữa dọn rác

    # 3. Lưu trạng thái 'pending' vào Redis ngay lập tức
    await redis_service.set_vto_request(
        request_id=request_id,
        data={"status": "pending", "result_url": None, "error": None},
        ttl=random_one_week()
    )

    # 4. Giao việc cho Background Task chạy ngầm
    background_tasks.add_task(
        run_vto_background_task,
        request_id=request_id,
        person_path=person_path,
        garment_path=garment_path,
        is_garment_temp=is_garment_temp,
        product_name=product_name
    )

    # 5. Trả ID về cho Frontend ngay lập tức
    print(f"🔗 Đã kích hoạt VTO ngầm với ID: {request_id}")
    return {"request_id": request_id}