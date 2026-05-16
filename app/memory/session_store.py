import asyncio
import copy
import json
from typing import Optional

from sqlalchemy import UUID

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

        # 🌟 THÊM ĐÚNG DÒNG NÀY ĐỂ KHỬ TOÀN BỘ UUID ẨN NẤP TRONG STATE
        # Nó sẽ biến đổi toàn bộ object dạng UUID thành chuỗi string thuần túy trước khi SQLAlchemy sờ vào
        state_to_save = json.loads(json.dumps(state_to_save, default=str, ensure_ascii=False))

        # ==========================================
        # TRÍCH XUẤT TITLE TỪ STATE
        # ==========================================
        keyword = state_to_save.get("vi_keyword") or state_to_save.get("original_keyword")
        conversation_title = f"Tìm kiếm: {keyword}" if keyword else "Cuộc hội thoại mua sắm"

        conversation_repo.upsert_conversation(
            session_id=session_id,
            state_blob=state_to_save,
            user_id=effective_user_id,
            title=conversation_title,
        )
        message_repo.sync_messages(session_id, chat_history)
    except Exception as e:
        print(f"[❌ LỖI DB] Không thể backup session {session_id} xuống PostgreSQL: {e}")
        db.rollback()
    finally:
        db.close()

async def get_or_create_state(session_id: str, user_id: Optional[UUID] = None) -> ShoppingState:
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
        # 🌟 SỬA TẠI ĐÂY: Ép kiểu sang chuỗi str để đồng bộ thuần JSON
        if user_id and not state.get("user_id"):
            state["user_id"] = str(user_id)
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
                # 🌟 SỬA TẠI ĐÂY: Đảm bảo user_id khôi phục từ DB nạp vào state cũng là dạng chuỗi text
                restored_state["user_id"] = str(user_id)

                await save_state(session_id, restored_state)
                return restored_state

        except Exception as e:
            print(f"[❌ LỖI KHÔI PHỤC DB] Không thể khôi phục state {session_id}: {e}")
        finally:
            db.close()  # Đảm bảo không bị Leak Connection

    # 3. Không có ở cả Redis lẫn DB: Khởi tạo mới
    initial_state: ShoppingState = {
        "session_id": session_id,
        # 🌟 SỬA TẠI ĐÂY: Ép kiểu UUID sang chuỗi ngay khi tạo state mới ban đầu
        "user_id": str(user_id) if user_id else None,
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
        # 🌟 GIỮ NGUYÊN BẢO HIỂM: Thêm default=str để phòng chống tất cả các loại object lạ khác độc hại
        json.dumps(state, ensure_ascii=False, default=str)
    )

    # 2. Kích hoạt luồng chạy ngầm backup xuống PostgreSQL
    asyncio.create_task(
        asyncio.to_thread(_backup_state_to_db_sync, session_id, state)
    )


async def clear_state(session_id: str):
    redis_key = f"shopping_state:{session_id}"
    await redis_service.client.delete(redis_key)