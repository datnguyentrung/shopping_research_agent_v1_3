from typing import cast, Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.entities.conversation import Conversation
from app.memory.adk_state import ShoppingState
from app.repositories.base import BaseRepository

class ConversationRepository(BaseRepository[Conversation]):
    """Repository quản lý Meta data và State hội thoại (Warm Storage)."""

    def __init__(self, db: Session):
        super().__init__(db, Conversation)

    def upsert_conversation(self, session_id: str, state_blob: ShoppingState, user_id: Optional[UUID] = None) -> None:
        """
        Lưu hoặc cập nhật state vào PostgreSQL dưới dạng JSONB.
        user_id: UUID của user đã đăng nhập, None nếu guest.
        """
        # Tạo câu lệnh Insert
        stmt = insert(Conversation).values(
            id=session_id,
            user_id=user_id,  # None nếu guest
            state_blob=state_blob
        )

        # Upsert: Trùng session_id (Khóa chính) thì update state_blob
        stmt = stmt.on_conflict_do_update(
            index_elements=['id'],
            set_={
                'state_blob': stmt.excluded.state_blob,
                'updated_at': func.now()
            }
        )

        self.db.execute(stmt)
        self.db.commit()

    def get_conversation_state(self, session_id: str) -> ShoppingState | None:
        record = self.db.query(Conversation).filter(Conversation.id == session_id).first()
        if record:
            return cast(ShoppingState, cast(Any, record.state_blob))
        return None