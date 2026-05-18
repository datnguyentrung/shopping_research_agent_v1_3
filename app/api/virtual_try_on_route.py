import os
import tempfile
import uuid
from typing import List

from fastapi import APIRouter, Form, UploadFile, File, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import current_user

from app.core.security import get_db_session
from app.entities.virtual_try_on import VirtualTryOnStatus
from app.repositories.virtual_try_on_repository import VirtualTryOnRepository
from app.schema.virtual_schemas import VirtualTryOnSchema
from app.services import redis_service
from app.services.virtual_try_on.vto_service import run_vto_background_task
from app.utils.download_image_from_url import download_image_from_url
from app.utils.time_to_live_utils import random_one_week
from app.core.security import get_current_user_optional
router = APIRouter()

# ==========================================
# MAIN ROUTE: KÍCH HOẠT VTO
# ==========================================
@router.post("/fire")
async def fire_vto_request(
        background_tasks: BackgroundTasks,  # Thêm BackgroundTasks
        person_image_file: UploadFile = File(...),
        product_file_path: str = Form(...),
        product_url: str = Form(...),
        product_name: str = Form(...),
        db: Session = Depends(get_db_session),
        current_user_id = Depends(get_current_user_optional)
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

    # ==========================================
    # BƯỚC MỚI: LƯU VÀO DATABASE TRƯỚC
    # ==========================================
    repo = VirtualTryOnRepository(db)
    new_try_on_record = repo.create_try_on(
        user_id=current_user_id,
        product_path=product_url,
        status=VirtualTryOnStatus.PENDING
    )

    # 3. Lưu trạng thái 'pending' vào Redis (DÙNG HÀM HASH MỚI)
    await redis_service.init_vto_hash(
        request_id=request_id,
        ttl=random_one_week()
    )

    # 4. Giao việc cho Background Task chạy ngầm
    background_tasks.add_task(
        run_vto_background_task,
        request_id=request_id,
        try_on_id=new_try_on_record.id,  # Truyền ID của DB xuống Task
        person_path=person_path,
        garment_path=garment_path,
        is_garment_temp=is_garment_temp,
        product_name=product_name
    )

    # 5. Trả ID về cho Frontend ngay lập tức
    print(f"🔗 Đã kích hoạt VTO ngầm với ID: {request_id}")
    return {
        "request_id": request_id,
        "try_on_id": new_try_on_record.id
    }


@router.get("/vto-history", response_model=List[VirtualTryOnSchema])
async def get_by_user_id(
        db: Session = Depends(get_db_session),
        current_user_id=Depends(get_current_user_optional)
):
    repo = VirtualTryOnRepository(db)
    list_virtual_try_ons = repo.get_by_user_id(current_user_id)

    # Không cần list comprehension [Schema.from_orm(x) for x in list],
    # FastAPI tự động map nhờ from_attributes=True trong Schema
    return list_virtual_try_ons
