import uuid

from app.memory.session_store import get_or_create_session
from app.models.ui_chunks import ChatRequest, MessageChunk

handle_initial_phase = None
handle_category_drilldown = None
handle_product_swipe = None
handle_questionnaire = None

_GREETING_PREFIXES = (
    "xin chào",
    "chào",
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
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


def _ensure_initial_handler_loaded() -> None:
    global handle_initial_phase

    if handle_initial_phase is None:
        from app.core.shopping_flow.handlers.initial import handle_initial_phase as _handle_initial_phase

        handle_initial_phase = _handle_initial_phase


def _ensure_category_drilldown_handler_loaded() -> None:
    global handle_category_drilldown

    if handle_category_drilldown is None:
        from app.core.shopping_flow.handlers.category_drilldown import handle_category_drilldown as _handle_category_drilldown

        handle_category_drilldown = _handle_category_drilldown


def _ensure_product_swipe_handler_loaded() -> None:
    global handle_product_swipe

    if handle_product_swipe is None:
        from app.core.shopping_flow.handlers.product_swipe import handle_product_swipe as _handle_product_swipe

        handle_product_swipe = _handle_product_swipe


def _ensure_questionnaire_handler_loaded() -> None:
    global handle_questionnaire

    if handle_questionnaire is None:
        from app.core.shopping_flow.handlers.questionnaire import handle_questionnaire as _handle_questionnaire

        handle_questionnaire = _handle_questionnaire


async def stream_shopping_agent_native(payload: ChatRequest):
    session_id = getattr(payload, "sessionId", None) or str(uuid.uuid4())
    session = get_or_create_session(session_id)
    message_text = (payload.message or "").strip()

    if message_text and not session.get("original_keyword"):
        session["original_keyword"] = message_text

    if payload.hidden_events:
        action = payload.hidden_events.action
        data = payload.hidden_events.payload

        if action == "PRODUCT_FEEDBACK":
            _ensure_product_swipe_handler_loaded()
            async for chunk in handle_product_swipe(session, session_id, action, data):
                yield chunk
            return

        if action == "SUBMIT_SURVEY":
            if session.get("phase") == "CATEGORY_DRILLDOWN":
                _ensure_category_drilldown_handler_loaded()
                async for chunk in handle_category_drilldown(payload, session, action, data):
                    yield chunk
            else:
                _ensure_questionnaire_handler_loaded()
                async for chunk in handle_questionnaire(payload, session, action, data):
                    yield chunk
            return

        if action == "SKIP_SURVEY":
            _ensure_questionnaire_handler_loaded()
            async for chunk in handle_questionnaire(payload, session, action, data):
                yield chunk
            return

        yield MessageChunk(content="Mình chưa hiểu thao tác này, bạn thử lại nhé.")
        return

    if _is_greeting_or_smalltalk(message_text):
        yield MessageChunk(content="Chào bạn! Mình có thể giúp tìm sản phẩm phù hợp. Bạn muốn mua gì nào?")
        return

    if not message_text:
        yield MessageChunk(content="Bạn muốn tìm mua sản phẩm gì? Hãy gửi tên món đồ để mình bắt đầu nhé.")
        return

    _ensure_initial_handler_loaded()
    async for chunk in handle_initial_phase(payload, session):
        yield chunk
