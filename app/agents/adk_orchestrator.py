import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.memory.session_store import get_or_create_state, save_state
from app.models.ui_chunks import ChatRequest, MessageChunk, A2UIChunk

# Import các Nodes của bạn
from app.core.shopping_flow.handlers.initial import adk_initial_node
from app.core.shopping_flow.handlers.category_drilldown import adk_category_drilldown_node
from app.core.shopping_flow.handlers.questionnaire import adk_questionnaire_node
from app.core.shopping_flow.handlers.product_swipe import adk_product_swipe_node
from app.services.lite_llm.intent_analyzer_service import analyze_user_intent


async def run_shopping_orchestrator(payload: ChatRequest, user_id: Optional[UUID] = None):
    session_id = getattr(payload, "sessionId", None)
    is_new_session = False

    if not session_id:
        session_id = str(uuid.uuid4())
        is_new_session = True

    # Load State
    state = await get_or_create_state(session_id, user_id)
    state["user_id"] = user_id
    state["current_message"] = (payload.message or "").strip()
    state["hidden_action"] = payload.hidden_events.action if payload.hidden_events else None
    state["hidden_payload"] = payload.hidden_events.payload if payload.hidden_events else None

    # ==========================================
    # TRÍCH XUẤT TITLE TỪ STATE
    # Lấy vi_keyword hoặc original_keyword. Nếu chưa có gì thì để mặc định.
    # ==========================================
    keyword = state.get("vi_keyword") or state.get("original_keyword")
    conversation_title = f"Tìm kiếm: {keyword}" if keyword else "Cuộc hội thoại mua sắm"

    if is_new_session:
        yield A2UIChunk(a2ui={"type": "a2ui_session_init",
                              "data": {
                                  "sessionId": session_id,
                                  "title": conversation_title,
                                  "createdAt": datetime.now(timezone.utc).isoformat(),
                              }})

    current_phase = state.get("phase", "INIT")
    node_runner = None

    # ==========================================
    # LUỒNG 1: XỬ LÝ SỰ KIỆN UI CỦA FRONTEND (FSM)
    # ==========================================
    if state["hidden_action"]:
        if state["hidden_action"] == "PRODUCT_FEEDBACK" or current_phase == "PRODUCT_SWIPE":
            node_runner = adk_product_swipe_node(state)
        elif state["hidden_action"] in ["SUBMIT_SURVEY", "SKIP_SURVEY"]:
            if current_phase == "CATEGORY_DRILLDOWN":
                node_runner = adk_category_drilldown_node(state)
            elif current_phase == "QUESTIONNAIRE":
                node_runner = adk_questionnaire_node(state)

    # ==========================================
    # LUỒNG 2: LLM TỔNG XỬ LÝ NGÔN NGỮ TỰ NHIÊN
    # ==========================================
    elif state["current_message"]:
        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": "🧠 Đang phân tích yêu cầu của bạn...", "progressPercent": 1}})

        # Gọi Master LLM để đọc ý định
        intent_data = await analyze_user_intent(state["current_message"])

        if intent_data.get("intent") == "start_new_search":
            # Lấy keyword LLM bóc tách được để làm sạch câu từ
            clean_keyword = intent_data.get("keyword") or state["current_message"]

            state["original_keyword"] = clean_keyword
            # Cập nhật lại current_message để các Node sau (initial.py) dùng từ khóa sạch
            state["current_message"] = clean_keyword

            state["phase"] = "INIT"
            node_runner = adk_initial_node(state)

        else:
            # LLM đánh giá đây chỉ là tán gẫu/chào hỏi (general_chat)
            reply = intent_data.get("reply_text", "Chào bạn! Mình có thể giúp gì cho bạn hôm nay?")
            yield MessageChunk(content=reply)

            # Lưu State và thoát (Không kích hoạt FSM Node nào cả)
            await save_state(session_id, state)
            return

    else:
        yield MessageChunk(content="Mình chưa nhận được thông tin, bạn hãy thử lại nhé.")
        return

    # ==========================================
    # KÍCH HOẠT NODE ĐÃ ĐƯỢC CHỌN (NẾU CÓ)
    # ==========================================
    if node_runner:
        async for output in node_runner:
            # Lắng nghe 'state_update' để cập nhật DB
            if isinstance(output, dict) and "state_update" in output:
                state.update(output["state_update"])
                await save_state(session_id, state)
            else:
                yield output