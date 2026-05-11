import random
import uuid

from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_prepare_stream,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.core.shopping_flow.product_filters import parse_budget_bounds
from app.models.ui_chunks import ChatRequest, A2UIChunk, MessageChunk


def _build_search_keyword_from_session(session: dict, extra_terms: list[str] | None = None) -> str:
    """
    Ghép keyword tìm kiếm từ:
    - vi_keyword: từ khóa gốc user nhập ("áo khoác")
    - extra_terms: các attribute options user đã chọn (nếu có)
    KHÔNG ghép leaf_category_name vì đó là internal label DB.
    """
    base = (session.get("vi_keyword") or session.get("original_keyword") or "").strip()
    terms = [base] + (extra_terms or [])
    return " ".join(filter(None, terms)).strip()


def _get_user_message(session: dict, payload: ChatRequest) -> str:
    """
    Lấy user_message có ngữ cảnh đầy đủ:
    - Ưu tiên payload.message nếu user vừa gõ thêm gì đó
    - Fallback về original_keyword trong session (câu gốc user đã nhập)
    Giúp AI ranker hiểu đúng intent dù đang ở hidden_events turn.
    """
    if hasattr(payload, "message") and payload.message and payload.message.strip():
        return payload.message.strip()
    # Khi payload.message rỗng (do hidden_events), dùng lại câu gốc
    return (session.get("original_keyword") or "").strip()


async def handle_category_drilldown(payload: ChatRequest, session: dict, action: str, data):
    trace_id = session.get("_trace_id", "unknown")

    if action != "SUBMIT_SURVEY":
        return

    if isinstance(data, list) and data:
        selected_name = data[0]
    elif isinstance(data, dict):
        selected_name = data.get("name") or data.get("value") or data.get("label") or ""
    else:
        selected_name = data

    selected_name = str(selected_name).strip()
    if not selected_name:
        yield MessageChunk(content="Mình chưa nhận được lựa chọn danh mục, bạn chọn lại giúp mình nhé.")
        return

    cat_map = session.get("category_map", {})
    selected_cat_id = cat_map.get(selected_name, session.get("current_category_id"))

    if selected_cat_id is None:
        yield MessageChunk(content="Mình chưa xác định được danh mục phù hợp, bạn chọn lại giúp mình nhé.")
        return

    session["current_category_id"] = selected_cat_id

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đã ghi nhận: {selected_name}. Đang tra cứu...",
                                   "progressPercent": 5}})

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đang tìm các nhóm nhỏ hơn trong '{selected_name}'...",
                                   "progressPercent": 15}})

    options, category_map, children = get_child_categories(selected_cat_id, trace_id)

    if len(options) > 4:
        options = random.sample(options, 4)

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đã tìm thấy {len(options)} nhóm sản phẩm con.",
                                   "progressPercent": 25}})

    if children:
        session["category_map"] = category_map
        next_question = {
            "id": "cat_drilldown_" + uuid.uuid4().hex,
            "name": "Chi tiết hơn một chút nhé, bạn muốn tìm loại nào?",
            "options": options,
        }
        yield build_questionnaire_chunk(next_question, allow_multiple=False)
        return

    # Đã tới leaf — lưu lại để hiển thị UI, KHÔNG dùng cho search keyword
    session["leaf_category_name"] = selected_name

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đã chọn '{selected_name}'. Đang tìm tiêu chí lọc...",
                                   "progressPercent": 35}})

    session["attributes"] = build_attribute_questions(selected_cat_id, trace_id)

    if session["attributes"]:
        session["phase"] = "QUESTIONNAIRE"
        first_attr = session["attributes"].pop(0)
        session["current_attribute_id"] = first_attr["id"]

        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": f"Đã tìm thấy {len(session['attributes']) + 1} tiêu chí. Bắt đầu lọc nào!",
                                       "progressPercent": 45}})
        yield build_questionnaire_chunk(first_attr, allow_multiple=True)
        return

    # Không có attribute → search luôn
    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": "Đã thu thập đủ thông tin. Đang thiết lập bộ lọc...",
                                   "progressPercent": 50}})

    # ── FIX 1: Keyword chỉ dùng vi_keyword, không ghép leaf_category_name ──
    final_search_keyword = _build_search_keyword_from_session(session)

    # ── FIX 2: user_message có ngữ cảnh đầy đủ dù đang ở hidden_events turn ──
    user_message = _get_user_message(session, payload)

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đang tìm kiếm '{final_search_keyword}'...",
                                   "progressPercent": 70}})

    raw_products, ranked_stream = await search_and_prepare_stream(
        final_search_keyword=final_search_keyword,
        user_message=user_message,
        answers=[],
        min_price_filter=None,
        max_price_filter=None,
        trace_id=trace_id,
    )

    session["raw_products"] = raw_products
    session["pending_products"] = []
    first_prod = None

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": "AI đang phân tích và xếp hạng mẫu phù hợp nhất...",
                                   "progressPercent": 85}})

    async for product in ranked_stream:
        if first_prod is None:
            first_prod = product
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Hoàn tất!", "progressPercent": 100}})
            yield build_interactive_product_chunk(first_prod)
            session["phase"] = "PRODUCT_SWIPE"
        else:
            session["pending_products"].append(product)

    if first_prod is None:
        yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
        session["phase"] = "DONE"