
import traceback

from app.core.shopping_flow.phase_utils import search_and_prepare_stream,build_search_keyword_from_answers, get_user_message
from app.core.shopping_flow.product_filters import parse_budget_bounds
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.models.ui_chunks import ChatRequest, A2UIChunk, MessageChunk


async def handle_questionnaire(payload: ChatRequest, session: dict, action: str, data):
    trace_id = session.get("_trace_id", "unknown")

    if action not in ["SUBMIT_SURVEY", "SKIP_SURVEY"]:
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
        if "answers" not in session:
            session["answers"] = []
        session["answers"].append({
            "attribute_id": session.get("current_attribute_id"),
            "selected_options": data,
        })

    if session["attributes"]:
        next_attr = session["attributes"].pop(0)
        session["current_attribute_id"] = next_attr["id"]

        # [TIẾN TRÌNH 30%] Khi có câu hỏi tiếp theo
        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": "Đã lưu lựa chọn. Đang tải câu hỏi tiếp theo...",
                                       "progressPercent": 30}})
        yield build_questionnaire_chunk(next_attr, allow_multiple=True)
        return

    # [TIẾN TRÌNH 50%] Hết câu hỏi
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {"statusText": "Đã thu thập đủ thông tin. Đang thiết lập bộ lọc...", "progressPercent": 50},
        }
    )

    first_prod = None

    first_prod = None

    try:
        # Lấy vi_keyword gốc
        base_keyword = (
                session.get("vi_keyword") or session.get("original_keyword") or ""
        ).strip()

        # Gom các options user đã chọn từ answers, bỏ qua options là giá tiền
        min_price_filter, max_price_filter = None, None
        attribute_terms = []

        for ans in session.get("answers", []):
            for option in ans.get("selected_options", []):
                option_str = str(option)

                # Parse giá — nếu có thì lưu filter, không ghép vào keyword
                parsed_min, parsed_max = parse_budget_bounds(option_str)
                if parsed_min is not None or parsed_max is not None:
                    if parsed_min is not None:
                        min_price_filter = parsed_min
                    if parsed_max is not None:
                        max_price_filter = parsed_max
                else:
                    # Không phải giá → ghép vào keyword tìm kiếm
                    attribute_terms.append(option_str)

        # Ghép keyword: "áo khoác không có mũ tay dài"
        final_search_keyword, min_price_filter, max_price_filter = build_search_keyword_from_answers(session)

        user_message = get_user_message(session, payload)

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
            answers=session.get("answers", []),
            min_price_filter=min_price_filter,
            max_price_filter=max_price_filter,
            trace_id=trace_id,
        )
        session["raw_products"] = raw_products
        session["pending_products"] = []

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

        stream_count = 0
        async for product in ranked_stream:
            stream_count += 1
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
                session["phase"] = "PRODUCT_SWIPE"
            else:
                session["pending_products"].append(product)

    except Exception as exc:
        traceback.print_exc()
        session["pending_products"] = []

    if first_prod is None:
        yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
        session["phase"] = "DONE"