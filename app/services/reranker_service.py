
import json
import re
from google.genai import types
from collections.abc import AsyncIterator

from google import genai

from app.core.llm_models import MODELS_TO_TRY
from app.utils.request_model_service import _build_user_contents, get_client
from app.utils.trace_log import product_summary, trace_print

async def rank_products_with_llm_stream(
        filtered_products: list,
        user_message: str,
        answers: list,
        trace_id: str | None = None) -> AsyncIterator[dict]:
    trace_key = trace_id or "no-trace"
    trace_print(
        trace_key,
        "rank_products_with_llm_stream",
        "enter",
        filteredProducts=len(filtered_products),
        answersCount=len(answers),
        userMessagePreview=user_message[:160],
    )

    if not filtered_products:
        trace_print(trace_key, "rank_products_with_llm_stream", "no_filtered_products")
        return

    preferences_text = "Không có tiêu chí đặc biệt."
    if answers:
        prefs = [", ".join([str(opt) for opt in ans.get("selected_options", [])]) for ans in answers if
                 ans.get("selected_options")]
        if prefs:
            preferences_text = "Người dùng ưu tiên các tiêu chí sau: " + " | ".join(prefs)

    mini_products = []
    product_map = {}
    for prod in filtered_products:
        p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        pid = str(p_dict.get("product_id") or p_dict.get("productId") or p_dict.get("id"))

        product_map[pid] = prod
        mini_products.append({
            "product_id": pid,
            "name": p_dict.get("name", ""),
            "price": p_dict.get("price_current", 0),
            "rating": p_dict.get("rating_star", 0),
            "sold": p_dict.get("sold_count", 0)
        })

    trace_print(
        trace_key,
        "rank_products_with_llm_stream",
        "prompt_prepared",
        candidateCount=len(mini_products),
    )

    prompt = f"""Hãy xếp hạng danh sách sản phẩm E-commerce dưới đây.
    [YÊU CẦU BAN ĐẦU CỦA KHÁCH]: "{user_message}"
    [CÁC TIÊU CHÍ KHÁCH ĐÃ CHỌN THÊM]: {preferences_text}
    [DANH SÁCH SẢN PHẨM ỨNG VIÊN]: {json.dumps(mini_products, ensure_ascii=False)}
    Nhiệm vụ: Chấm điểm (score từ 0-100)..."""

    yielded_ids = set()
    stream_idx = 0

    async for pid in stream_ranking_ids(prompt):
        stream_idx += 1
        trace_print(
            trace_key,
            "rank_products_with_llm_stream",
            "ranking_id_streamed",
            index=stream_idx,
            productId=pid,
            seenCount=len(yielded_ids),
        )
        if pid in product_map and pid not in yielded_ids:
            yielded_ids.add(pid)
            product = product_map[pid]
            trace_print(
                trace_key,
                "rank_products_with_llm_stream",
                "emit_ranked_product",
                product=product_summary(product),
            )
            yield product

    fallback_count = 0
    for pid, p in product_map.items():
        if pid not in yielded_ids:
            fallback_count += 1
            trace_print(
                trace_key,
                "rank_products_with_llm_stream",
                "emit_fallback_product",
                product=product_summary(p),
            )
            yield p

    trace_print(
        trace_key,
        "rank_products_with_llm_stream",
        "completed",
        rankedYielded=len(yielded_ids),
        fallbackYielded=fallback_count,
        totalYielded=len(yielded_ids) + fallback_count,
    )



async def stream_ranking_ids(prompt: str) -> AsyncIterator[str]:
    """
    Đọc stream từ LLM và trích xuất product_id ngay khi nó xuất hiện.
    """
    contents = _build_user_contents(prompt)

    generate_content_config = types.GenerateContentConfig(
        temperature=0.5,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.MEDIUM,
        ),
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.ARRAY,
            items=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                properties={
                    "product_id": genai.types.Schema(type=genai.types.Type.STRING),
                    "score": genai.types.Schema(type=genai.types.Type.INTEGER),
                },
                required=["product_id", "score"]
            )
        ),
    )

    for model in MODELS_TO_TRY:
        try:
            stream = await get_client().aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            )
            buffer = ""
            seen_ids = set()

            async for chunk in stream:
                if text := getattr(chunk, "text", None):
                    buffer += text
                    # Regex quét qua buffer tìm cấu trúc "product_id": "id_sản_phẩm"
                    matches = re.findall(r'"product_id"\s*:\s*"([^"]+)"', buffer)
                    for pid in matches:
                        if pid not in seen_ids:
                            seen_ids.add(pid)
                            yield pid  # Bắn ngay ID này về luồng xử lý
            return  # Thành công thì thoát fallback
        except Exception as e:
            print(f"[Warning] Lỗi model '{model}' khi stream ranking: {e}")
            continue