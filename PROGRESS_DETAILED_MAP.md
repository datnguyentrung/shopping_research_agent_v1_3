# 📊 Bản Đồ Chi Tiết Progress Percent - Shopping Research Agent V1.3

## 🎬 PHASE 1: INITIAL (Tìm Kiếm Mới)

```
┌────────────────────────────────────────────────────────────────────────┐
│ INITIAL NODE - Từ keyword → Mẫu đầu tiên hiển thị                    │
└────────────────────────────────────────────────────────────────────────┘

    1% ─ Bắt đầu phân tích yêu cầu
         └─ statusText: "Đang bóc tách yêu cầu của bạn..."
         └─ Task: State init, logging,  parse message
         └─ Duration: <100ms

    5% ─ Google Translate (sửa lỗi chính tả + song ngữ)
         └─ statusText: "Đang sửa lỗi chính tả và dịch sang tiếng Anh..."
         └─ Task: await get_bilingual_and_correct(user_message)
         └─ Duration: 1-2s (External API call)
         └─ **Scope**: EXTERNAL API (15-40% zone, nhưng nhanh → 5%)

    12% ─ ML Classifier (phân loại danh mục)
          └─ statusText: "Đã nhận diện từ khóa: '{vi_keyword}'. Đang dò tìm danh mục..."
          └─ Task: classify_keyword_topk(en_keyword, k=1)
          └─ Duration: 800ms-1s
          └─ **Scope**: EXTERNAL API (ML model inference)

    18% ─ Query DB lấy danh mục con (first level children)
          └─ statusText: "Tìm thấy danh mục, đang tìm nhóm chi tiết..."
          └─ Task: get_child_categories(top_cat["category_id"], trace_id)
          └─ Duration: 200-400ms
          └─ **Scope**: DB QUERY

    28% ─ Tìm match được danh mục con tự động (nếu có)
          └─ statusText: "Tìm thấy {len(options)} loại. Đang căn chỉnh..."
          └─ Task: String matching, setup for UI or search
          └─ Duration: <100ms

    ❓ Điểm phân nhánh: Có children không?
       YES → 32%+ → CATEGORY_DRILLDOWN flow (show UI question)
       NO  → 38%+ → tiếp tục xây dựng attribute questions để QUESTIONNAIRE

    38% ─ Xây dựng attribute questions từ DB
          └─ statusText: "Đang khai thác các tiêu chí lọc (màu, size, thương hiệu...)..."
          └─ Task: build_attribute_questions(state["current_category_id"], trace_id)
          └─ Duration: 300-500ms
          └─ **Scope**: DB QUERY (CTE recursive)

    48% ─ Chuẩn bị câu hỏi đầu tiên hoặc setup search
          └─ statusText: "Tìm thấy {len} tiêu chí. Chuẩn bị hỏi bạn..."
          └─ Task: Pop first attr → show questionnaire OR xây dựng search keyword
          └─ Duration: <100ms

    ❓ Nếu có attributes → QUESTIONNAIRE flow (show UI question, RETURN)
       Nếu KHÔNG → tiếp tục search luôn

    55% ─ Thiết lập search keyword + price filter
          └─ statusText: "Sắp bắt đầu tìm kiếm. Đang thiết lập thông số..."
          └─ Task: Build final_search_keyword, parse price bounds
          └─ Duration: <50ms

    60% ─ Khởi động parallel searches (Vertex AI + Serper)
          └─ statusText: "Lục lọi hàng ngàn kho hàng tìm '{leaf_category_name}'..."
          └─ Task: await run_parallel_searches(keyword_vi, min, max)
          └─ Duration: 3-5s (Vertex + Serper async)
          └─ **Scope**: EXTERNAL API (15-40% zone, tuy nhiên song song → 60%)

    72% ─ BƯỚC LLM: Khởi động LLM ranking stream
          └─ statusText: "Tìm thấy {len(raw_products)} sản phẩm. AI đang chấm điểm..."
          └─ Task: await search_and_prepare_stream(...) → rank_products_with_llm_stream()
          └─ Duration: 2-4s (LLM streaming)
          └─ **Scope**: LLM STREAM (40-99% zone)

    72% → 96% ─ Dynamic Loop: Stream LLM-ranked products
                   └─ Loop: async for product in ranked_stream:
                   └─ Rule: prod_count % 3 == 0 → cập nhật progress
                   └─ Progress formula:
                      progress = min(95, 72 + (prod_count // 3))
                   └─ VD:
                      prod_count=0: no update
                      prod_count=3: progress=73
                      prod_count=6: progress=74
                      prod_count=9: progress=75
                      ...
                      prod_count=66: progress=94
                   └─ statusText: "📦 Đã sắp xếp {prod_count} sản phẩm..."

    96% ─ Mẫu đầu tiên sân sàng → trả về UI
          └─ statusText: "✨ AI đã chọn ra mẫu hàng đầu tiên..."
          └─ Task: yield build_interactive_product_chunk(first_prod)
          └─ Duration: <50ms

    100% ─ Hoàn tất toàn bộ pending_products
           └─ statusText: "🎉 Xong! Tìm thấy {total} ứng viên."
           └─ Task: Set state["phase"] = "PRODUCT_SWIPE"
           └─ Duration: <50ms
           └─ RETURN to ORCHESTRATOR

    **SUMMARY INITIAL PHASE**:
    ├─ Logic (1-28%): 27% = translate + classify + DB queries
    ├─ API Search (60%): 32% = parallel Vertex + Serper
    ├─ LLM Stream (72-100%): 28% = ranking stream
    └─ Total: 100% monotonic, no backtrack
```

