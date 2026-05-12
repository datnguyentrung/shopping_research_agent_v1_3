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

    # [3%] Ghi nhận phản hồi
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {"statusText": last_options_text if last_options_text else "Đang ghi nhận lựa chọn...",
                     "progressPercent": 3},
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

        # [12%] Chuẩn bị câu hỏi tiếp theo
        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": "✓ Đã lưu. Chuẩn bị câu hỏi tiếp theo...",
                                       "progressPercent": 12}})
        yield build_questionnaire_chunk(next_attr, allow_multiple=True)

        # -> FIX 3: Báo cáo state trước khi chuyển giao diện
        yield {"state_update": state}
        return

    # [18%] Xong hết câu hỏi - bắt đầu tìm kiếm
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {"statusText": f"Đã thu thập {len(state.get('answers', []))} tiêu chí. Chuẩn bị tìm kiếm...", "progressPercent": 18},
        }
    )

    first_prod = None

    try:
        # -> FIX 4: Gọi hàm helper để sinh keyword và bóc tách giá
        final_search_keyword, min_price_filter, max_price_filter = build_search_keyword_from_answers(state)

        # -> FIX 5: Lấy user_message từ helper sử dụng state
        user_message = _get_user_message_from_state(state)

        # [28%] Xây dụng thông số tìm kiếm
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Đang căn chỉnh thông số: Tìm '{final_search_keyword}'...",
                    "progressPercent": 28,
                },
            }
        )

        # [35%] Gọi API song song (Vertex + Serper)
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Lục lọi hàng ngàn kho hàng với bộ tiêu chí của bạn...",
                    "progressPercent": 35,
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

        # [48%] Bắt đầu AI Ranking
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Tìm thấy {len(raw_products)} sản phẩm. AI đang chấm điểm từng mẫu...",
                    "progressPercent": 48,
                },
            }
        )

        prod_count = 0
        async for product in ranked_stream:
            prod_count += 1
            if first_prod is None:
                first_prod = product
                # [95%] Mẫu đầu tiên sân sàng
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {"statusText": "✨ Mẫu hàng đầu tiên được AI chọn. Chuẩn bị hiển thị...", "progressPercent": 95},
                    }
                )
                yield build_interactive_product_chunk(first_prod)
                state["phase"] = "PRODUCT_SWIPE"
            else:
                state["pending_products"].append(product)
                # Dynamic progress trong stream
                if prod_count % 2 == 0:
                    progress = min(94, 48 + (prod_count // 2))
                    yield A2UIChunk(
                        a2ui={
                            "type": "a2ui_processing_status",
                            "data": {
                                "statusText": f"📦 Đã sắp xếp {prod_count} sản phẩm...",
                                "progressPercent": progress,
                            },
                        }
                    )

        if first_prod is None:
            yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
            state["phase"] = "DONE"
        else:
            # [100%] Hoàn tất
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {"statusText": f"🎉 Xong! Tìm thấy {len(state['pending_products']) + 1} ứng viên.", "progressPercent": 100},
                }
            )

    except Exception as exc:
        traceback.print_exc()
        state["pending_products"] = []
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra trong quá trình thu thập thuộc tính.")
        state["phase"] = "ERROR"

    # -> FIX 6: Chốt State cuối cùng cho toàn bộ luồng
    yield {"state_update": state}