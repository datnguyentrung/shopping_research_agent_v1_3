# 📊 Hướng Dẫn Phân Bổ Progress Percent (%) trong Shopping Research Agent V1.3

## 🎯 Triết Lý Chung

- **Nguyên tắc Monotonicity**: Progress CHỈ TĂNG hoặc ĐỨNG IM, KHÔNG BAO GIỜ GIẢM
- **Phân bổ theo Time Complexity**: 
  - Logic nội bộ / Đọc State: **1-5%**
  - Query Database: **5-15%**
  - External API (Search, Phân tích): **15-40%**
  - LLM Stream (Suy nghĩ + Sinh text): **40-99%**

---

## 🔄 Các Phase Chính

### 1️⃣ **INITIAL (Tìm kiếm mới)**

```
1%      → Bằng dụ yêu cầu
5%      → Google Translate (sửa lỗi chính tả)
12%     → ML Classifier (phân loại danh mục)
18%     → Query DB lấy danh mục con
28%     → Tìm match danh mục con auto
32%     → Setup QUESTIONNAIRE | Hiển thị câu hỏi drilldown
38%     → Query DB xây dụng attribute questions
48%     → Setup search keyword + price filter
55%     → KHỞI ĐỘNG parallel searches (Vertex + Serper)
60%     → Hoàn tất lấy raw_products
72%     → BƯỚC LLM: Bắt đầu LLM ranking stream
↓ Dynamic iteration
88-95%  → Từng sản phẩm từ stream được thêm vào pending
96%     → Mẫu đầu tiên sân sàng → trả về UI
100%    → Hoàn tất toàn bộ pending_products
```

**Giải thích:**
- **1-28%**: Tất cả logic DB (translate, classify, query child categories, attributes)
- **32-55%**: Chuẩn bị search keywords, filter giá, setup parallel requests
- **60-72%**: Chờ Vertex AI + Serper API trả lại raw products
- **72-100%**: LLM Stream ranking - dùng **dynamic progress** để tăng nhẹ theo số sản phẩm nhận được

---

### 2️⃣ **CATEGORY_DRILLDOWN (Hỏi người dùng chọn chi tiết danh mục)**

```
3%      → Ghi nhận lựa chọn danh mục
8%      → Query DB lấy danh mục con
15%     → Hoàn tát query, chuẩn bị UI
22%     → Nếu có children: Hiển thị câu hỏi tiếp theo
28%     → Nếu leaf: Query attributes từ DB
38%     → Chuẩn bị câu hỏi đầu tiên
45%     → Khởi động search keyword + filter
55%     → Gọi parallel searches
68%     → Bắt đầu LLM ranking
↓ Dynamic iteration (prod_count % 2 == 0)
88-95%  → Pending products từ stream
96%     → Mẫu đầu tiên sân sàng
100%    → Hoàn tát
```

**Giải thích:**
- **3-28%**: DB queries (lấy child categories, attributes)
- **38-55%**: Search setup + parallel API gọi
- **68-100%**: LLM stream ranking (dynamic progress)

---

### 3️⃣ **QUESTIONNAIRE (User chọn attribute filters)**

```
3%      → Ghi nhận lựa chọn
12%     → Chuẩn bị câu hỏi tiếp theo (nếu có)
18%     → Xây dụng final search keyword từ answers
28%     → Căn chỉnh bộ lọc giá, keyword
35%     → Gọi parallel searches (Vertex + Serper)
48%     → Bắt đầu LLM ranking
↓ Dynamic iteration (prod_count % 2 == 0)
88-94%  → Stream ranking products
95%     → Mẫu đầu tiên sân sàng
100%    → Hoàn tát toàn bộ pending
```

**Giải thích:**
- **3-28%**: Logic xây dụng search keyword từ answers + price bounds parsing
- **35-48%**: Parallel API search
- **48-100%**: LLM ranking stream (dynamic tăng theo prod_count)

---

### 4️⃣ **PRODUCT_SWIPE (Người dùng vuốt thích/không thích sản phẩm)**

#### ✨ Sub-flow 1: "Thích" (Like)
```
2% → Ghi nhận "thích" → add vào whitelist
```

#### ❌ Sub-flow 2: "Không thích" (Dislike) - Nhánh "Giá quá cao"
```
3%  → Ghi nhận lý do
8%  → Lọc giá
25% → Báo cáo số loại bỏ
```

#### ❌ Sub-flow 3: "Không thích" - Nhánh "Thương hiệu"
```
3%  → Ghi nhận lý do
8%  → Lọc thương hiệu
25% → Báo cáo
```

