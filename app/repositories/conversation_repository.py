from typing import cast, Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.entities.conversation import Conversation
from app.memory.adk_state import ShoppingState
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Repository quản lý Meta data và State hội thoại (Warm Storage)."""

    def __init__(self, db: Session):
        super().__init__(db, Conversation)

    def upsert_conversation(self, session_id: str, state_blob: ShoppingState, title: str,
                            user_id: Optional[UUID] = None) -> None:
        """
        Lưu hoặc cập nhật state vào PostgreSQL dưới dạng JSONB.
        user_id: UUID của user đã đăng nhập, None nếu guest.
        """
        stmt = insert(Conversation).values(
            id=session_id,
            user_id=user_id,
            title=title,
            state_blob=state_blob
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=['id'],
            set_={
                'state_blob': stmt.excluded.state_blob,
                'updated_at': func.now(),
                'title': stmt.excluded.title,
            }
        )

        self.db.execute(stmt)
        self.db.commit()

    def get_conversation_state(self, session_id: str) -> ShoppingState | None:
        # Cập nhật luôn hàm này sang cú pháp 2.0 cho đồng bộ
        stmt = select(Conversation).where(Conversation.id == session_id)
        record = self.db.scalars(stmt).first()

        if record:
            return cast(ShoppingState, cast(Any, record.state_blob))
        return None

    def get_conversations_by_user_id(
            self,
            user_id: UUID,
            limit: int,
            offset: int,
            sort_by: str,
            sort_dir: str,
            search: Optional[str]
    ) -> tuple[list[Conversation], int]:
        """Truy vấn danh sách conversation có phân trang, search và sort."""

        # 1. Khởi tạo Base Statement cho Data và Count
        stmt = select(Conversation).where(Conversation.user_id == user_id)
        count_stmt = select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)

        # 2. Xử lý Search theo Title (nếu có)
        if search:
            search_filter = Conversation.title.ilike(f"%{search}%")
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        # 3. Đếm tổng số bản ghi (Dùng db.scalar cho câu lệnh count)
        total_records = self.db.scalar(count_stmt) or 0

        # 4. Xử lý Sort
        sort_column = getattr(Conversation, sort_by, Conversation.created_at)

        if sort_dir.lower() == "asc":
            stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(sort_column.desc())

        # 5. Phân trang
        stmt = stmt.offset(offset).limit(limit)

        # 6. Lấy dữ liệu (Dùng db.execute().scalars().all())
        items = self.db.execute(stmt).scalars().all()

        return list(items), total_records