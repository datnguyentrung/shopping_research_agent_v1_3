import json

from cachetools import TTLCache
from app.memory.adk_state import ShoppingState
from app.services import redis_service

# Quản lý session đơn giản bằng Dictionary (Memory).
# Tương lai nếu MB Bank yêu cầu scale, bạn chỉ cần thay TTLCache bằng Redis ở đây.
SESSION_TTL = 3600


async def get_or_create_state(session_id: str) -> ShoppingState:
    raw_data = await redis_service.client.get(f"chat:session:{session_id}")

    if raw_data:
        return json.loads(raw_data)

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
    }

    await save_state(session_id, initial_state)
    return initial_state

async def save_state(session_id: str, state: ShoppingState):
    await redis_service.client.setex(
        f"chat:session:{session_id}",
        SESSION_TTL,
        json.dumps(state)
    )

def clear_state(session_id: str):
    """Gọi hàm này khi user hoàn tất luồng để dọn rác RAM ngay lập tức"""
    redis_service.client.delete(f"chat:session:{session_id}")