---

## 🎬 PHASE 2: CATEGORY_DRILLDOWN (Hỏi người dùng chọn chi tiết danh mục)

```
┌────────────────────────────────────────────────────────────────────────┐
│ CATEGORY_DRILLDOWN NODE - Người dùng chọn ngành hàng nhỏ hơn          │
└────────────────────────────────────────────────────────────────────────┘

Trigger: SUBMIT_SURVEY event từ UI (user chọn một danh mục con)

    3% ─ Ghi nhận + validate lựa chọn danh mục
         └─ statusText: "✅ Ghi nhận: '{selected_name}'. Đang tra cứu..."
         └─ Task: Extract selected_name từ hidden_payload, lookup ID trong category_map
         └─ Duration: <50ms

    8% ─ Query DB lấy child categories cấp tiếp theo
         └─ statusText: "Đang khai thác nhóm sản phẩm con..."
         └─ Task: get_child_categories(selected_cat_id, trace_id)
         └─ Duration: 200-400ms
         └─ **Scope**: DB QUERY

    15% ─ Hoàn tất query + random sample (nếu > 4)
          └─ statusText: "Tìm thấy {len(options)} nhóm sản phẩm con. Chuẩn bị hiển thị..."
          └─ Task: if len(options) > 4: random.sample(options, 4)
          └─ Duration: <50ms

    ❓ Điểm phân nhánh: Còn children không?
       YES → 22%+ → Hiển thị câu hỏi "Loại nào?" (QUESTIONNAIRE UI)
              └─ Sau đó RETURN
       NO  → 28%+ → Đây là LEAF category, tiếp tục xây dựng search

    22% ─ [Nếu có children] Chuẩn bị + yield questionnaire UI
          └─ statusText: "Chuẩn bị giao diện lựa chọn chi tiết..."
          └─ Task: build_questionnaire_chunk(next_question, allow_multiple=False)
          └─ Duration: <50ms
          └─ **RETURN** (state update trước khi return)

    28% ─ [Nếu LEAF] Xây dựng attribute questions từ DB
          └─ statusText: "✓ Xác định danh mục: '{selected_name}'. Đang tìm tiêu chí lọc..."
          └─ Task: build_attribute_questions(selected_cat_id, trace_id)
          └─ Duration: 300-500ms
          └─ **Scope**: DB QUERY

    38% ─ [Nếu có attributes] Chuẩn bị câu hỏi đầu tiên
          └─ statusText: "Tìm thấy {len} tiêu chí. Chuẩn bị hỏi bạn..."
          └─ Task: Pop first attr, set state["phase"] = "QUESTIONNAIRE"
          └─ Duration: <50ms
          └─ **RETURN** (state update trước khi return)

    45% ─ [Nếu KHÔNG có attributes] Bắt đầu search keywords setup
          └─ statusText: "Đã thu thập đủ thông tin. Đang thiết lập bộ lọc..."
          └─ Task: _build_search_keyword_from_state(state)
          └─ Duration: <50ms

    55% ─ Bắt đầu parallel searches
          └─ statusText: "Lục lọi hàng ngàn kho hàng tìm '{final_keyword}'..."
          └─ Task: await run_parallel_searches(...)
          └─ Duration: 3-5s
          └─ **Scope**: EXTERNAL API

    68% ─ BƯỚC LLM: Khởi động LLM ranking
          └─ statusText: "Tìm thấy {len} sản phẩm. AI đang chấm điểm..."
          └─ Task: await search_and_prepare_stream(...) → rank stream
          └─ Duration: 2-4s
          └─ **Scope**: LLM STREAM

    68% → 96% ─ Dynamic Loop: Stream ranked products
                   └─ Rule: prod_count % 2 == 0 → update
                   └─ progress = min(95, 68 + (prod_count // 2))

    96% ─ Mẫu đầu tiên sân sàng
          └─ statusText: "✨ Mẫu hàng đầu tiên được AI chọn..."
          └─ Task: yield build_interactive_product_chunk(first_prod)
          └─ Duration: <50ms

    100% ─ Hoàn tát → PRODUCT_SWIPE phase
           └─ statusText: "🎉 Xong! Tìm thấy {total} ứng viên."
           └─ RETURN

    **SUMMARY CATEGORY_DRILLDOWN PHASE**:
    ├─ Logic + DB (3-38%): 35% = validate + DB queries
    ├─ API Search (55%): 13% = parallel search requests
    ├─ LLM Stream (68-100%): 32% = ranking stream
    └─ Total: 100% (hoặc return sớm)
```

