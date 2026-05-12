import random
import traceback
import uuid

from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_prepare_stream,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.memory.adk_state import ShoppingState
from app.models.ui_chunks import A2UIChunk, MessageChunk


def _build_search_keyword_from_state(state: ShoppingState, extra_terms: list[str] | None = None) -> str:
    """
    Ghép keyword tìm kiếm từ:
    - vi_keyword: từ khóa gốc user nhập ("áo khoác")
    - extra_terms: các attribute options user đã chọn (nếu có)
    KHÔNG ghép leaf_category_name vì đó là internal label DB.
    """
    base = (state.get("vi_keyword") or state.get("original_keyword") or "").strip()
    terms = [base] + (extra_terms or [])
    return " ".join(filter(None, terms)).strip()


def _get_user_message_from_state(state: ShoppingState) -> str:
    """
    Lấy user_message có ngữ cảnh đầy đủ hoàn toàn từ State.
    """
    current_message = state.get("current_message", "").strip()
    if current_message:
        return current_message
    return (state.get("original_keyword") or "").strip()


async def adk_category_drilldown_node(state: ShoppingState):
    # -> FIX 1: Lấy các biến action, data từ state
    trace_id = state.get("session_id", "unknown")
    action = state.get("hidden_action")
    data = state.get("hidden_payload")

    # -> FIX 2: Báo cáo State trước mọi lệnh return
    if action != "SUBMIT_SURVEY":
        yield {"state_update": state}
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
        yield {"state_update": state}
        return

    cat_map = state.get("category_map", {})
    selected_cat_id = cat_map.get(selected_name, state.get("current_category_id"))

    if selected_cat_id is None:
        yield MessageChunk(content="Mình chưa xác định được danh mục phù hợp, bạn chọn lại giúp mình nhé.")
        yield {"state_update": state}
        return

    state["current_category_id"] = selected_cat_id

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đã ghi nhận: {selected_name}. Đang tra cứu...",
                                   "progressPercent": 5}})

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đang tìm các nhóm nhỏ hơn trong '{selected_name}'...",
                                   "progressPercent": 15}})

    try:
        options, category_map, children = get_child_categories(selected_cat_id, trace_id)

        if len(options) > 4:
            options = random.sample(options, 4)

        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": f"Đã tìm thấy {len(options)} nhóm sản phẩm con.",
                                       "progressPercent": 25}})

        if children:
            state["category_map"] = category_map
            next_question = {
                "id": "cat_drilldown_" + uuid.uuid4().hex,
                "name": "Chi tiết hơn một chút nhé, bạn muốn tìm loại nào?",
                "options": options,
            }
            yield build_questionnaire_chunk(next_question, allow_multiple=False)
            yield {"state_update": state} # Báo cáo state trước khi chuyển Phase
            return

        # Đã tới leaf — lưu lại để hiển thị UI, KHÔNG dùng cho search keyword
        state["leaf_category_name"] = selected_name

        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": f"Đã chọn '{selected_name}'. Đang tìm tiêu chí lọc...",
                                       "progressPercent": 35}})

        state["attributes"] = build_attribute_questions(selected_cat_id, trace_id)

        if state["attributes"]:
            state["phase"] = "QUESTIONNAIRE"
            first_attr = state["attributes"].pop(0)
            state["current_attribute_id"] = first_attr["id"]

            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": f"Đã tìm thấy {len(state['attributes']) + 1} tiêu chí. Bắt đầu lọc nào!",
                                           "progressPercent": 45}})
            yield build_questionnaire_chunk(first_attr, allow_multiple=True)
            yield {"state_update": state} # Báo cáo state trước khi chuyển Phase
            return

        # Không có attribute → search luôn
        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": "Đã thu thập đủ thông tin. Đang thiết lập bộ lọc...",
                                       "progressPercent": 50}})

        final_search_keyword = _build_search_keyword_from_state(state)
        # -> FIX 3: Dùng hàm helper mới không cần payload
        user_message = _get_user_message_from_state(state)

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

        state["raw_products"] = raw_products
        state["pending_products"] = []
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
                state["phase"] = "PRODUCT_SWIPE"
            else:
                state["pending_products"].append(product)

        if first_prod is None:
            yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
            state["phase"] = "DONE"

    except Exception as exc:
        traceback.print_exc()
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra khi xử lý danh mục.")
        state["phase"] = "ERROR"

    # Chốt điểm cuối cùng của luồng thực thi
    yield {"state_update": state}