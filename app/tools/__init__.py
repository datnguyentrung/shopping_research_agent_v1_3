"""
Tất cả công cụ (Tools) mà Shopping Agent sử dụng cho Tool Calling.
"""

from google.genai import types
from app.tools.gg_translate_tool import get_bilingual_and_correct
from app.tools.query_category_classifier_tool import classify_keyword_topk
from app.tools.shopping_super_tool import search_and_display_declaration, stream_search_and_display

AVAILABLE_TOOLS = {
    "get_bilingual_and_correct": get_bilingual_and_correct,
    "classify_keyword_topk": classify_keyword_topk,
    "tool_search_and_display": stream_search_and_display
}

# Tạo GEMINI_TOOLS từ FunctionDeclarations
GEMINI_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_bilingual_and_correct",
                description="Sửa lỗi chính tả và dịch từ khóa sang song ngữ VI/EN.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "text": types.Schema(type=types.Type.STRING, description="Từ khóa cần sửa lỗi")
                    },
                    required=["text"],
                ),
            ),
            types.FunctionDeclaration(
                name="classify_keyword_topk",
                description="Phân loại từ khóa vào danh mục sản phẩm.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "text": types.Schema(type=types.Type.STRING, description="Từ khóa cần phân loại"),
                        "k": types.Schema(type=types.Type.INTEGER, description="Số lượng danh mục top")
                    },
                    required=["text", "k"],
                ),
            ),
            search_and_display_declaration.function_declarations[0],
        ]
    )
]