---

## 🎬 PHASE 3: QUESTIONNAIRE (User điền attribute filters)

```
┌────────────────────────────────────────────────────────────────────────┐
│ QUESTIONNAIRE NODE - Người dùng trả lời câu hỏi về thuộc tính         │
└────────────────────────────────────────────────────────────────────────┘

Trigger: SUBMIT_SURVEY hoặc SKIP_SURVEY event

    3% ─ Ghi nhận + validate attribute selection
         └─ statusText: "{last_options_text}" (hiển thị lựa chọn)
         └─ Task: Extract data từ hidden_payload, append to state["answers"]
         └─ Duration: <50ms

    12% ─ Chuẩn bị câu hỏi tiếp theo (nếu có)
          └─ statusText: "✓ Đã lưu. Chuẩn bị câu hỏi tiếp theo..."
          └─ Task: Pop next_attr từ state["attributes"]
          └─ Duration: <50ms
          └─ **IF có next question**: yield questionnaire UI và RETURN
          └─ **IF không**: tiếp tục → 18%+

    18% ─ Xây dựng final search keyword từ tất cả answers
          └─ statusText: "Đã thu thập {len(answers)} tiêu chí. Chuẩn bị tìm kiếm..."
          └─ Task: build_search_keyword_from_answers(state)
          └─ Duration: <50ms
          └─ Includes: price bounds parsing

    28% ─ Căn chỉnh bộ lọc giá + keyword
          └─ statusText: "Đang căn chỉnh thông số: Tìm '{final_keyword}'..."
          └─ Task: Validate min_price, max_price, final_search_keyword
          └─ Duration: <50ms

    35% ─ Gọi parallel searches
          └─ statusText: "Lục lọi hàng ngàn kho hàng với bộ tiêu chí của bạn..."
          └─ Task: await run_parallel_searches(...)
          └─ Duration: 3-5s
          └─ **Scope**: EXTERNAL API

    48% ─ BƯỚC LLM: Khởi động LLM ranking
          └─ statusText: "Tìm thấy {len} sản phẩm. AI đang chấm điểm từng mẫu..."
          └─ Task: await search_and_prepare_stream(...)
          └─ Duration: 2-4s
          └─ **Scope**: LLM STREAM

    48% → 95% ─ Dynamic Loop: Stream ranked products
                   └─ Rule: prod_count % 2 == 0 → update
                   └─ progress = min(94, 48 + (prod_count // 2))

    95% ─ Mẫu đầu tiên sân sàng
          └─ statusText: "✨ Mẫu hàng đầu tiên được AI chọn..."

    100% ─ Hoàn tát → PRODUCT_SWIPE phase
           └─ statusText: "🎉 Xong! Tìm thấy {total} ứng viên."

    **SUMMARY QUESTIONNAIRE PHASE**:
    ├─ Logic (3-35%): 32% = validate + keyword building
    ├─ API Search (35%): 13% = wait for parallel search
    ├─ LLM Stream (48-100%): 52% = ranking stream + first product display
    └─ Total: 100%
```

