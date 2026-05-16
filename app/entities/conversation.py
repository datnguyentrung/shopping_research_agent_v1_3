import uuid
from sqlalchemy import Column, String, DateTime, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Conversation(Base):
    __tablename__ = 'conversations'

    # Có thể dùng string session_id của bạn hoặc chuyển sang UUID chuẩn
    id = Column(String(255), primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'),
                     nullable=True)  # Có thể null nếu user chưa đăng nhập
    title = Column(String(255), default='Cuộc hội thoại mua sắm')

    # Giữ lại cột này để lưu trạng thái mua sắm (nhưng KHÔNG LƯU chat_history ở đây nữa)
    state_blob = Column(JSONB, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    # Index
    __table_args__ = (
        Index('idx_conversations_user_id', 'user_id'),
        # Bạn có thể phẩy và thêm nhiều index khác ở đây nếu muốn
    )