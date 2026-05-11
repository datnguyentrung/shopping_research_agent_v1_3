"""
Tool tìm kiếm và hiển thị sản phẩm
"""

from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk
from app.models.ui_chunks import A2UIChunk, MessageChunk
from app.services.reranker_service import rank_products_with_llm_stream
from app.services.search_service import run_parallel_searches
from app.memory.session_store import get_or_create_session
from google.genai import types

search_and_display_declaration = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="tool_search_and_display",
            description="Tìm kiếm, chấm điểm bằng AI và hiển thị danh sách sản phẩm lên màn hình UI cho người dùng.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "keyword": types.Schema(type=types.Type.STRING, description="Từ khóa sản phẩm (tiếng Việt)."),
                    "user_message": types.Schema(type=types.Type.STRING, description="Câu yêu cầu gốc của khách."),
                    "min_price": types.Schema(type=types.Type.INTEGER, description="Giá thấp nhất (nếu có)"),
                    "max_price": types.Schema(type=types.Type.INTEGER, description="Giá cao nhất (nếu có)"),
                    "criteria_text": types.Schema(type=types.Type.STRING,
                                                  description="Tóm tắt các yêu cầu (màu, size).")
                },
                required=["keyword", "user_message"]
            )
        )
    ]
)


async def stream_search_and_display(
        session_id: str,
        keyword: str,
        user_message: str,
        min_price: int = None,
        max_price: int = None,
        criteria_text: str = ""
):
    session = get_or_create_session(session_id)
    session["vi_keyword"] = keyword
    session["original_keyword"] = keyword

    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                          "data": {"statusText": f"Đang tìm '{keyword}'...", "progressPercent": 60}})

    raw_products = await run_parallel_searches(keyword_vi=keyword, min_price=min_price, max_price=max_price)

    if not raw_products:
        yield MessageChunk(content="Rất tiếc mình không tìm thấy sản phẩm nào phù hợp yêu cầu.")
        return

    yield A2UIChunk(
        a2ui={"type": "a2ui_processing_status", "data": {"statusText": "AI đang xếp hạng...", "progressPercent": 85}})

    answers = [{"selected_options": [criteria_text]}] if criteria_text else []

    # Tạo luồng chấm điểm
    ranked_stream = rank_products_with_llm_stream(
        filtered_products=raw_products,
        user_message=user_message,
        answers=answers,
        trace_id=session_id
    )

    session["raw_products"] = raw_products
    session["pending_products"] = []

    first_prod = None

    # Lặp qua stream chấm điểm
    async for product in ranked_stream:
        if first_prod is None:
            first_prod = product
            yield A2UIChunk(
                a2ui={"type": "a2ui_processing_status", "data": {"statusText": "Hoàn tất!", "progressPercent": 100}})
            yield build_interactive_product_chunk(first_prod)
            # Chuyển Phase về Product Swipe để bắt các event ở các turn kế tiếp
            session["phase"] = "PRODUCT_SWIPE"
        else:
            # Lưu các sản phẩm còn lại vào giỏ Pending
            session["pending_products"].append(product)

    if first_prod is None:
        yield MessageChunk(content="Không có sản phẩm nào vượt qua vòng kiểm duyệt của AI.")
