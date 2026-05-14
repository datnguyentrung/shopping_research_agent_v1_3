import json

from cachetools import TTLCache
from app.memory.adk_state import ShoppingState
from app.repositories.chat_session_repository import ChatSessionRepository
from app.services import redis_service
from app.services.database import SessionLocal

# Quản lý session đơn giản bằng Dictionary (Memory).
# Tương lai nếu MB Bank yêu cầu scale, bạn chỉ cần thay TTLCache bằng Redis ở đây.
SESSION_TTL = 86400

def _backup_state_to_db_sync(session_id: str, state: ShoppingState):
    """
    Hàm đồng bộ chạy ngầm: Khởi tạo kết nối DB, đẩy JSONB xuống và đóng kết nối.
    """
    db = SessionLocal()
    try:
        repo = ChatSessionRepository(db)
        repo.upsert_session(session_id, state)
    except Exception as e:
        print(f"[❌ LỖI DB] Không thể backup session {session_id} xuống PostgreSQL: {e}")
    finally:
        db.close()

async def get_or_create_state(session_id: str) -> ShoppingState:
    """
        Truy xuất State từ Redis. Nếu chưa có, khởi tạo State mặc định.
        """
    redis_key = f"shopping_state:{session_id}"

    # Đọc dữ liệu từ Redis
    raw_data = await redis_service.client.get(redis_key)

    if raw_data:
        # Nếu đã có session, parse JSON trả về dictionary
        return json.loads(raw_data)
    else:
        # Khởi tạo state mặc định cho một user mới theo đúng chuẩn ADK
        initial_state: ShoppingState = {
            "session_id": session_id,
            "phase": "INIT",
            "original_keyword": "",
            "vi_keyword": "",
            "current_message": "",
            "hidden_action": None,
            "hidden_payload": None,
            "category_map": {},
            "current_category_id": "",  # String
            "leaf_category_name": "",
            "attributes": [],
            "current_attribute_id": 0,  # Integer
            "answers": [],
            "raw_products": [],
            "pending_products": [],
            "whitelist": [],
            "blacklist": [],
            "preferred_keywords": [],
            "chat_history": [],
        }
        # Lưu state mới tạo vào Redis với TTL
        await save_state(session_id, initial_state)
        return initial_state

async def save_state(session_id: str, state: ShoppingState):
    """
    Cập nhật State mới nhất vào Redis.
    Hàm này sẽ được gọi ở cuối mỗi turn hội thoại.
    """
    redis_key = f"shopping_state:{session_id}"
    await redis_service.client.setex(
        redis_key,
        SESSION_TTL,
        json.dumps(state, ensure_ascii=False)
    )

async def clear_state(session_id: str):
    """
    Xóa State khỏi Redis khi luồng mua sắm kết thúc.
    Tương lai: Tại đây sẽ trigger luồng đẩy dữ liệu xuống Supabase (Cold Storage).
    """
    redis_key = f"shopping_state:{session_id}"
    await redis_service.client.delete(redis_key)