---

## 🎬 PHASE 4: PRODUCT_SWIPE (Vuốt thích/không thích)

```
┌────────────────────────────────────────────────────────────────────────┐
│ PRODUCT_SWIPE NODE - Người dùng vuốt thích/không thích sản phẩm      │
└────────────────────────────────────────────────────────────────────────┘

Trigger: PRODUCT_FEEDBACK event (decision: "like" or "dislike")

BRANCH A: LIKE (Người dùng thích)
┌──────────────────────────────────────────────────────────────────┐
    2% ─ Ghi nhận "thích"
         └─ statusText: "❤️ Ghi nhận bạn thích sản phẩm này!"
         └─ Task: state["whitelist"].append(data)
         └─ Duration: <50ms
         └─ → Kiểm tra điều kiện kết thúc (line 279) → tiếp tục hoặc FINAL_SUMMARY
└──────────────────────────────────────────────────────────────────┘

BRANCH B: DISLIKE - (Người dùng không thích)
┌──────────────────────────────────────────────────────────────────┐

SUB-BRANCH B1: "Giá quá cao"
    3% ─ Ghi nhận lý do
         └─ statusText: "👎 Ghi nhận: Bạn không thích vì 'Giá quá cao'..."
    8% ─ Lọc sản phẩm: price_current <= rejected_price * 1.1
         └─ statusText: "📊 Đang lọc sản phẩm với giá thấp hơn..."
    25% ─ Báo cáo
         └─ statusText: "✓ Loại bỏ {dropped} sản phẩm không phù hợp."

SUB-BRANCH B2: "Thương hiệu"
    3% ─ Ghi nhận lý do
    8% ─ Lọc brand: chỉ giữ products với brand ≠ rejected_brand
         └─ statusText: "🏷️ Đang bỏ các sản phẩm từ thương hiệu..."
    25% ─ Báo cáo

SUB-BRANCH B3: "Khác" hoặc custom reason (RE-SEARCH BRANCH)
    3% ─ Ghi nhận lý do
         └─ statusText: "👎 Ghi nhận: ..., Đang phân tích..."
    6% ─ Chuẩn bị phân tích LLM
         └─ statusText: "🔍 AI đang bóc tách từ khóa cần tránh..."
    12% ─ Gọi LLM analyze_dislike_reason
          └─ statusText: "💭 AI đang suy ngẫm: Để tìm sản phẩm tốt hơn..."
          └─ Task: await analyze_dislike_reason(reason)
          └─ Duration: 1-2s (LLM call)
    18% ─ Lọc sản phẩm dựa trên banned_keywords
          └─ statusText: "🚫 Loại bỏ sản phẩm chứa: {keywords[:3]}..."
    22% ─ [NẾU context thay đổi] Khởi động RE-SEARCH
          └─ statusText: "🔄 Tiêu chí thay đổi: '{preferred[0]}'. Tìm kiếm lại..."
          └─ Task: Check _keywords_change_context(preferred_keywords, state)
          └─ Duration: next 66% cho re-search flow

    ├─ 22% → 38%: Setup new search keywords + parallel API calls
    │          └─ statusText: "🔍 Lục lọi kho hàng với tiêu chí mới..."
    │
    ├─ 38% → 52%: Start LLM ranking với keyword mới
    │          └─ statusText: "⭐ AI đang chấm điểm ứng viên mới..."
    │
    ├─ 52% → 88%: Dynamic loop LLM stream (prod_count % 3 == 0)
    │          └─ progress = min(78, 52 + (prod_count // 3))
    │          └─ statusText: "📦 Đã sắp xếp {prod_count} sản phẩm..."
    │
    └─ 88%: Cập nhật danh sách mới
             └─ statusText: "✅ Cập nhật danh sách thành công!"

└──────────────────────────────────────────────────────────────────┘

ĐIỂM KIỂM TRA: total_swipes ≥ 5 hoặc len(whitelist) ≥ 5 hoặc pending < 1?
   ❌ NO: Tiếp tục → Hiển thị sản phẩm tiếp theo từ pending_products
           └─ 1% ─ statusText: "👉 Sản phẩm tiếp theo..."
           └─ Task: yield build_interactive_product_chunk(next_prod)
   
   ✅ YES: Chuyển → FINAL_SUMMARY phase
           └─ 32% ─ statusText: "📋 Bạn thích {count} sản phẩm. Bắt đầu tổng hợp..."
           └─ ... (xem PHASE 5)

    **SUMMARY PRODUCT_SWIPE PHASE**:
    ├─ Like: 2%
    ├─ Dislike (short): 3-25%
    ├─ Dislike (re-search): 3-88%
    ├─ Next product: 1%
    ├─ Final summary entry: 32% (actually handled by next phase)
    └─ Each branch maintains monotonicity
```

