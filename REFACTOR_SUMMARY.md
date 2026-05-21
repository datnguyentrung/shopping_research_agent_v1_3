# 🎯 Refactor Summary - Shopping Research Agent V1.3 Progress Streaming

## 📋 Tổng Quan Công Việc

Refactored toàn bộ 5 files handlers + final_summary để bổ sung **chi tiết yield progress points** theo nguyên tắc:
1. **Monotonicity** - Progress chỉ tăng/đứng IM, KHÔNG giảm
2. **Time Complexity Allocation** - % phân bổ theo độ phức tạp tác vụ
3. **Smooth Loop Progress** - Dynamic progress cho LLM stream loops
4. **Engaging UX Text** - Văn phong sành sỏi thay vì máy móc

---

## 📝 Files Đã Refactor

### 1. **app/core/shopping_flow/handlers/initial.py** ✅
**Lý do**: Bổ sung chi tiết progress từ 1% → 100% cho toàn bộ luồng tìm kiếm mới

**Thay đổi chính**:
- `1%`: Bắt đầu phân tích yêu cầu
- `5%`: Google Translate (sửa lỗi chính tả)
- `12%`: ML Classifier (phân loại danh mục) - **External API**
- `18%`: Query DB lấy danh mục con - **DB Query**
- `28%`: Xây dụng attribute questions - **DB Query**
- `38%-55%`: Setup search keyword + parallel searches - **API Calls**
- `72%`: Bắt đầu LLM ranking - **LLM Stream**
- `72%-96%`: Dynamic progress trong ranked_stream loop
- `100%`: Hoàn tát

**Nguyên tắc áp dụng**:
- Logic nội bộ (1-5%): Translate, state parsing
- DB Query (5-28%): Category, attributes từ DB
- API Calls (38-60%): Vertex + Serper parallel search
- LLM Stream (72-100%): Dynamic progress tăng theo prod_count

---

### 2. **app/core/shopping_flow/handlers/category_drilldown.py** ✅
**Lý do**: Bổ sung progress cho nhánh "Người dùng chọn chi tiết danh mục"

**Thay đổi chính**:
- `3%`: Ghi nhận lựa chọn
- `8%`: Query DB lấy child categories
- `15%`: Hoàn tát query
- `22%`: Hiển thị câu hỏi drilldown (nếu có children)
- `28%-38%`: Setup search keyword
- `45%-55%`: API searches
- `68%-100%`: LLM ranking stream (dynamic)

**Lợi ích**: Tránh kỳ vọng % quá cao ở nhánh "query danh mục nhỏ" so với "search thực tế"

---

### 3. **app/core/shopping_flow/handlers/questionnaire.py** ✅
**Lý do**: Bổ sung progress cho nhánh "User điền attribute filters"

**Thay đổi chính**:
- `3%`: Ghi nhận lựa chọn attribute
- `12%`: Chuẩn bị câu hỏi tiếp theo (nếu có)
- `18%-28%`: Xây dụng final keyword từ answers
- `35%`: Parallel searches bắt đầu
- `48%-100%`: LLM ranking (dynamic tăng)

**Nguyên tắc**: Progress từ 3% → 35% (setup), 35% → 48% (API gọi), 48% → 100% (LLM stream)

---

### 4. **app/core/shopping_flow/handlers/product_swipe.py** ✅
**Lý do**: Bổ sung progress cho các sub-flows (like, dislike, re-search, final summary)

**Thay đổi chính**:

#### 🟩 Sub-flow "Thích"
- `2%`: Ghi nhận thích

#### 🟥 Sub-flow "Không thích" - Các nhánh:
1. **Giá quá cao**: 3% → 8% (lọc) → 25% (báo cáo)
2. **Thương hiệu**: 3% → 8% (lọc) → 25% (báo cáo)
3. **Khác (Re-search)**: 
   - 3% → 6%: Chuẩn bị phân tích
   - 6% → 12%: Gọi LLM analyze_dislike_reason
   - 12% → 18%: Lọc sản phẩm
   - 18% → 22%: Khởi động re-search (nếu context thay đổi)
   - 38% → 88%: Parallel search + LLM ranking (dynamic)

#### 🟧 Kết thúc vòng Swipe (Final Summary):
- 32% → 42% → 52% → 62% → 72% (LLM stream) → 88% → 94% → 100%

**Quan trọng**: Một flow có nhiều nhánh, nhưng progress **LUÔN** từ 1-2% → max 88% (để dành phần cuối cho "Done")

---

### 5. **app/core/shopping_flow/final_summary.py** ✅
**Lý do**: Bổ sung chi tiết progress trong generate_final_summary_with_llm

**Thay đổi chính**:
- `offset+1%`: Khởi động tổng hợp
- `offset+8%`: Phân loại liked/rejected
- `offset+14%`: Xây dụng danh sách ứng viên
- `offset+18%-28%`: LLM stream viết báo cáo (có dynamic progress `stream_count % 10 == 0`)
- `offset+30%`: Hoàn tát

**Lợi ích**: Dùng `progress_offset` parameter để tích hợp liền mạch với product_swipe.py (offset+62% bắt đầu)

---

## 🎨 Văn Phong Status Text

