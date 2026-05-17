import uuid
from sqlalchemy import Column, String, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255))
    avatar_url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    # THÊM MỚI: Relationship cho VirtualTryOn
    virtual_try_ons = relationship("VirtualTryOn", back_populates="user", cascade="all, delete-orphan")