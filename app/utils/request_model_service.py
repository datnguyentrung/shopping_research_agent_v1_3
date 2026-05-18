import json
import types
from typing import Any

from google import genai
from google.genai import types

from app.core.config.settings import settings

client = None


def get_client() -> genai.Client:
    global client
    if client is None:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return client

def get_client_cloud():
    """
    Khởi tạo Google GenAI Client chạy qua luồng Vertex AI
    để cấn trừ chi phí trực tiếp vào gói 300 USD (7.9 triệu VND) free credit.
    """
    return genai.Client(
        vertexai=True,
        # project="shopping-research-419204",  # ID dự án lấy từ màn hình của ông
        location="us-central1"               # Môi trường us-central1 hỗ trợ đầy đủ các dòng Gemini 3.1 và Imagen
    )


def _build_user_contents(text: str) -> list[types.Content]:
    return [types.Content(role="user", parts=[types.Part.from_text(text=text)])]


def _safe_json_loads(response: Any, default: Any) -> Any:
    text_payload = ""
    if isinstance(response, str):
        text_payload = response
    elif response and getattr(response, "text", None):
        text_payload = response.text

    if text_payload:
        return json.loads(text_payload)
    return default


async def generate_with_fallback_async(
        client_instance: genai.Client,
        models: list[str],
        contents: list[types.Content],
        config: types.GenerateContentConfig
) -> str:
    """
    Ham goi API bat dong bo (Async) co che thu lai (fallback).
    """
    for model in models:
        try:
            chunks: list[str] = []
            stream = await client_instance.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if text := getattr(chunk, "text", None):
                    chunks.append(text)

            return "".join(chunks)

        except Exception as e:
            error_msg = str(e)

            # IN RA LỖI CHI TIẾT ĐỂ DEBUG
            print(f"-> [Chi tiết lỗi của {model}]: {error_msg}")

            if any(err in error_msg for err in ["503", "UNAVAILABLE", "529", "429", "RESOURCE_EXHAUSTED"]):
                print(f"[Warning] Model '{model}' loi (Qua tai/Het Quota). Dang chuyen sang model tiep theo...")
                continue
            print(f"[Error] Loi nghiem trong tu '{model}': {error_msg}")
            raise e

    raise RuntimeError("Tat ca cac model fallback deu qua tai.")
