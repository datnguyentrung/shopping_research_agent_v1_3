import asyncio
from typing import Any, Dict, List

from cachetools import TTLCache

# Quản lý session đơn giản bằng Dictionary (Memory).
SESSION_STORE = TTLCache(maxsize=1000, ttl=3600)


def get_or_create_session(session_id: str) -> dict:
    if session_id not in SESSION_STORE:
        # Khởi tạo state mặc định cho một user mới
        SESSION_STORE[session_id] = {
            "phase": "INIT",
            "attributes": [],
            "answers": [],
            "raw_products": [],
            "pending_products": [],
            "whitelist": [],
            "blacklist": [],
            "search_task": None,
            # Fields cho Task 3 & 4: Feedback va Routing
            "preferred_keywords": [],
            "banned_keywords_history": [],
            "original_keyword": "",
            "augmented_keywords": [],
            "category_name": "",
        }
    return SESSION_STORE[session_id]


def clear_session(session_id: str):
    """Gọi hàm này khi user hoàn tất luồng để dọn rác RAM ngay lập tức"""
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]