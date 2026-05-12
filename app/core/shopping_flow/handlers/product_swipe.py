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
                # ── 2% ── Ghi nhận lựa chọn "thích"
                yield A2UIChunk(
                    a2ui={
                        "type": "a2ui_processing_status",
                        "data": {
                            "statusText": f"❤️ Ghi nhận bạn thích sản phẩm này. Trong kho của mình rồi!",
                            "progressPercent": 2,
                        },
                    }
                )
            elif decision == "dislike":
                state["blacklist"].append(data)
                reason = data.get("reason", "")
                rejected_product = data.get("product", {})

                if reason and state.get("pending_products"):
                    original_count = len(state["pending_products"])

                    # ── 3% ── Ghi nhận lý do từ chối
                    yield A2UIChunk(
                        a2ui={
                            "type": "a2ui_processing_status",
                            "data": {
                                "statusText": f"👎 Ghi nhận: Bạn không thích vì '{reason}'. Đang phân tích...",
                                "progressPercent": 3,
                            },
                        }
                    )

                    filtered_products = []

                    if reason == "Giá quá cao":
                        # ── 8% ── Lọc giá
                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": "📊 Đang lọc sản phẩm với giá thấp hơn...",
                                    "progressPercent": 8,
                                },
                            }
                        )
                        current_price = float(rejected_product.get("price_current", 0)) if rejected_product else 0
                        for p in state["pending_products"]:
                            p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                            if current_price == 0 or float(p_dict.get("price_current", 0)) <= (current_price * 1.1):
                                filtered_products.append(p)

                    elif reason == "Thương hiệu":
                        # ── 8% ── Lọc thương hiệu
                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": "🏷️ Đang bỏ các sản phẩm từ thương hiệu này...",
                                    "progressPercent": 8,
                                },
                            }
                        )
                        bad_brand = rejected_product.get("brand", "").lower() if rejected_product else ""
                        for p in state["pending_products"]:
                            p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                            if not bad_brand or p_dict.get("brand", "").lower() != bad_brand:
                                filtered_products.append(p)

                    elif reason == "Khác" or reason not in ["Không hợp phong cách", "Tính năng"]:
                        # ── 6% ── Chuẩn bị phân tích lý do
                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": "🔍 AI đang bóc tách từ khóa cần tránh từ lý do của bạn...",
                                    "progressPercent": 6,
                                },
                            }
                        )

                        # ── 12% ── Gọi LLM phân tích lý do
                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": "💭 AI đang suy ngẫm: Để tìm sản phẩm tốt hơn, cần tránh những gì?...",
                                    "progressPercent": 12,
                                },
                            }
                        )

                        analysis = await analyze_dislike_reason(reason)
                        banned_keywords = analysis.get("banned_keywords", [])
                        preferred_keywords = analysis.get("preferred_keywords", [])

                        if not state.get("preferred_keywords"):
                            state["preferred_keywords"] = []
                        state["preferred_keywords"].extend(preferred_keywords)

                        # ── 18% ── Lọc sản phẩm dựa trên từ khóa cấm
                        yield A2UIChunk(
                            a2ui={
                                "type": "a2ui_processing_status",
                                "data": {
                                    "statusText": f"🚫 Loại bỏ sản phẩm chứa: {', '.join(banned_keywords[:3])}...",
                                    "progressPercent": 18,
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
                            # ── 22% ── Bắt đầu tìm kiếm lại
                            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                                  "data": {"statusText": f"🔄 Tiêu chí thay đổi: '{preferred_keywords[0]}'. Tìm kiếm lại...",
                                                           "progressPercent": 22}})

                            new_keyword = _build_new_keyword(state, preferred_keywords)
                            state["vi_keyword"] = new_keyword

                            from app.core.shopping_flow.phase_utils import search_and_prepare_stream

                            # ── 38% ── Gọi API song song với từ khóa mới
                            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                                  "data": {"statusText": f"🔍 Lục lọi kho hàng với tiêu chí mới: '{new_keyword}'...",
                                                           "progressPercent": 38}})

                            new_raw, new_ranked_stream = await search_and_prepare_stream(
                                final_search_keyword=new_keyword,
                                user_message=new_keyword,
                                answers=state.get("answers", []),
                                trace_id=session_id,
                            )
                            state["raw_products"] = new_raw

                            interacted_ids = {
                                str(item.get("productId") or item.get("product_id"))
                                for item in state.get("whitelist", []) + state.get("blacklist", [])
                            }

                            # ── 52% ── Bắt đầu xếp hạng
                            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                                  "data": {"statusText": "⭐ AI đang chấm điểm ứng viên mới...",
                                                           "progressPercent": 52}})

                            new_pending = []
                            prod_count = 0
                            async for prod in new_ranked_stream:
                                prod_count += 1
                                p_dict = prod.model_dump(by_alias=False) if hasattr(prod, "model_dump") else prod
                                if str(p_dict.get("product_id")) not in interacted_ids:
                                    new_pending.append(prod)
                                # Dynamic progress
                                if prod_count % 3 == 0:
                                    progress = min(78, 52 + (prod_count // 3))
                                    yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                                          "data": {"statusText": f"📦 Đã sắp xếp {prod_count} sản phẩm...",
                                                                   "progressPercent": progress}})

                            state["pending_products"] = new_pending
                            filtered_products = new_pending

                            # ── 88% ── Hoàn tất re-search
                            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                                  "data": {"statusText": "✅ Cập nhật danh sách thành công!",
                                                           "progressPercent": 88}})
                    else:
                        filtered_products = state["pending_products"]

                    if not filtered_products and state.get("pending_products"):
                        filtered_products = state["pending_products"]

                    if filtered_products:
                        state["pending_products"] = filtered_products

                    if len(filtered_products) < original_count:
                        dropped = original_count - len(filtered_products)

                        # ── 25% (nếu không phải re-search) ── Báo cáo loại bỏ
                        if not state.get("preferred_keywords"):
                            yield A2UIChunk(
                                a2ui={
                                    "type": "a2ui_processing_status",
                                    "data": {
                                        "statusText": f"✓ Loại bỏ {dropped} sản phẩm không phù hợp.",
                                        "progressPercent": 25,
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

                # -> FIX 3: Gắn phase = DONE
                state["phase"] = "DONE"
                yield {"state_update": state}
                return

            state["phase"] = "FINAL_SUMMARY"

            # ── 32% ── BÁO CÁO TỔNG HỢP
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status", "data": {
                "statusText": f"📋 Bạn thích {len(state['whitelist'])} sản phẩm. Bắt đầu tổng hợp báo cáo...",
                "progressPercent": 32}})

            # ── 42% ── Thu thập thông tin chi tiết
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "📊 Đang tập hợp thông tin chi tiết các mẫu bạn đã chọn...",
                                           "progressPercent": 42}})

            # ── 52% ── Nạp vào hệ thống phân tích
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "🧠 Đang nạp dữ liệu vào hệ thống phân tích AI...",
                                           "progressPercent": 52}})

            # ── 62% ── Phân tích đối chiếu
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "🔍 AI đang phân tích đối chiếu các mẫu...",
                                           "progressPercent": 62}})

            final_chunks = generate_final_summary_with_llm(
                whitelist=state["whitelist"],
                all_products=state.get("raw_products", []),
                original_keyword=state.get("vi_keyword", ""),
                pending_products=state.get("pending_products", []),
                blacklist=state["blacklist"],
                progress_offset=62,
            )

            async for chunk in final_chunks:
                yield chunk

            # ── 88% ── Hoàn thiện chi tiết
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "✍️ Đang hoàn thiện chi tiết báo cáo...", "progressPercent": 88}})

            # ── 94% ── Chuẩn bị trả về
            yield A2UIChunk(a2ui={"type": "a2ui_processing_status",
                                  "data": {"statusText": "📤 Đang chuẩn bị kết quả cuối cùng...",
                                           "progressPercent": 94}})

            # ── 100% ── Hoàn tất
            yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})

            state["phase"] = "DONE"
            yield {"state_update": state}
            return

        # Nếu chưa đủ điều kiện, đẩy sản phẩm tiếp theo lên UI
        if state["pending_products"]:
            next_prod = state["pending_products"].pop(0)
            # ── 1% ── Hiển thị sản phẩm tiếp theo
            yield A2UIChunk(
                a2ui={
                    "type": "a2ui_processing_status",
                    "data": {
                        "statusText": "👉 Sản phẩm tiếp theo...",
                        "progressPercent": 1,
                    },
                }
            )
            yield build_interactive_product_chunk(next_prod)

    except Exception as exc:
        traceback.print_exc()
        yield MessageChunk(content="Đã có lỗi xảy ra trong quá trình lọc sản phẩm.")
        state["phase"] = "ERROR"

    # -> FIX: Chốt State cuối cùng
    yield {"state_update": state}
