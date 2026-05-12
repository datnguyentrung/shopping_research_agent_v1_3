import traceback
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk
from app.core.shopping_flow.final_summary import generate_final_summary_with_llm
from app.memory.adk_state import ShoppingState

from app.models.ui_chunks import A2UIChunk, MessageChunk
from app.services.analyze_dislike_reason_service import analyze_dislike_reason

# Các từ khóa thay đổi ngữ cảnh tìm kiếm (giới tính, độ tuổi, loại hình)
_CONTEXT_SIGNALS = {
    "nam", "nữ", "bé", "trẻ em", "người lớn",
    "men", "women", "kids", "adult",
    "unisex", "nam giới", "nữ giới",
}


def _keywords_change_context(preferred_keywords: list[str], state: ShoppingState) -> bool:
    """
    Kiểm tra xem preferred_keywords có thay đổi ngữ cảnh tìm kiếm không.
    Nếu user nói 'cho nam' thì cần re-search, không chỉ filter.
    """
    if not preferred_keywords:
        return False
    for kw in preferred_keywords:
        if any(signal in kw.lower() for signal in _CONTEXT_SIGNALS):
            return True
    return False


def _build_new_keyword(state: ShoppingState, preferred_keywords: list[str]) -> str:
    """
    Ghép keyword mới từ vi_keyword gốc + preferred_keywords của user.
    VD: "áo khoác" + ["nam", "áo khoác nam"] → "áo khoác nam"
    """
    base = (state.get("vi_keyword") or state.get("original_keyword") or "").strip()

    # Lấy keyword preferred ngắn gọn nhất (tránh lặp)
    best_preferred = min(preferred_keywords, key=len) if preferred_keywords else ""

    # Nếu preferred đã bao gồm base thì dùng preferred luôn
    if base.lower() in best_preferred.lower():
        return best_preferred.strip()

    return f"{base} {best_preferred}".strip()


