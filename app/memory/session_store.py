import copy
import json
from typing import Optional

from app.memory.adk_state import ShoppingState
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services import redis_service
from app.services.database import SessionLocal
from app.utils.time_to_live_utils import random_one_day, random_one_week

def _backup_state_to_db_sync(session_id: str, state: ShoppingState, user_id: Optional[str] = None):
    """
    Hàm đồng bộ chạy ngầm.
    Chỉ mở kết nối và lưu xuống DB NẾU ĐÓ LÀ NGƯỜI DÙNG THỰC TẾ.
    """
    effective_user_id = user_id or state.get("user_id")

    # NẾU LÀ GUEST -> NGẮT LUỒNG NGAY LẬP TỨC, KHÔNG ĐỤNG ĐẾN DB
    if not effective_user_id:
        return

    db = SessionLocal()
    try:
        conversation_repo = ConversationRepository(db)
        message_repo = MessageRepository(db)

        state_to_save = copy.deepcopy(state)
        chat_history = state_to_save.pop("chat_history", [])

        conversation_repo.upsert_conversation(
            session_id=session_id,
            state_blob=state_to_save,
            user_id=effective_user_id,
        )
        message_repo.sync_messages(session_id, chat_history)
    except Exception as e:
        print(f"[❌ LỖI DB] Không thể backup session {session_id} xuống PostgreSQL: {e}")
        db.rollback()
    finally:
        db.close()


async def get_or_create_state(session_id: str, user_id: Optional[str] = None) -> ShoppingState:
    """
    Truy xuất State từ Redis.
    - Khách vãng lai: Chỉ tìm trên Redis. Nếu mất -> Reset.
    - User thực tế: Tìm Redis. Nếu mất -> Khôi phục từ DB.
    """
    redis_key = f"shopping_state:{session_id}"

    # 1. Đọc dữ liệu từ Redis (Cho cả Guest và User)
    raw_data = await redis_service.client.get(redis_key)
    if raw_data:
        state = json.loads(raw_data)

        # [TÍNH NĂNG HAY]: Nếu khách vãng lai đang chat mà bấm Đăng nhập
        # Nâng cấp họ thành User thực tế và cập nhật lại TTL
        if user_id and not state.get("user_id"):
            state["user_id"] = user_id
            await save_state(session_id, state)

        return state

    # 2. Cache Miss: CHỈ tìm trong Database nếu họ LÀ USER THỰC TẾ
    if user_id:
        db = SessionLocal()
        try:
            conversation_repo = ConversationRepository(db)
            message_repo = MessageRepository(db)

            saved_state = conversation_repo.get_conversation_state(session_id)

            if saved_state:
                db_messages = message_repo.get_messages_by_conversation(session_id)
                chat_history = [{"role": msg.sender, "content": msg.content} for msg in db_messages]

                restored_state = saved_state
                restored_state["chat_history"] = chat_history
                restored_state["user_id"] = user_id

                await save_state(session_id, restored_state)
                return restored_state

        except Exception as e:
            print(f"[❌ LỖI KHÔI PHỤC DB] Không thể khôi phục state {session_id}: {e}")
        finally:
            db.close()  # Đảm bảo không bị Leak Connection

    # 3. Không có ở cả Redis lẫn DB (Hoặc là Guest bị hết hạn Cache): Khởi tạo mới
    initial_state: ShoppingState = {
        "session_id": session_id,
        "user_id": user_id,
        "phase": "INIT",
        "original_keyword": "",
        "vi_keyword": "",
        "current_message": "",
        "hidden_action": None,
        "hidden_payload": None,
        "category_map": {},
        "current_category_id": "",
        "leaf_category_name": "",
        "attributes": [],
        "current_attribute_id": 0,
        "answers": [],
        "raw_products": [],
        "pending_products": [],
        "whitelist": [],
        "blacklist": [],
        "preferred_keywords": [],
        "chat_history": [],
    }
    await save_state(session_id, initial_state)
    return initial_state


async def save_state(session_id: str, state: ShoppingState):
    """
    Cập nhật State mới nhất vào Redis với TTL linh hoạt dựa trên loại User.
    """
    redis_key = f"shopping_state:{session_id}"

    # Kiểm tra xem có phải là Guest hay không để set TTL phù hợp
    ttl = random_one_day() if state.get("user_id") else random_one_week()

    await redis_service.client.setex(
        redis_key,
        ttl,
        json.dumps(state, ensure_ascii=False)
    )


async def clear_state(session_id: str):
    redis_key = f"shopping_state:{session_id}"
    await redis_service.client.delete(redis_key)