from sqlalchemy.orm import Session

from app.entities.message import Message
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    """Repository quản lý chi tiết từng dòng tin nhắn."""

    def __init__(self, db: Session):
        super().__init__(db, Message)

    def sync_messages(self, session_id: str, messages_data: list) -> None:
        """
        Đồng bộ danh sách tin nhắn.
        Cách đơn giản cho Job chạy ngầm: Xóa cũ, Insert toàn bộ mới.
        """
        # Xóa history cũ của session này
        self.db.query(Message).filter(Message.conversation_id == session_id).delete()

        # Build danh sách objects
        new_messages = [
            Message(
                conversation_id=session_id,
                sender=msg.get("role", "user"),
                content=msg.get("content", "")
            )
            for msg in messages_data
        ]

        # Bulk insert cho tối ưu
        if new_messages:
            self.db.add_all(new_messages)

        self.db.commit()

    def get_messages_by_conversation(self, session_id: str):
        """Lấy toàn bộ tin nhắn của một session, sắp xếp theo thời gian tăng dần."""
        return self.db.query(Message)\
            .filter(Message.conversation_id == session_id)\
            .order_by(Message.created_at.asc())\
            .all()