---

## 🎬 PHASE 5: FINAL_SUMMARY (Tích hợp trong product_swipe finalize)

```
┌────────────────────────────────────────────────────────────────────────┐
│ FINAL_SUMMARY - Tổng hợp báo cáo mua sắm (phần của product_swipe)   │
└────────────────────────────────────────────────────────────────────────┘

Trigger: Khi len(whitelist) ≥ 5 hoặc total_swipes ≥ 5 hoặc no pending left

Progress offset điểm vào là product_swipe line 281: progress_offset=62

    offset+1% (=63%) ─ Khởi động tổng hợp báo cáo
                       └─ statusText: "📋 Bắt đầu tổng hợp {count} sản phẩm..."
                       └─ Task: Prepare whitelist_ids, blacklist_ids

    offset+8% (=70%) ─ Phân loại liked/rejected products
                       └─ statusText: "🔍 Phân loại: {liked} mẫu yêu thích, {disliked} bỏ qua..."
                       └─ Task: Loop through all_products, classify theo ID

    offset+14% (=76%) ─ Xây dựng danh sách ứng viên (candidates)
                        └─ statusText: "✅ Chọn ra {count} ứng viên tiềm năng..."
                        └─ Task: Build ai_candidates từ pending_products + top-rated products

    offset+18% (=80%) ─ Khởi động LLM generate_final_summary_stream
                        └─ statusText: "🧠 AI đang suy ngẫm để viết báo cáo..."
                        └─ Task: Build prompt + LLM stream
                        └─ Duration: 3-6s (LLM thinking + generation)

    offset+18% → offset+28% (=80% → 90%) ─ Dynamic Loop: LLM text streaming
                                            └─ Rule: stream_count % 10 == 0 → update
                                            └─ progress = min(progress_offset + 28, 
                                                               progress_offset + 18 + (stream_count // 5))
                                            └─ statusText: "✍️ AI đang viết... ({count} đoạn)"
                                            └─ Duration: LLM stream output

    offset+30% (=92%) ─ Hoàn tát báo cáo từ AI
                        └─ statusText: "✓ Hoàn tát báo cáo từ AI!"

    [Back to product_swipe]

    94% ─ Chuẩn bị kết quả cuối cùng
          └─ statusText: "📤 Đang chuẩn bị kết quả cuối cùng..."

    100% ─ Done signal + state["phase"] = "DONE"
           └─ yield A2UIChunk(a2ui={"type": "a2ui_done", "data": {}})

    **SUMMARY FINAL_SUMMARY PHASE**:
    ├─ Logic (offset+1-14%): 13% = classify + candidates build
    ├─ LLM Thinking (offset+18%): 2% = prompt build + LLM init
    ├─ LLM Stream (offset+18-30%): 12% = dynamic progress text streaming
    ├─ Finalize (94-100%): 6% = done signal + wrapping
    └─ Total: offset+62% → 100%
```

