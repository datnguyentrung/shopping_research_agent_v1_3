
from app.core.shopping_flow.ui_chunks import build_interactive_product_chunk
from app.memory.session_store import clear_session
from app.core.shopping_flow.final_summary import generate_final_summary_with_llm

from app.models.ui_chunks import A2UIChunk, MessageChunk
from app.services.analyze_dislike_reason_service import analyze_dislike_reason


async def handle_product_swipe(session: dict, session_id: str, action: str, data):
    if action != "PRODUCT_FEEDBACK":
        return

    if isinstance(data, dict):
        decision = data.get("decision", "").lower()
        if decision == "like":
            session["whitelist"].append(data)
        elif decision == "dislike":
            session["blacklist"].append(data)
            reason = data.get("reason", "")
            rejected_product = data.get("product", {})

            if reason and session.get("pending_products"):
                original_count = len(session["pending_products"])

                # ── 3% ──
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
                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        if current_price == 0 or float(p_dict.get("price_current", 0)) <= (current_price * 1.1):
                            filtered_products.append(p)

                elif reason == "Thương hiệu":
                    bad_brand = rejected_product.get("brand", "").lower() if rejected_product else ""
                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        if not bad_brand or p_dict.get("brand", "").lower() != bad_brand:
                            filtered_products.append(p)

                elif reason == "Khác" or reason not in ["Không hợp phong cách", "Tính năng"]:
                    # ── 8%: Trước khi gọi AI trích xuất ngữ nghĩa ──
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

                    # Luu preferred_keywords vao session de supplementary search su dung
                    if not session.get("preferred_keywords"):
                        session["preferred_keywords"] = []
                    session["preferred_keywords"].extend(preferred_keywords)

                    # ── 14%: Sau AI, trước khi lọc danh sách ──
                    yield A2UIChunk(
                        a2ui={
                            "type": "a2ui_processing_status",
                            "data": {
                                "statusText": "Đang rà soát và gạch tên các sản phẩm không phù hợp...",
                                "progressPercent": 14,
                            },
                        }
                    )

                    for p in session["pending_products"]:
                        p_dict = p.model_dump(by_alias=False) if hasattr(p, "model_dump") else p
                        p_text = f"{p_dict.get('name', '')}".lower()
                        is_banned = any(kw.lower() in p_text for kw in banned_keywords if kw.strip())
                        if not is_banned:
                            filtered_products.append(p)
                else:
                    filtered_products = session["pending_products"]

                if not filtered_products and session.get("pending_products"):
                    filtered_products = session["pending_products"]

                if filtered_products:
                    session["pending_products"] = filtered_products

                if len(filtered_products) < original_count:
                    dropped = original_count - len(filtered_products)

                    # ── 20%: Đã lọc xong ──
                    yield A2UIChunk(
                        a2ui={
                            "type": "a2ui_processing_status",
                            "data": {
                                "statusText": f"Đã loại bỏ {dropped} sản phẩm không phù hợp. Đang sắp xếp lại danh sách...",
                                "progressPercent": 20,
                            },
                        }
                    )

    total_swipes = len(session.get("whitelist", [])) + len(session.get("blacklist", []))

    if len(session["whitelist"]) >= 5 or total_swipes >= 5 or len(session["pending_products"]) < 1:
        if not session["whitelist"]:
            yield MessageChunk(
                content="Có vẻ bạn chưa ưng ý sản phẩm nào trong lô này. Hãy thử ấn Bắt đầu mới và mô tả lại nhu cầu cụ thể hơn nhé!")
            yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
            clear_session(session_id)
            return

        session["phase"] = "FINAL_SUMMARY"

        # ═══════════════════════════════════════════════════════
        #  BÁO CÁO TỔNG HỢP — tiếp nối tuyến tính từ swipe (30→100)
        # ═══════════════════════════════════════════════════════

        # ── 30% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": f"Bạn đã ưng ý {len(session['whitelist'])} mẫu. Đang bắt đầu tổng hợp báo cáo...",
                    "progressPercent": 30,
                },
            }
        )

        # ── 35% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang thu thập thông tin chi tiết các mẫu bạn đã chọn...",
                    "progressPercent": 35,
                },
            }
        )

        # ── 40% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang nạp danh sách sản phẩm vào hệ thống phân tích...",
                    "progressPercent": 40,
                },
            }
        )

        # ── 46% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang phân tích đối chiếu giữa các sản phẩm...",
                    "progressPercent": 46,
                },
            }
        )

        final_chunks = generate_final_summary_with_llm(
            whitelist=session["whitelist"],
            all_products=session.get("raw_products", []),
            original_keyword=session.get("vi_keyword", ""),
            pending_products=session.get("pending_products", []),
            blacklist=session["blacklist"],
            progress_offset=46,
        )

        async for chunk in final_chunks:
            yield chunk

        # ── 76% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Sắp hoàn thành báo cáo tổng hợp...",
                    "progressPercent": 76,
                },
            }
        )

        # ── 82% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang hoàn thiện chi tiết báo cáo...",
                    "progressPercent": 82,
                },
            }
        )

        # ── 88% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đã hoàn thành báo cáo tổng hợp!",
                    "progressPercent": 88,
                },
            }
        )

        # ── 94% ──
        yield A2UIChunk(
            a2ui={
                "type": "a2ui_processing_status",
                "data": {
                    "statusText": "Đang tải kết quả cuối cùng cho bạn...",
                    "progressPercent": 94,
                },
            }
        )

        yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})
        clear_session(session_id)
        return

    next_prod = session["pending_products"].pop(0)
    yield build_interactive_product_chunk(next_prod)