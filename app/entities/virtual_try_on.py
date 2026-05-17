import uuid
from enum import Enum  # Import thư viện enum chuẩn của Python
from sqlalchemy import Column, String, DateTime, func, ForeignKey, Text, Index
from sqlalchemy import Enum as SQLEnum  # Đổi tên Enum của SQLAlchemy để tránh trùng lặp
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


# 1. Kế thừa từ enum.Enum của Python
class VirtualTryOnStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"


class VirtualTryOn(Base):
    __tablename__ = "virtual_try_on"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    product_path = Column(String(255), nullable=False)

    # 2. Sử dụng SQLEnum và truyền class enum của Python vào
    status = Column(SQLEnum(VirtualTryOnStatus), default=VirtualTryOnStatus.PENDING)

    # 3. Đổi tên và dùng kiểu Text cho chuỗi Base64 khổng lồ, cho phép NULL
    result_base64 = Column(Text, nullable=True)

    # 4. Lỗi cũng có thể NULL nếu quá trình thành công
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 5. Sửa lại tên biến back_populates cho đúng ngữ cảnh
    user = relationship("User", back_populates="virtual_try_ons")

    __table_args__ = (
        Index('idx_virtual_try_on_user_id', 'user_id'),
    )