---

## 📊 Bảng Quick Reference

| Phase | Min % | Max % | Key Milestones |
|-------|-------|-------|-----------------|
| INITIAL | 1% | 100% | 5% (Translate) → 12% (Classify) → 60% (Search) → 72% (LLM) |
| CATEGORY_DRILLDOWN | 3% | 100% | 8% (DB Query) → 55% (Search) → 68% (LLM) |
| QUESTIONNAIRE | 3% | 100% | 18% (Keyword build) → 35% (Search) → 48% (LLM) |
| PRODUCT_SWIPE (like) | 2% | 2% | Instant |
| PRODUCT_SWIPE (dislike-short) | 3% | 25% | 8% (Filter) → 25% (Report) |
| PRODUCT_SWIPE (re-search) | 3% | 88% | 12% (LLM analyze) → 38% (Search) → 88% (Stream) |
| FINAL_SUMMARY | 62% | 100% | 80% (LLM start) → 92% (LLM end) |

---

## 🎯 Các Con Số Quan Trọng

```
API + LLM Breakdown:
├─ Google Translate: 1-2s (5%)
├─ ML Classifier: 0.8-1s (12%)
├─ DB Queries: 0.2-0.5s each (5-15% zone)
├─ Vertex + Serper parallel: 3-5s (55-60%)
└─ LLM Ranking Stream: 2-4s (72%+)

Total pipeline: 10-20s (depending on LLM latency)

Dynamic Progress Adjustment:
├─ prod_count: mỗi 2-3 sản phẩm → +1%
├─ stream_count: mỗi 10 đoạn text → +1-2%
└─ Max: 94% (để dành 6% cho "Done")
```

---

## ✅ Monotonicity Verification

✓ INITIAL: 1 → 5 → 12 → 18 → 28 → 38 → 48 → 55 → 60 → 72 → [72-96] → 100 
✓ CATEGORY_DRILLDOWN: 3 → 8 → 15 → [22 OR 28] → [38 OR 55] → 68 → 100
✓ QUESTIONNAIRE: 3 → 12 → 18 → 28 → 35 → 48 → [48-95] → 100
✓ PRODUCT_SWIPE: 1-2-3 → [3-88] → 1 (next product) OR 32% (final summary entry)
✓ FINAL_SUMMARY: offset+1 → +8 → +14 → +18 → [+18-28] → +30 → .. → 100

All branches: **NO backtrack, only forward or stay**

