
import json
import traceback

from app.models.ui_chunks import A2UIChunk, MessageChunk
from app.services.generate_final_summary_stream_service import generate_final_summary_stream


async def generate_final_summary_with_llm(
        whitelist: list,
        all_products: list,
        original_keyword: str = "",
        pending_products: list | None = None,
        blacklist: list | None = None,
        progress_offset: int = 0,
):
    """Build a final recommendation report from user likes/dislikes and candidates.

    Args:
        progress_offset: Starting percentage for progress yields.
                         Allows the caller to maintain monotonic progress
                         across a multi-phase pipeline.
    """
    if blacklist is None:
        blacklist = []
    if pending_products is None:
        pending_products = []

    selected_products = []
    rejected_products = []

    # ── offset + 4%: Bắt đầu chuẩn bị dữ liệu ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"Đang tổng hợp {len(whitelist)} mẫu bạn thích và phân tích đối chiếu...",
                "progressPercent": progress_offset + 4,
            },
        }
    )

    whitelist_ids = [str(item.get("productId") or item.get("product_id")) for item in whitelist]
    blacklist_ids = [str(item.get("productId") or item.get("product_id")) for item in blacklist]
    interacted_ids = set(whitelist_ids + blacklist_ids)

    for prod in all_products:
        prod_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        current_id = str(prod_dict.get("product_id"))

        if current_id in whitelist_ids:
            # --- FIX Ở ĐÂY: Xóa ảnh nếu nó là Base64 ---
            img_url = prod_dict.get("main_image", "")
            if img_url.startswith("data:image"):
                img_url = ""  # Xóa trắng để AI bỏ qua
            # ------------------------------------------

            selected_products.append(
                {
                    "Tên": prod_dict.get("name", "N/A"),
                    "Giá": f"{int(prod_dict.get('price_current', 0)):,} {prod_dict.get('currency', 'VND')}",
                    "Đánh giá": f"{prod_dict.get('rating_star', 0)} ⭐",
                    "Đã bán": prod_dict.get("sold_count", "Không có dữ liệu"),
                    "Shop": prod_dict.get("shop", {}).get("shop_name", "N/A"),
                    "Ảnh": img_url,  # Dùng biến đã được làm sạch
                    "Link": prod_dict.get("product_url", ""),
                }
            )
        elif current_id in blacklist_ids:
            rejected_products.append(
                {
                    "Tên": prod_dict.get("name", "N/A"),
                    "Giá": f"{int(prod_dict.get('price_current', 0)):,}".replace(",", ".") + " ₫",
                }
            )

    # ── offset + 10%: Đã phân loại xong liked/rejected ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"Đã phân loại {len(selected_products)} thích, {len(rejected_products)} không thích. Đang tìm ứng viên...",
                "progressPercent": progress_offset + 10,
            },
        }
    )

    candidates = []
    pending_dicts = [p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p for p in pending_products]

    for prod_dict in pending_dicts:
        current_id = str(prod_dict.get("product_id"))
        if current_id not in interacted_ids:
            candidates.append(prod_dict)
            if len(candidates) >= 20:
                break

    existing_candidate_ids = {str(c.get("product_id")) for c in candidates}
    for prod in all_products:
        if len(candidates) >= 40:
            break

        prod_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
        current_id = str(prod_dict.get("product_id"))

        if current_id not in interacted_ids and current_id not in existing_candidate_ids:
            rating = float(prod_dict.get("rating_star", 0))
            if rating == 0.0 or rating >= 4.0:
                candidates.append(prod_dict)

    ai_candidates = []
    for candidate in candidates:
        # --- FIX Ở ĐÂY: Xóa ảnh nếu nó là Base64 ---
        img_url = candidate.get("main_image", "")
        if img_url.startswith("data:image"):
            img_url = ""
        # ------------------------------------------
        ai_candidates.append(
            {
                "Tên": candidate.get("name", "N/A"),
                "Giá": f"{int(candidate.get('price_current', 0)):,} VND",
                "Đánh giá": f"{candidate.get('rating_star', 0)} ⭐",
                "Đã bán": candidate.get("sold_count", "Không có dữ liệu"),
                "Shop": candidate.get("shop", {}).get("shop_name", "N/A"),
                "Ảnh": img_url,
                "Link": candidate.get("product_url", ""),
            }
        )

    # ── offset + 16%: Đã xây dựng xong danh sách ứng viên ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"Đã chọn ra {len(ai_candidates)} ứng viên tiềm năng. Đang chuẩn bị prompt phân tích...",
                "progressPercent": progress_offset + 16,
            },
        }
    )

    prompt = f"""Dựa trên dữ liệu dưới đây, hãy áp dụng hướng dẫn hệ thống để viết báo cáo mua sắm:

    [TỪ KHÓA GỐC]: "{original_keyword}"
    [ĐÃ THÍCH]: {json.dumps(selected_products, ensure_ascii=False)}
    [KHÔNG THÍCH]: {json.dumps(rejected_products, ensure_ascii=False)}
    [ỨNG VIÊN]: {json.dumps(ai_candidates, ensure_ascii=False)}
    """

    # ── offset + 20%: Trước khi gọi LLM ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": "AI đang viết báo cáo tổng hợp cuối cùng cho bạn...",
                "progressPercent": progress_offset + 20,
            },
        }
    )

    try:
        async for text_chunk in generate_final_summary_stream(prompt):
            if text_chunk:
                yield MessageChunk(content=text_chunk)
    except Exception as exc:
        print(f"Error generating final summary: {exc}")
        traceback.print_exc()
        yield MessageChunk(
            content="\n\n*Hệ thống đang quá tải, không thể tạo báo cáo tóm tắt lúc này. Bạn vui lòng xem lại danh sách ở trên nhé!*"
        )

    # ── offset + 26%: Sau khi LLM stream hoàn tất ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": "Đã nhận xong nội dung báo cáo từ AI...",
                "progressPercent": progress_offset + 26,
            },
        }
    )