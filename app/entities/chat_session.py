from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class ChatSession(Base):
    __tablename__ = 'chat_session'

    # Dùng luôn session_id làm khóa chính để truy vấn O(1)
    session_id = Column(String(255), primary_key=True, index=True)

    # Lưu toàn bộ state (bao gồm whitelist, blacklist, answers...) vào cột này
    state_blob = Column(JSONB, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ChatSession(session_id='{self.session_id}')>"