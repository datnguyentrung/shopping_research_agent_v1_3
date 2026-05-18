from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session

from app.entities.virtual_try_on import VirtualTryOn, VirtualTryOnStatus
from app.repositories.base import BaseRepository, ModelType


class VirtualTryOnRepository(BaseRepository[VirtualTryOn]):
    """Repository quản lý các bản ghi Virtual Try-On."""

    def __init__(self, db: Session):
        super().__init__(db, VirtualTryOn)

    def create_try_on(
            self,
            user_id: UUID,  # Ép kiểu UUID cho chuẩn
            product_path: str,
            status: VirtualTryOnStatus = VirtualTryOnStatus.PENDING,
            result_base64: Optional[str] = None,
            error: Optional[str] = None
    ) -> VirtualTryOn:

        # Khởi tạo đối tượng
        db_obj = VirtualTryOn(
            user_id=user_id,
            product_path=product_path,
            status=status,
            result_base64=result_base64,
            error=error
        )

        # Thêm vào session và lưu xuống database
        self.db.add(db_obj)
        self.db.commit()

        # Refresh để lấy lại ID và các trường auto-generated (như created_at)
        self.db.refresh(db_obj)

        return db_obj

    # Thêm hàm update trạng thái để dùng ở Service
    def update_status(
            self,
            try_on_id: UUID,
            status: VirtualTryOnStatus,
            result_base64: Optional[str] = None,
            error: Optional[str] = None
    ) -> Optional[ModelType]:
        db_obj = self.get(try_on_id)
        if db_obj:
            db_obj.status = status
            if result_base64:
                db_obj.result_base64 = result_base64
            if error:
                db_obj.error = error
            self.db.commit()
            self.db.refresh(db_obj)
        return db_obj

    def get_by_user_id(
            self,
            user_id: UUID,
    ) -> List[VirtualTryOn]:  # Bỏ chữ 'type' đi
        return self.db.query(self.model).filter(self.model.user_id == user_id).all()