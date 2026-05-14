
import json
import traceback

from app.models.ui_chunks import A2UIChunk, MessageChunk
from app.services.lite_llm.generate_final_summary_stream_service import generate_final_summary_stream


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

    # ── offset + 1%: Khởi động tổng hợp ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"📋 Bắt đầu tổng hợp {len(whitelist)} sản phẩm bạn thích...",
                "progressPercent": progress_offset + 1,
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

    # ── offset + 8%: Phân loại sản phẩm ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"🔍 Phân loại: {len(selected_products)} mẫu yêu thích, {len(rejected_products)} mẫu bỏ qua. Tìm ứng viên bổ sung...",
                "progressPercent": progress_offset + 8,
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

    # ── offset + 14%: Xây dựng danh sách ứng viên ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"✅ Chọn ra {len(ai_candidates)} ứng viên tiềm năng. Chuẩn bị prompt AI...",
                "progressPercent": progress_offset + 14,
            },
        }
    )

    prompt = f"""Dựa trên dữ liệu dưới đây, hãy áp dụng hướng dẫn hệ thống để viết báo cáo mua sắm:

    [TỪ KHÓA GỐC]: "{original_keyword}"
    [ĐÃ THÍCH]: {json.dumps(selected_products, ensure_ascii=False)}
    [KHÔNG THÍCH]: {json.dumps(rejected_products, ensure_ascii=False)}
    [ỨNG VIÊN]: {json.dumps(ai_candidates, ensure_ascii=False)}
    """

    # ── offset + 18%: Gọi LLM để viết báo cáo ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": "🧠 AI đang suy ngẫm để viết báo cáo tư vấn chuyên sâu cho bạn...",
                "progressPercent": progress_offset + 18,
            },
        }
    )

    try:
        stream_count = 0
        async for text_chunk in generate_final_summary_stream(prompt):
            stream_count += 1
            if text_chunk:
                yield MessageChunk(content=text_chunk)
            # Dynamic progress: Từ offset+18% đến offset+28%
            if stream_count % 10 == 0:
                progress = min(progress_offset + 28, progress_offset + 18 + (stream_count // 5))
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {
                            "statusText": f"✍️ AI đang viết... ({stream_count} đoạn)",
                            "progressPercent": progress,
                        },
                    }
                )
    except Exception as exc:
        print(f"Error generating final summary: {exc}")
        traceback.print_exc()
        yield MessageChunk(
            content="\n\n*Hệ thống đang quá tải, không thể tạo báo cáo tóm tắt lúc này. Bạn vui lòng xem lại danh sách ở trên nhé!*"
        )

    # ── offset + 30%: Hoàn tất LLM stream ──
    yield A2UIChunk(
        a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": "✓ Hoàn tất báo cáo từ AI!",
                "progressPercent": progress_offset + 30,
            },
        }
    )