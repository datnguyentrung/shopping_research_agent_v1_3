from google.genai import types

from app.utils.load_instruction_from_file import load_instruction_from_file
from app.utils.request_model_service import _build_user_contents
from app.utils.fallback_service import generate_stream_with_fallback_async

async def generate_final_summary_stream(prompt: str):
    system_instruction = load_instruction_from_file("prompts/interactive_agent.md")
    contents = _build_user_contents(prompt)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.HIGH,
        ),
        temperature=1,
    )

    # Đẩy thẳng vào generator dùng chung, không cần viết lại vòng lặp try-catch nữa!
    async for chunk in generate_stream_with_fallback_async(contents=contents, config=config):
        yield chunk