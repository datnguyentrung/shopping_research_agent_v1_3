"""Shared LLM model fallback order used by non-ADK generation paths."""

MODELS_TO_TRY = [
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-flash-latest",
]

MODELS_IMAGE_TO_TRY = [
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
]
