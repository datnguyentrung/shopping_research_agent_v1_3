import uuid
from typing import Optional
from uuid import UUID

from app.memory.session_store import get_or_create_state, save_state
from app.models.ui_chunks import ChatRequest, MessageChunk

# Import các Nodes bạn vừa bọc ở Bước 2
from app.core.shopping_flow.handlers.initial import adk_initial_node
from app.core.shopping_flow.handlers.category_drilldown import adk_category_drilldown_node
from app.core.shopping_flow.handlers.questionnaire import adk_questionnaire_node
from app.core.shopping_flow.handlers.product_swipe import adk_product_swipe_node
from app.models.ui_chunks import A2UIChunk

_GREETING_PREFIXES = (
    "xin chào", "chào", "hello", "hi", "hey",
    "good morning", "good afternoon", "good evening",
)


def _is_greeting_or_smalltalk(text: str) -> bool:
    normalized = " ".join((text or "").strip().lower().split())
    if not normalized:
        return False

    return any(
        normalized == prefix
        or normalized.startswith(f"{prefix} ")
        or normalized.startswith(f"{prefix},")
        for prefix in _GREETING_PREFIXES
    )


# ----------------------------

async def run_shopping_orchestrator(payload: ChatRequest, user_id: Optional[UUID] = None):
    session_id = getattr(payload, "sessionId", None)
    is_new_session = False

    if not session_id:
        session_id = str(uuid.uuid4())
        is_new_session = True

    # Load state hiện tại từ Memory (có thể tích hợp Redis sau nếu cần)
    state = await get_or_create_state(session_id, user_id = None)

    # Gắn user_id vào state (đăng nhập) hoặc None (guest)
    state["user_id"] = user_id

    # Bơm input mới vào State
    state["current_message"] = (payload.message or "").strip()
    state["hidden_action"] = payload.hidden_events.action if payload.hidden_events else None
    state["hidden_payload"] = payload.hidden_events.payload if payload.hidden_events else None

    if is_new_session:
        yield A2UIChunk(a2ui={"type": "a2ui_session_init", "data": {"sessionId": session_id}})

    # CHÀO HỎI (Ngoại lệ nhỏ xử lý nhanh không cần vào State Machine)
    # -> ĐÃ XÓA DÒNG IMPORT CŨ BỊ LỖI Ở ĐÂY <-
    if not state.get("original_keyword") and _is_greeting_or_smalltalk(state["current_message"]):
        yield MessageChunk(content="Chào bạn! Mình có thể giúp tìm sản phẩm phù hợp. Bạn muốn mua gì nào?")
        return

    # THE ROUTER: Orchestrator tự động quyết định Node nào sẽ chạy dựa trên Phase
    current_phase = state.get("phase", "INIT")

    node_runner = None
    if state["hidden_action"] == "PRODUCT_FEEDBACK" or current_phase == "PRODUCT_SWIPE":
        node_runner = adk_product_swipe_node(state)
    elif state["hidden_action"] in ["SUBMIT_SURVEY", "SKIP_SURVEY"]:
        if current_phase == "CATEGORY_DRILLDOWN":
            node_runner = adk_category_drilldown_node(state)
        elif current_phase == "QUESTIONNAIRE":
            node_runner = adk_questionnaire_node(state)
    elif current_phase == "INIT":
        node_runner = adk_initial_node(state)
    else:
        yield MessageChunk(content="Mình chưa hiểu thao tác này, bạn thử lại nhé.")
        return

    # Lắng nghe Node chạy và stream về Frontend
    async for output in node_runner:
        # Nếu node trả về dict có key 'state_update', tức là nó muốn cập nhật State nội bộ (Không stream ra FE)
        if isinstance(output, dict) and "state_update" in output:
            # Update memory nội bộ (Ghi đè session)
            state.update(output["state_update"])

            await save_state(session_id, state)
        else:
            # Nếu là A2UIChunk hoặc MessageChunk thì stream ra Frontend cho user
            yield output
