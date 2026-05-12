import redis.asyncio as redis
import json

from app.core.config import settings


class RedisService:
    def __init__(self):
        # Lấy URL từ Render Dashboard (dạng rediss://...)
        self.redis_url = settings.REDIS_URL
        self.client = None

    async def connect(self):
        # Render yêu cầu SSL (rediss://).
        # Cấu hình y hệt đoạn LettuceConnectionFactory bên Java của bạn:
        self.client = redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,  # Tự động decode bytes sang string
            ssl_cert_reqs=None  # Tương đương disablePeerVerification() bên Java
        )

    async def set_vto_request(self, request_id: str, data: dict, ttl: int):
        """Lưu kết quả VTO với TTL ngẫu nhiên (tránh Cache Stampede)"""
        await self.client.setex(
            f"vto:request:{request_id}",
            ttl,
            json.dumps(data)
        )

    async def get_vto_request(self, request_id: str):
        data = await self.client.get(f"vto:request:{request_id}")
        return json.loads(data) if data else None


# Khởi tạo instance dùng chung
redis_service = RedisService()