### Trước (Cũ):
```
"Đang phân tích..."
"Đang query DB"
"Đang gọi API"
"Đang xử lý..."
```

### Sau (Mới):
```
"🔍 Đang bóc tách yêu cầu của bạn..."
"💭 AI đang suy ngẫm..."
"✨ Mẫu hàng đầu tiên được AI chọn"
"📦 Đã sắp xếp {count} sản phẩm..."
"❤️ Ghi nhận bạn thích sản phẩm này!"
"👎 Ghi nhận: Bạn không thích vì..., Đang phân tích..."
"🔄 Tiêu chí thay đổi: Cần tìm kiếm lại..."
"🧠 AI đang suy ngẫm để viết báo cáo..."
```

---

## ✅ Kiểm Tra Quality Gate

- [x] **Monotonicity**: Tất cả progress từ các nhánh đều không giảm
- [x] **Time Complexity**: 
  - Logic (1-5%), DB (5-28%), API (28-60%), LLM (60-100%)
- [x] **Dynamic Loop Progress**: 
  - `prod_count % 2-3 == 0` để cập nhật loop progress
  - `stream_count % 10 == 0` cho LLM text stream
- [x] **FSM Logic Preserved**: KHÔNG thay đổi bất kỳ logic nghiệp vụ nào
- [x] **State Chốt Points**: Luôn `yield {"state_update": state}` ở cuối
- [x] **Error Handling**: Exception → phase = "ERROR" được giữ nguyên

---

## 🧪 Cách Kiểm Tra

### 1. Chạy theo bất kỳ flow nào và quan sát progress:
```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "áo khoác nam", "sessionId": "tests-123"}'
```

### 2. Kiểm tra monotonicity:
- Canh lại mỗi thao tác (swipe like/dislike)
- Progress PHẢI từ 1% → 100%, không bao giờ giảm

### 3. Debug với TRACE_ENABLED:
```bash
# .env
TRACE_ENABLED=true
```
Sẽ in chi tiết progress trên logs

---

## 📊 Bảng So Sánh (Trước vs Sau)

| Phase | Trước | Sau |
|-------|-------|-----|
| **INITIAL** | 30% → 40% → 60% → 90% → 100% | 1% → 5% → 12% → 28% → 55% → 72% → 100% |
| **CATEGORY_DRILLDOWN** | 5% → 15% → 25% → 35% → 50% → 85% → 100% | 3% → 8% → 15% → 28% → 45% → 68% → 100% |
| **QUESTIONNAIRE** | 10% → 30% → 50% → 70% → 85% → 100% | 3% → 12% → 28% → 35% → 48% → 100% |
| **PRODUCT_SWIPE (like)** | - | 2% |
| **PRODUCT_SWIPE (dislike, short)** | 3% → 8% → 20% | 3% → 8% → 25% |
| **PRODUCT_SWIPE (re-search)** | 30% → 60% → 85% → 100% | 22% → 38% → 52% → 88% |
| **FINAL_SUMMARY** | 30% → 35% → 40% → 46% → 76% → 82% → 88% → 94% → Done | offset+1% → +18% (LLM) → +30% |

---

## 🎯 Lợi Ích Chính

1. **Trải Nghiệm Người Dùng**: Progress mượt mà, chi tiết, không bao giờ quay lùi
2. **Tâm Lý Học**: Văn phong sành sỏi + emoji tạo cảm giác AI "thông minh"
3. **Transparency**: User biết hệ thống đang làm gì (phân tích, tìm kiếm, xếp hạng?)
4. **Maintainability**: Tất cả % có comment giải thích tại sao là con số đó

---

## 📌 Ghi Chú Kỹ Thuật

### Không Tính % Cho:
- `yield {"state_update": state}` - chỉ cập nhật state, không hiển thị UI
- Exception handlers - progress dừng tại "ERROR"
- Return sớm - không cần yield 100% nếu early exit

### Cơ Chế Dynamic Progress:
```python
prod_count = 0
base_percent = 72

async for product in ranked_stream:
    prod_count += 1
    if prod_count % 3 == 0:  # Mỗi 3 sản phẩm
        progress = min(95, base_percent + (prod_count // 3))
        # Không spam, mượt mà, không vượt 95%
```

### Tích Hợp progress_offset:
```python
# product_swipe.py
final_chunks = generate_final_summary_with_llm(
    ...,
    progress_offset=62,  # FINAL_SUMMARY bắt từ 62%
)
```

---

## 🚀 Kế Tiếp (Optional Enhancements)

1. **Backend Metrics**: Track trung bình thời gian mỗi phase để điều chỉnh % nếu cần
2. **A/B Testing**: Test 2 bản έχει văn phong khác nhau để xem cái nào engagement cao hơn
3. **Per-Source Timing**: Vertex AI vs Serper vs Serper có tốc độ khác nhau → điều chỉnh % setup
4. **Cancelable Tasks**: Cho user cancel giữa chừng (break loop nếu progress > 95%)

---

## ✨ Kết Luận

Refactor này giữ **100% logic FSM** không đổi, chỉ **thêm yield points** để tăng UX/engagement. Tất cả code vẫn production-ready, testable, và có thể điều chỉnh forward-compatible.