async def adk_product_swipe_node(state: ShoppingState):
    # -> FIX 1: Trích xuất action, data, và session_id từ State
    action = state.get("hidden_action")
    data = state.get("hidden_payload")
    session_id = state.get("session_id", "unknown")

    # -> FIX 2: Báo cáo State trước khi return sớm
    if action != "PRODUCT_FEEDBACK":
        yield {"state_update": state}
        return

    try:
        if isinstance(data, dict):
            decision = data.get("decision", "").lower()
            if decision == "like":
                state["whitelist"].append(data)
            elif decision == "dislike":
                state["blacklist"].append(data)
                reason = data.get("reason", "")
                rejected_product = data.get("product", {})

                if reason and state.get("pending_products"):
                    original_count = len(state["pending_products"])

                    yield A2UIChunk(
                        a2ui={
                            "type": "a2ui_processing_status",
                            "data": {
                                "statusText": f"Đã ghi nhận bạn không thích vì: '{reason}'. Đang phân tích phản hồi...",
                                "progressPercent": 3,
                            },
                        }
                    )

                    filtered_products = []

                    if reason == "Giá quá cao":
                        current_price = float(rejected_product.get("price_current", 0)) if rejected_product else 0
                        for p in state["pending_products"]:
                            p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                            if current_price == 0 or float(p_dict.get("price_current", 0)) <= (current_price * 1.1):
                                filtered_products.append(p)

                    elif reason == "Thương hiệu":
                        bad_brand = rejected_product.get("brand", "").lower() if rejected_product else ""
                        for p in state["pending_products"]:
                            p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                            if not bad_brand or p_dict.get("brand", "").lower() != bad_brand:
                                filtered_products.append(p)

                    elif reason == "Khác" or reason not in ["Không hợp phong cách", "Tính năng"]:
                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": "AI đang phân tích và bóc tách từ khóa cần tránh...",
                                    "progressPercent": 8,
                                },
                            }
                        )

                        analysis = await analyze_dislike_reason(reason)
                        banned_keywords = analysis.get("banned_keywords", [])
                        preferred_keywords = analysis.get("preferred_keywords", [])

                        if not state.get("preferred_keywords"):
                            state["preferred_keywords"] = []
                        state["preferred_keywords"].extend(preferred_keywords)

                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": "Đang rà soát và gạch tên các sản phẩm không phù hợp...",
                                    "progressPercent": 14,
                                },
                            }
                        )

                        for p in state["pending_products"]:
                            p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                            p_text = f"{p_dict.get('name', '')}".lower()
                            is_banned = any(kw.lower() in p_text for kw in banned_keywords if kw.strip())
                            if not is_banned:
                                filtered_products.append(p)

                        needs_research = _keywords_change_context(preferred_keywords, state)
                        if needs_research and preferred_keywords:
                            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                                  "data": {"statusText": "Đang tìm kiếm lại theo yêu cầu mới...",
                                                           "progressPercent": 25}})

                            new_keyword = _build_new_keyword(state, preferred_keywords)
                            state["vi_keyword"] = new_keyword

                            from app.core.shopping_flow.phase_utils import search_and_prepare_stream
                            new_raw, new_ranked_stream = await search_and_prepare_stream(
                                final_search_keyword=new_keyword,
                                user_message=new_keyword,
                                answers=state.get("answers", []),
                                trace_id=session_id,  # FIX: Dùng session_id
                            )
                            state["raw_products"] = new_raw

                            interacted_ids = {
                                str(item.get("productId") or item.get("product_id"))
                                for item in state.get("whitelist", []) + state.get("blacklist", [])
                            }

                            new_pending = []
                            async for prod in new_ranked_stream:
                                p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
                                if str(p_dict.get("product_id")) not in interacted_ids:
                                    new_pending.append(prod)

                            state["pending_products"] = new_pending
                            filtered_products = new_pending
                    else:
                        filtered_products = state["pending_products"]

                    if not filtered_products and state.get("pending_products"):
                        filtered_products = state["pending_products"]

                    if filtered_products:
                        state["pending_products"] = filtered_products

                    if len(filtered_products) < original_count:
                        dropped = original_count - len(filtered_products)
                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": f"Đã loại bỏ {dropped} sản phẩm không phù hợp. Đang sắp xếp lại danh sách...",
                                    "progressPercent": 20,
                                },
                            }
                        )

        total_swipes = len(state.get("whitelist", [])) + len(state.get("blacklist", []))

        # Kiểm tra điều kiện kết thúc vòng Swipe
        if len(state["whitelist"]) >= 5 or total_swipes >= 5 or len(state["pending_products"]) < 1:
            if not state["whitelist"]:
                yield MessageChunk(
                    content="Có vẻ bạn chưa ưng ý sản phẩm nào trong lô này. Hãy thử ấn Bắt đầu mới và mô tả lại nhu cầu cụ thể hơn nhé!")
                yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})

                # -> FIX 3: Gắn phase = DONE thay vì gọi clear_state trực tiếp
                state["phase"] = "DONE"
                yield {"state_update": state}
                return

            state["phase"] = "FINAL_SUMMARY"

            # BÁO CÁO TỔNG HỢP (Luồng chuyển trực tiếp)
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status", "data": {
                "statusText": f"Bạn đã ưng ý {len(state['whitelist'])} mẫu. Đang bắt đầu tổng hợp báo cáo...",
                "progressPercent": 30}})
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Đang thu thập thông tin chi tiết các mẫu bạn đã chọn...",
                                           "progressPercent": 35}})
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Đang nạp danh sách sản phẩm vào hệ thống phân tích...",
                                           "progressPercent": 40}})
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Đang phân tích đối chiếu giữa các sản phẩm...",
                                           "progressPercent": 46}})

            final_chunks = generate_final_summary_with_llm(
                whitelist=state["whitelist"],
                all_products=state.get("raw_products", []),
                original_keyword=state.get("vi_keyword", ""),
                pending_products=state.get("pending_products", []),
                blacklist=state["blacklist"],
                progress_offset=46,
            )

            async for chunk in final_chunks:
                yield chunk

            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Sắp hoàn thành báo cáo tổng hợp...", "progressPercent": 76}})
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Đang hoàn thiện chi tiết báo cáo...", "progressPercent": 82}})
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Đã hoàn thành báo cáo tổng hợp!", "progressPercent": 88}})
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "Đang tải kết quả cuối cùng cho bạn...",
                                           "progressPercent": 94}})

            yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})

            # -> FIX 3: Gắn phase = DONE
            state["phase"] = "DONE"
            yield {"state_update": state}
            return

        # Nếu chưa đủ điều kiện, đẩy sản phẩm tiếp theo lên UI
        next_prod = state["pending_products"].pop(0)
        yield build_interactive_product_chunk(next_prod)

    except Exception as exc:
        traceback.print_exc()
        yield MessageChunk(content="Đã có lỗi xảy ra trong quá trình lọc sản phẩm.")
        state["phase"] = "ERROR"

    # -> FIX: Chốt State cuối cùng
    yield {"state_update": state}