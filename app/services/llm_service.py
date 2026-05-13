# To run this code you need to install the following dependencies:
# pip install google-genai

import os
from google import genai
from google.genai import types
from google.genai.types import ThinkingLevel

from app.utils.request_model_service import get_client


def generate(think_level: ThinkingLevel, prompts: str, properties: dict):
    client = get_client()

    model = "gemini-3-flash-preview"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="""INSERT_INPUT_HERE"""),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level=think_level,
        ),
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type = genai.types.Type.OBJECT,
            properties = {
                "fit": genai.types.Schema(
                    type = genai.types.Type.STRING,
                ),
                "color_and_fabric": genai.types.Schema(
                    type = genai.types.Type.STRING,
                ),
                "garment_type": genai.types.Schema(
                    type = genai.types.Type.STRING,
                ),
                "neckline_and_sleeves": genai.types.Schema(
                    type = genai.types.Type.STRING,
                ),
                "details": genai.types.Schema(
                    type = genai.types.Type.STRING,
                ),
            },
        ),
    )

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        if text := chunk.text:
            print(text, end="")

if __name__ == "__main__":
    generate()


