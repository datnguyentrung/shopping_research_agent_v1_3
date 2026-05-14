from sqlalchemy.orm import Session, InstrumentedAttribute
from sqlalchemy.dialects.postgresql import insert

from app.entities.chat_session import ChatSession
from app.memory.adk_state import ShoppingState
from app.repositories.base import BaseRepository


class ChatSessionRepository(BaseRepository[ChatSession]):
    """Repository quản lý lưu trữ State hội thoại xuống Database (Warm Storage)."""

    def __init__(self, db: Session):
        super().__init__(db, ChatSession)

    def upsert_session(self, session_id: str, state_blob: ShoppingState) -> None:
        """
        Lưu hoặc cập nhật state vào PostgreSQL dưới dạng JSONB.
        Sử dụng cơ chế ON CONFLICT (Upsert) để tối ưu hiệu suất.
        """
        # Tạo câu lệnh Insert
        stmt = insert(ChatSession).values(
            session_id=session_id,
            state_blob=state_blob
        )

        # Thêm điều kiện: Nếu trùng khóa chính (session_id) thì Update cột state_blob
        stmt = stmt.on_conflict_do_update(
            index_elements=['session_id'],
            set_={'state_blob': stmt.excluded.state_blob}
        )

        # Thực thi và lưu thay đổi
        self.db.execute(stmt)
        self.db.commit()

    def get_session_state(self, session_id: str) -> InstrumentedAttribute | None:
        """
        Kéo state từ Database lên lại (dùng khi Redis bị mất dữ liệu).
        """
        record = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if record:
            return record.state_blob
        return None