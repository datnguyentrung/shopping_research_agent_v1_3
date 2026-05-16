import uuid
from sqlalchemy import Column, String, DateTime, func, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Message(Base):
    __tablename__ = 'messages'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(String(255), ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    sender = Column(String(50)) # 'user' hoặc 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    conversation = relationship("Conversation", back_populates="messages")

    # Index
    __table_args__ = (
        Index('idx_messages_conversation_id', 'conversation_id'),
    )