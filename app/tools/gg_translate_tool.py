import os

from google.cloud import translate_v2 as translate

from app.core.config import settings

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS


async def get_bilingual_and_correct(text: str) -> dict:
    """
    Hàm nhận input (có thể sai chính tả), trả về dict chứa bản chuẩn EN và VI.
    """
    # Khởi tạo client v2 (Phương án 3)
    client = translate.Client()

    # Bước 1: Gọi API dịch thử sang tiếng Anh
    # Mục đích: Vừa lấy bản tiếng Anh, vừa để Google cho biết ngôn ngữ gốc là gì
    first_pass = client.translate(text, target_language='en')
    detected_lang = first_pass['detectedSourceLanguage']

    if detected_lang == 'vi':
        # --- TRƯỜNG HỢP INPUT LÀ TIẾNG VIỆT (VD: "áo khócac") ---
        # 1. Bản tiếng Anh chuẩn đã có từ first_pass
        en_text = first_pass['translatedText']

        # 2. Dịch ngược tiếng Anh chuẩn về tiếng Việt để sửa lỗi chính tả
        vi_pass = client.translate(en_text, target_language='vi')
        vi_text = vi_pass['translatedText']

    else:
        # --- TRƯỜNG HỢP INPUT LÀ TIẾNG ANH (VD: "shoee") ---
        # 1. Dịch text gốc sang tiếng Việt để lấy bản tiếng Việt chuẩn
        vi_pass = client.translate(text, target_language='vi')
        vi_text = vi_pass['translatedText']

        # 2. Dịch ngược tiếng Việt chuẩn về tiếng Anh để sửa lỗi chính tả
        en_pass = client.translate(vi_text, target_language='en')
        en_text = en_pass['translatedText']

    # Xử lý text để in thường (lowercase) cho giống format của bạn
    return {
        "en": en_text.lower(),
        "vi": vi_text.lower()
    }

# ==========================================
# TEST THỬ KẾT QUẢ
# ==========================================

# inputs = ["áo khócac", "shoee", "cơm gừ", "wateer"]
#
# for word in inputs:
#     result = get_bilingual_and_correct(word)
#     print(f"Nhập: {word} -> Output: en: {result['en']}, vi: {result['vi']}")