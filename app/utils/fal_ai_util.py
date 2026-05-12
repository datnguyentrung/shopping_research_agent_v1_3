import asyncio
import fal_client

from app.core.config import settings


async def submit(person_image: str, product_file_path: str, category: str):
    # NHỚ: Thay bằng link ngrok của bạn + /webhook
    webhook_url = settings.WEBHOOK_URL

    handler = await fal_client.submit_async(
        "fal-ai/fashn/tryon/v1.6",
        arguments={
            "model_image": person_image,
            "garment_image": product_file_path,
            "category": category,
            "mode": "balanced"
        },
        webhook_url=webhook_url,
    )

    # BẮT BUỘC PHẢI RETURN cái handler này về cho Router
    return handler

if __name__ == "__main__":
    asyncio.run(submit())