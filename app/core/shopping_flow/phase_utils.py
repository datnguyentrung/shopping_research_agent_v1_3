
import asyncio
import random

from app.core.shopping_flow.product_filters import apply_product_filters
from app.memory.adk_state import ShoppingState
from app.models.ui_chunks import MessageChunk
from app.repositories.category_attribute_repository import CategoryAttributeRepository
from app.repositories.category_repository import CategoryRepository
from app.services.database import SessionLocal
from app.services.reranker_service import rank_products_with_llm_stream
from app.services.search_service import run_parallel_searches
from app.utils.trace_log import trace_print


async def stream_static_message(text: str, chunk_size: int = 3, delay: float = 0.03):
    """
    Chia nhỏ một chuỗi tĩnh thành nhiều MessageChunk.
    - chunk_size: Số lượng từ mỗi lần yield.
    - delay: Độ trễ giữa mỗi lần yield (giây) để tạo hiệu ứng gõ phím.
    """
    words = text.split(" ")
    for i in range(0, len(words), chunk_size):
        # Nối lại và thêm khoảng trắng ở cuối
        chunk_str = " ".join(words[i:i + chunk_size]) + " "
        yield MessageChunk(content=chunk_str)
        await asyncio.sleep(delay)


def build_attribute_questions(category_id: str, trace_id: str | None = None) -> list[dict]:
    """Load inherited attributes and keep a compact randomized subset for UI questions."""
    trace_key = trace_id or "no-trace"
    trace_print(trace_key, "build_attribute_questions", "enter", categoryId=category_id)

    db = SessionLocal()
    try:
        category_attribute_repo = CategoryAttributeRepository(db)
        db_attributes = category_attribute_repo.get_inherited_attributes_cte([str(category_id)])

        attributes_data = []
        if db_attributes:
            selected_attributes = [db_attributes[0]]
            remaining_attributes = db_attributes[1:]
            num_samples = min(4, len(remaining_attributes))

            if num_samples > 0:
                selected_attributes.extend(random.sample(remaining_attributes, num_samples))

            for attr in selected_attributes:
                attributes_data.append(
                    {
                        "id": attr.id,
                        "name": attr.name,
                        "options": attr.options if attr.options else [],
                    }
                )

        trace_print(
            trace_key,
            "build_attribute_questions",
            "exit",
            sourceAttributes=len(db_attributes) if db_attributes else 0,
            selectedAttributes=len(attributes_data),
        )
        return attributes_data
    finally:
        db.close()


def get_child_categories(category_id: str, trace_id: str | None = None) -> tuple[list[str], dict[str, str], list]:
    """Load direct children for category drill-down and provide FE-ready option list."""
    trace_key = trace_id or "no-trace"
    trace_print(trace_key, "get_child_categories", "enter", categoryId=category_id)

    db = SessionLocal()
    try:
        category_repo = CategoryRepository(db)
        cat_children = category_repo.get_by_parent_id(category_id)
        options = [getattr(child, "name_vi", child.name) or child.name for child in cat_children]
        mapping = {(getattr(child, "name_vi", child.name) or child.name): child.id for child in cat_children}

        trace_print(
            trace_key,
            "get_child_categories",
            "exit",
            childrenCount=len(cat_children),
            optionsCount=len(options),
        )
        return options, mapping, cat_children
    finally:
        db.close()


# async def search_and_rank_products(
#     final_search_keyword: str,
#     user_message: str,
#     answers: list,
#     min_price_filter: int | None = None,
#     max_price_filter: int | None = None,
# ):
#     """Centralized search + ranking pipeline used by multiple phases."""
#     raw_products = await run_parallel_searches(final_search_keyword, min_price_filter, max_price_filter)
#
#     from app.core.shopping_flow.product_filters import apply_product_filters
#
#     filtered_products = apply_product_filters(raw_products, answers)
#     ranked_products = await rank_products_with_llm_stream(filtered_products, user_message, answers)
#     return raw_products, ranked_products

async def search_and_prepare_stream(
        final_search_keyword: str,
        user_message: str,
        answers: list,
        min_price_filter: int | None = None,
        max_price_filter: int | None = None,
        trace_id: str | None = None,
):
    trace_key = trace_id or "no-trace"
    trace_print(
        trace_key,
        "search_and_prepare_stream",
        "enter",
        finalSearchKeyword=final_search_keyword,
        answersCount=len(answers),
        minPrice=min_price_filter,
        maxPrice=max_price_filter,
    )

    raw_products = await run_parallel_searches(
        final_search_keyword,
        min_price_filter,
        max_price_filter,
        trace_id=trace_key,
    )

    filtered_products = apply_product_filters(raw_products, answers)
    ranked_stream = rank_products_with_llm_stream(filtered_products, user_message, answers, trace_id=trace_key)

    trace_print(
        trace_key,
        "search_and_prepare_stream",
        "prepared",
        rawProducts=len(raw_products),
        filteredProducts=len(filtered_products),
    )
    return raw_products, ranked_stream

def build_search_keyword_from_answers(session: ShoppingState, answers: list | None = None) -> tuple[str, int | None, int | None]:
    """
    Trả về (final_keyword, min_price, max_price) từ session + answers.
    - keyword = vi_keyword + các option KHÔNG phải giá
    - min/max price từ các option là giá tiền
    """
    from app.core.shopping_flow.product_filters import parse_budget_bounds

    base = (session.get("vi_keyword") or session.get("original_keyword") or "").strip()
    answers = answers or session.get("answers", [])

    attribute_terms = []
    min_price, max_price = None, None

    for ans in answers:
        for option in ans.get("selected_options", []):
            option_str = str(option)
            parsed_min, parsed_max = parse_budget_bounds(option_str)
            if parsed_min is not None or parsed_max is not None:
                if parsed_min is not None:
                    min_price = parsed_min
                if parsed_max is not None:
                    max_price = parsed_max
            else:
                attribute_terms.append(option_str)

    keyword = " ".join(filter(None, [base] + attribute_terms)).strip()
    return keyword, min_price, max_price


def get_user_message(session: dict, payload) -> str:
    """
    Lấy user_message có ngữ cảnh đầy đủ.
    Khi hidden_events turn, payload.message rỗng → fallback về original_keyword.
    """
    if hasattr(payload, "message") and payload.message and payload.message.strip():
        return payload.message.strip()
    return (session.get("original_keyword") or "").strip()