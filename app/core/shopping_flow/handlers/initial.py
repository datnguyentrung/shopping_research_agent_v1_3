import traceback
import uuid

from app.memory.adk_state import ShoppingState
from app.tools.gg_translate_tool import get_bilingual_and_correct
from app.tools.query_category_classifier_tool import classify_keyword_topk
from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_prepare_stream,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.models.ui_chunks import A2UIChunk, MessageChunk
from app.utils.trace_log import trace_print


async def adk_initial_node(state: ShoppingState):
    trace_id = state.get("session_id", "unknown")
    user_message = state.get("current_message", "")

    # ---> THÊM ĐOẠN NÀY: Lưu tin nhắn đầu tiên vào lịch sử <---
    if user_message and not state.get("chat_history"):
        state["chat_history"] = [{"role": "user", "content": user_message}]

    # ── 1% ── Bắt đầu phân tích
    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": "Đang bóc tách yêu cầu của bạn...", "progressPercent": 1}})

    try:
        # ── 5% ── Google Translate sửa lỗi
        yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                              "data": {"statusText": "Đang sửa lỗi chính tả và dịch sang tiếng Anh...",
                                       "progressPercent": 5}})
        result = await get_bilingual_and_correct(user_message)
        vi_keyword, en_keyword = result.get("vi"), result.get("en")

        # ── 12% ── Phân loại danh mục bằng ML
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Đã nhận diện từ khóa: '{vi_keyword}'. Đang dò tìm danh mục phù hợp...",
                    "progressPercent": 12
                }
            })

        categories = classify_keyword_topk(en_keyword, k=1)
        top_cat = categories[0] if categories else None

        trace_print(trace_id, "handle_initial_phase", "fix_and_translate_result", viKeyword=vi_keyword,
                    enKeyword=en_keyword)

        if not top_cat or top_cat.get('score', 0) < 0.5:
            vi_keyword = "Thời trang và Phụ kiện"
            # ── 15% ── Fallback danh mục mềm
            yield MessageChunk(
                content="Do bạn chưa nêu tên sản phẩm cụ thể, mình sẽ mở danh mục tổng hợp 'Thời trang & Phụ kiện' để bạn tham khảo nhé. Bạn có thể gõ tên món đồ (vd: 'áo phông', 'giày thể thao') bất cứ lúc nào để mình tìm chính xác hơn!"
            )
            top_cat = {"category_id": "fashion", "category_name": "Clothing, Shoes & Jewelry"}

            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": "Đang khai thác danh mục 'Thời trang & Phụ kiện' để tìm nhóm nhỏ hơn...",
                        "progressPercent": 18,
                    },
                }
            )
        else:
            # ── 15% ── Đã xác định danh mục chính
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": f"✅ Tìm thấy danh mục '{top_cat.get('category_name', 'Unknown')}'. Đang tìm nhóm chi tiết...",
                        "progressPercent": 18,
                    },
                }
            )

        state["original_keyword"] = vi_keyword
        state["vi_keyword"] = vi_keyword

        if not top_cat:
            yield MessageChunk(content="Xin lỗi, mình không tìm thấy danh mục phù hợp cho từ khóa này.")
            state["phase"] = "ERROR"
            yield {"state_update": state}
            return

        state["current_category_id"] = top_cat["category_id"]

        # ── 22% ── Tra cứu danh mục con từ DB
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang tây tác cơ sở dữ liệu để tìm danh mục con...",
                    "progressPercent": 22,
                },
            }
        )
        options, category_map, children = get_child_categories(top_cat["category_id"], trace_id)

        need_drilldown_ui = False
        if children:
            state["category_map"] = category_map
            target_kw = state.get("vi_keyword", "").lower()
            matched_option = None

            # ── 28% ── Tìm match được danh mục con
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": f"Tìm thấy {len(options)} loại trong danh mục này. Đang căn chỉnh...",
                        "progressPercent": 28,
                    },
                }
            )

            for opt in options:
                if target_kw in opt.lower() or opt.lower() in target_kw:
                    matched_option = opt
                    break

            if matched_option:
                state["current_category_id"] = category_map[matched_option]
                state["leaf_category_name"] = matched_option
            else:
                need_drilldown_ui = True

        if need_drilldown_ui:
            state["phase"] = "CATEGORY_DRILLDOWN"
            first_question = {
                "id": "cat_drilldown_" + uuid.uuid4().hex,
                "name": "Bạn đang tìm kiếm loại mặt hàng nào dưới đây?",
                "options": options,
            }
            # ── 32% ── Hiển thị câu hỏi drilldown
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": "Chuẩn bị giao diện lựa chọn chi tiết...",
                        "progressPercent": 32,
                    },
                }
            )
            yield build_questionnaire_chunk(first_question, allow_multiple=False)
            yield {"state_update": state}
            return

        if not state.get("leaf_category_name"):
            state["leaf_category_name"] = top_cat.get("category_name", "")

        # ── 38% ── Xây dựng câu hỏi thuộc tính từ DB
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang khai thác các tiêu chí lọc (màu, size, thương hiệu...) từ cơ sở dữ liệu...",
                    "progressPercent": 38,
                },
            }
        )

        state["attributes"] = build_attribute_questions(state["current_category_id"], trace_id)

        if state["attributes"]:
            state["phase"] = "QUESTIONNAIRE"
            first_attr = state["attributes"].pop(0)
            state["current_attribute_id"] = first_attr["id"]

            if "options" in first_attr and len(first_attr["options"]) > 4:
                first_attr["options"] = first_attr["options"][:4]

            # ── 48% ── Chuẩn bị câu hỏi đầu tiên
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": f"Tìm thấy {len(state['attributes']) + 1} tiêu chí. Chuẩn bị hỏi bạn về \"{first_attr.get('name', 'thuộc tính')}\"...",
                        "progressPercent": 48,
                    },
                }
            )
            yield build_questionnaire_chunk(first_attr, allow_multiple=True)
            yield {"state_update": state}
            return

        # Không có tiêu chí → tìm kiếm luôn
        # ── 55% ── Khởi động tìm kiếm song song
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {"statusText": "Sắp bắt đầu tìm kiếm sản phẩm. Đang thiết lập thông số...",
                         "progressPercent": 55},
            }
        )

        final_search_keyword = f"{state.get('original_keyword', '')} {state.get('leaf_category_name', '')}".strip()

        # ── 60% ── Gọi API song song (Vertex + Serper)
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Lục lọi hàng ngàn kho hàng tìm '{state.get('leaf_category_name', '')}'...",
                    "progressPercent": 60
                },
            }
        )

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

        # ── 72% ── Bắt đầu xếp hạng bằng AI
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Tìm thấy {len(raw_products)} sản phẩm. AI đang chấm điểm từng mẫu...",
                    "progressPercent": 72
                },
            }
        )

        first_prod = None
        prod_count = 0

        async for product in ranked_stream:
            prod_count += 1
            state["pending_products"].append(product)

            if first_prod is None:
                first_prod = product

            # Cập nhật progress mượt mà nhưng chưa gửi card sản phẩm
            if prod_count % 3 == 0:
                progress = min(94, 72 + (prod_count * 2))
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {"statusText": f"📦 Đã sắp xếp {prod_count} sản phẩm...", "progressPercent": progress},
                    }
                )

        # CHỐT HẠ SAU KHI XẾP HẠNG XONG
        if first_prod is None:
            yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
            state["phase"] = "DONE"
        else:
            # Báo 100% trước
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {"statusText": f"🎉 Xong! Tìm thấy {len(state['pending_products'])} ứng viên.",
                             "progressPercent": 100},
                }
            )
            # Hiện sản phẩm cuối cùng
            yield build_interactive_product_chunk(first_prod)
            state["phase"] = "PRODUCT_SWIPE"

    except Exception as exc:
        traceback.print_exc()
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra khi xử lý yêu cầu của bạn.")
        state["phase"] = "ERROR"

    # NÚT LƯU GAME: Đây là lệnh cuối cùng của hàm
    # Orchestrator sẽ lấy dict này để ghi đè vào SESSION_STORE
    yield {"state_update": state}