#### ❌ Sub-flow 4: "Không thích" - Nhánh "Khác" (Re-search)
```
3%   → Ghi nhận lý do
6%   → Chuẩn bị phân tích LLM
12%  → Gọi analyze_dislike_reason (LLM)
18%  → Lọc sản phẩm dựa trên banned_keywords
22%  → Khởi động RE-SEARCH nếu context_change
38%  → Gọi parallel searches với keyword mới
52%  → Bắt đầu LLM ranking lại
↓ Dynamic iteration (prod_count % 3 == 0)
78-88% → Stream ranking products mới
88%  → ✅ Cập nhật danh sách mới
```

**Giải thích Re-search:**
- **3-22%**: Phân tích lý do (LLM analyze_dislike_reason)
- **22-38%**: Xây dụng keyword mới + setup search
- **38-88%**: Parallel search + LLM ranking (dynamic)

#### 🎉 Sub-flow 5: Điều kiện kết thúc vòng Swipe → FINAL_SUMMARY
```
32%  → Bắt đầu báo cáo (offset 32%)
42%  → Thu thập chi tiết sản phẩm
52%  → Nạp dữ liệu vào hệ thống phân tích
62%  → Phân tích đối chiếu giữa các mẫu
62-72% → LLM stream viết báo cáo (dynamic từ generate_final_summary_with_llm)
88%  → Hoàn thiện chi tiết
94%  → Chuẩn bị kết quả cuối
100% → ✅ Hoàn tát
```

#### 1️⃣ Hiển thị sản phẩm tiếp theo (nếu chưa đủ)
```
1% → Hiển thị sản phẩm tiếp theo từ pending_products
```

---

### 5️⃣ **FINAL_SUMMARY (Tích hợp trong PRODUCT_SWIPE khi kết thúc)**

```
offset+1%   → Khởi động tổng hợp
offset+8%   → Phân loại liked/rejected
offset+14%  → Xây dụng danh sách ứng viên
offset+18%  → Gọi LLM generate_final_summary_stream
↓ Dynamic iteration (stream_count % 10 == 0)
offset+18%-28% → AI viết báo cáo (tăng động)
offset+30%  → ✓ Hoàn tát báo cáo từ AI
```

**Giải thích:**
- **offset+1-14%**: Classify products, prepare candidate list
- **offset+18-30%**: LLM stream report writing (dynamic progress)

---

## 🎙️ Văn Phong Status Text

### ❌ Tránh (máy móc, chung chung):
- "Đang query DB"
- "Đang gọi API"
- "Đang xử lý"

### ✅ Dùng (sành sỏi, hình ảnh sinh động):
- "Lục lọi hàng ngàn kho hàng tìm '{keyword}'..."
- "🔍 Đang bóc tách từ khóa cần tránh..."
- "💭 AI đang suy ngẫm..."
- "✨ Mẫu hàng đầu tiên được AI chọn"
- "📦 Đã sắp xếp {count} sản phẩm..."
- "❤️ Ghi nhận bạn thích!"
- "👎 Ghi nhận: Bạn không thích vì..., Đang phân tích..."

---

## 📈 Dynamic Progress trong LLM Stream

Khi lặp qua `async for chunk in ranked_stream`, dùng công thức:

```python
prod_count = 0
base_percent = 72  # ví dụ: sau khi khởi động search

async for product in ranked_stream:
    prod_count += 1
    if prod_count % 3 == 0:  # Mỗi 3 sản phẩm, cập nhật progress 1 lần
        progress = min(94, base_percent + (prod_count // 3))
        yield A2UIChunk(a2ui={
            "type": "a2ui_processing_status",
            "data": {
                "statusText": f"📦 Đã sắp xếp {prod_count} sản phẩm...",
                "progressPercent": progress
            }
        })
```

**Lợi ích:**
- Không spam progress updates (chỉ cập nhật cứ 3 lần)
- Progress tăng chậm nhưng liên tục (mượt mà)
- Không vượt quá 94% (dành 5-6% cho "hoàn tát" và chuẩn bị UI)

---

## ✅ Checklist Khi Thêm Yield Progress

- [ ] Progress KHÔNG GIẢM (monotonic)
- [ ] % bắt đầu ≥ % cuối của bước trước
- [ ] Ghi chú logic tại sao bước này mất X%
- [ ] Dùng emoji + văn phong sành sỏi cho statusText
- [ ] LLM stream có dùng dynamic progress (prod_count % N == 0)
- [ ] % cuối = 100%, không phải 99% hay 98%

---

## 🎊 Kết Luận

Phân bổ % giúp:
1. **User Experience**: Người dùng thấy progress liên tục, không tưởng app bị treo
2. **Transparency**: Hiển thị đúng độ phức tạp của từng bước
3. **Engagement**: Văn phong sành sỏi + emoji tạo cảm giác thân thiện
4. **Monotonicity**: Đảm bảo progress không bao giờ giảm (bất kỳ nhánh nào)

