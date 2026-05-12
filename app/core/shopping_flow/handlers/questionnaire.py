import traceback

from app.core.shopping_flow.phase_utils import search_and_prepare_stream, build_search_keyword_from_answers
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.memory.adk_state import ShoppingState
from app.models.ui_chunks import A2UIChunk, MessageChunk


def _get_user_message_from_state(state: ShoppingState) -> str:
    """
    Lấy user_message có ngữ cảnh đầy đủ hoàn toàn từ State (thay thế cho việc dùng payload).
    """
    current_message = state.get("current_message", "").strip()
    if current_message:
        return current_message
    return (state.get("original_keyword") or "").strip()


async def adk_questionnaire_node(state: ShoppingState):
    # -> FIX 1: Trích xuất action, data, và trace_id từ State
    action = state.get("hidden_action")
    data = state.get("hidden_payload")
    trace_id = state.get("session_id", "unknown")

    # -> FIX 2: Báo cáo State trước khi return sớm
    if action not in ["SUBMIT_SURVEY", "SKIP_SURVEY"]:
        yield {"state_update": state}
        return

    last_options_text = ""
    if action == "SUBMIT_SURVEY":
        last_options_text = "Đang cập nhật: " + (
            ", ".join(str(x) for x in data) if isinstance(data, list) else str(data))
    elif action == "SKIP_SURVEY":
        last_options_text = "Đã bỏ qua tiêu chí."

    # [TIẾN TRÌNH 10%] Ghi nhận phản hồi
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {"statusText": last_options_text if last_options_text else "Đang ghi nhận...",
                     "progressPercent": 10},
        }
    )

    if action == "SUBMIT_SURVEY":
        if "answers" not in state:
            state["answers"] = []
        state["answers"].append({
            "attribute_id": state.get("current_attribute_id"),
            "selected_options": data,
        })

    if state.get("attributes"):
        next_attr = state["attributes"].pop(0)
        state["current_attribute_id"] = next_attr["id"]

        # [TIẾN TRÌNH 30%] Khi có câu hỏi tiếp theo
        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": "Đã lưu lựa chọn. Đang tải câu hỏi tiếp theo...",
                                       "progressPercent": 30}})
        yield build_questionnaire_chunk(next_attr, allow_multiple=True)

        # -> FIX 3: Báo cáo state trước khi chuyển giao diện
        yield {"state_update": state}
        return

    # [TIẾN TRÌNH 50%] Hết câu hỏi
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {"statusText": "Đã thu thập đủ thông tin. Đang thiết lập bộ lọc...", "progressPercent": 50},
        }
    )

    first_prod = None

    try:
        # -> FIX 4: Gọi hàm helper để sinh keyword và bóc tách giá (Đã dọn dẹp vòng lặp thừa)
        final_search_keyword, min_price_filter, max_price_filter = build_search_keyword_from_answers(state)

        # -> FIX 5: Lấy user_message từ helper sử dụng state
        user_message = _get_user_message_from_state(state)

        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Đang tìm kiếm '{final_search_keyword}'...",
                    "progressPercent": 70,
                },
            }
        )

        raw_products, ranked_stream = await search_and_prepare_stream(
            final_search_keyword=final_search_keyword,
            user_message=user_message,
            answers=state.get("answers", []),
            min_price_filter=min_price_filter,
            max_price_filter=max_price_filter,
            trace_id=trace_id,
        )

        state["raw_products"] = raw_products
        state["pending_products"] = []

        # [TIẾN TRÌNH 85%] Bắt đầu AI Ranking
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "AI đang chấm điểm và chọn lọc mẫu đẹp nhất cho bạn...",
                    "progressPercent": 85,
                },
            }
        )

        async for product in ranked_stream:
            if first_prod is None:
                first_prod = product
                # [TIẾN TRÌNH 100%]
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {"statusText": "Hoàn tất!", "progressPercent": 100},
                    }
                )
                yield build_interactive_product_chunk(first_prod)
                state["phase"] = "PRODUCT_SWIPE"
            else:
                state["pending_products"].append(product)

        if first_prod is None:
            yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
            state["phase"] = "DONE"

    except Exception as exc:
        traceback.print_exc()
        state["pending_products"] = []
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra trong quá trình thu thập thuộc tính.")
        state["phase"] = "ERROR"

    # -> FIX 6: Chốt State cuối cùng cho toàn bộ luồng
    yield {"state_update": state}