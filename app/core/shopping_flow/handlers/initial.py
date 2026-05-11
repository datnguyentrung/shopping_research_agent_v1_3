import random
import traceback
import uuid


from app.tools.gg_translate_tool import get_bilingual_and_correct
from app.tools.query_category_classifier_tool import classify_keyword_topk
from app.core.shopping_flow.phase_utils import (
    build_attribute_questions,
    get_child_categories,
    search_and_prepare_stream,
)
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk, build_questionnaire_chunk
from app.models.ui_chunks import ChatRequest, A2UIChunk, MessageChunk
from app.utils.trace_log import product_summary, short_preview, trace_print


async def handle_initial_phase(payload: ChatRequest, session: dict):
    trace_id = session.get("_trace_id", "unknown")
    user_message = payload.message.strip()
    trace_print(
        trace_id,
        "handle_initial_phase",
        "enter",
        messagePreview=short_preview(user_message),
        incomingPhase=session.get("phase"),
    )

    session["whitelist"] = []
    session["blacklist"] = []

    # [TIẾN TRÌNH 5%] Khởi động
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": "Đang nhận diện yêu cầu của bạn...",
                "progressPercent": 5,
            },
        }
    )

    # [TIẾN TRÌNH 15%] Bắt đầu phân tích
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"Đợi mình một chút, đang phân tích nhu cầu '{user_message}' của bạn nhé...",
                "progressPercent": 15,
            },
        }
    )

    try:
        result = await get_bilingual_and_correct(user_message)
        vi_keyword, en_keyword = result.get("vi"), result.get("en")

        # [TIẾN TRÌNH 30%] Dịch xong
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Đã nhận diện từ khóa: '{vi_keyword}'. Đang đối chiếu với hệ thống danh mục...",
                    "progressPercent": 30
                },
            }
        )

        categories = classify_keyword_topk(en_keyword, k=1)
        top_cat = categories[0] if categories else None

        # [TIẾN TRÌNH 50%] Tìm thấy danh mục
        if top_cat:
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": f"Đã định vị được danh mục '{top_cat.get('category_name')}'. Đang chuẩn bị các tiêu chí để lọc...",
                        "progressPercent": 50
                    },
                }
            )

        trace_print(trace_id, "handle_initial_phase", "fix_and_translate_result", viKeyword=vi_keyword,
                    enKeyword=en_keyword)

        if not top_cat or top_cat.get('score', 0) < 0.5:
            vi_keyword = "Thời trang và Phụ kiện"
            yield MessageChunk(
                content="Do bạn chưa nêu tên sản phẩm cụ thể, mình sẽ mở danh mục tổng hợp 'Thời trang & Phụ kiện' để bạn tham khảo nhé. Bạn có thể gõ tên món đồ (vd: 'áo phông', 'giày thể thao') bất cứ lúc nào để mình tìm chính xác hơn!"
            )
            top_cat = {"category_id": "fashion", "category_name": "Clothing, Shoes & Jewelry"}

            # [TIẾN TRÌNH 40%] Vague path — trước khi lấy danh mục con
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": "Đang mở danh mục 'Thời trang & Phụ kiện' để bạn lựa chọn...",
                        "progressPercent": 40,
                    },
                }
            )
        else:
            # [TIẾN TRÌNH 40%] Trước khi phân loại danh mục
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": f"Đang tìm danh mục phù hợp nhất cho '{vi_keyword}'...",
                        "progressPercent": 40,
                    },
                }
            )




        session["original_keyword"] = vi_keyword
        session["vi_keyword"] = vi_keyword

        if not top_cat:
            yield MessageChunk(content="Xin lỗi, mình không tìm thấy danh mục phù hợp cho từ khóa này.")
            session["phase"] = "ERROR"
            return

        session["current_category_id"] = top_cat["category_id"]
        options, category_map, children = get_child_categories(top_cat["category_id"], trace_id)

        need_drilldown_ui = False
        if children:
            session["category_map"] = category_map
            target_kw = session.get("vi_keyword", "").lower()
            matched_option = None

            for opt in options:
                if target_kw in opt.lower() or opt.lower() in target_kw:
                    matched_option = opt
                    break

            if matched_option:
                session["current_category_id"] = category_map[matched_option]
                session["leaf_category_name"] = matched_option
            else:
                need_drilldown_ui = True

        if need_drilldown_ui:
            session["phase"] = "CATEGORY_DRILLDOWN"
            first_question = {
                "id": "cat_drilldown_" + uuid.uuid4().hex,
                "name": "Bạn đang tìm kiếm loại mặt hàng nào dưới đây?",
                "options": options,
            }
            yield build_questionnaire_chunk(first_question, allow_multiple=False)
            return

        if not session.get("leaf_category_name"):
            session["leaf_category_name"] = top_cat.get("category_name", "")

        # [TIẾN TRÌNH 60%] Trước khi xây dựng bộ câu hỏi thuộc tính
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang chuẩn bị các tiêu chí lọc sản phẩm...",
                    "progressPercent": 60,
                },
            }
        )

        session["attributes"] = build_attribute_questions(session["current_category_id"], trace_id)

        if session["attributes"]:
            session["phase"] = "QUESTIONNAIRE"
            first_attr = session["attributes"].pop(0)
            session["current_attribute_id"] = first_attr["id"]

            if "options" in first_attr and len(first_attr["options"]) > 4:
                first_attr["options"] = first_attr["options"][:4]

            yield build_questionnaire_chunk(first_attr, allow_multiple=True)
            return

        # [TIẾN TRÌNH 65%] Bắt đầu tìm kiếm
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {"statusText": "Đang thiết lập thông số tìm kiếm phù hợp nhất cho bạn...",
                         "progressPercent": 65},
            }
        )

        final_search_keyword = f"{session.get('original_keyword', '')} {session.get('leaf_category_name', '')}".strip()

        # [TIẾN TRÌNH 80%] Quét dữ liệu
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Đang quét hàng ngàn dữ liệu sản phẩm cho '{session.get('leaf_category_name', '')}'...",
                    "progressPercent": 80
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
        session["raw_products"] = raw_products
        session["pending_products"] = []

        first_prod = None
        stream_count = 0

        # [TIẾN TRÌNH 90%] Gọi LLM Ranking
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "AI đang chấm điểm và chọn lọc mẫu đẹp nhất cho bạn...",
                    "progressPercent": 90
                },
            }
        )

        async for product in ranked_stream:
            stream_count += 1
            session["pending_products"].append(product)

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

        if first_prod is None:
            yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
            session["phase"] = "DONE"

    except Exception as exc:
        traceback.print_exc()
        yield MessageChunk(content="Xin lỗi, có lỗi xảy ra khi xử lý yêu cầu của bạn.")
        session["phase"] = "ERROR"
