import redis.asyncio as redis
import json
import logging

from app.core.config import settings

# Khởi tạo logger
logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self):
        # Lấy URL từ Render Dashboard (dạng rediss://...)
        self.redis_url = settings.REDIS_URL
        self.client = None

    async def connect(self):
        # Ẩn bớt URL để bảo mật, không log password/token ra console
        safe_url = self.redis_url.split('@')[-1] if '@' in self.redis_url else "Redis_URL"
        logger.info(f"[Redis] REQ - Init connection to {safe_url}...")

        try:
            # Render yêu cầu SSL (rediss://).
            self.client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,  # Tự động decode bytes sang string
                ssl_cert_reqs=None  # Tương đương disablePeerVerification() bên Java
            )
            # Ping thử để đảm bảo kết nối thực sự thành công
            await self.client.ping()
            logger.info("[Redis] RES - Connected successfully.")
        except Exception as e:
            logger.error(f"[Redis] RES - Connection failed: {str(e)}")
            raise e

    async def set_vto_request(self, request_id: str, data: dict, ttl: int):
        """Lưu kết quả VTO với TTL ngẫu nhiên (tránh Cache Stampede)"""
        redis_key = f"vto:request:{request_id}"
        logger.info(f"[Redis] REQ - Set Cache | Key: {redis_key} | TTL: {ttl}s")

        try:
            await self.client.setex(
                redis_key,
                ttl,
                json.dumps(data)
            )
            logger.info(f"[Redis] RES - Set Cache Success | Key: {redis_key}")
        except Exception as e:
            logger.error(f"[Redis] RES - Set Cache Failed | Key: {redis_key} | Error: {str(e)}")
            # Tuỳ logic app của bạn có muốn raise lỗi này lên không hay bỏ qua
            # raise e

    async def get_vto_request(self, request_id: str):
        redis_key = f"vto:request:{request_id}"
        logger.info(f"[Redis] REQ - Get Cache | Key: {redis_key}")

        try:
            data = await self.client.get(redis_key)
            if data:
                logger.info(f"[Redis] RES - Cache HIT | Key: {redis_key}")
                return json.loads(data)
            else:
                logger.info(f"[Redis] RES - Cache MISS | Key: {redis_key}")
                return None
        except Exception as e:
            logger.error(f"[Redis] RES - Get Cache Failed | Key: {redis_key} | Error: {str(e)}")
            return None

    async def set_state(self, key: str, data: dict, ttl: int):
        """Lưu State chung của ứng dụng vào Redis"""
        logger.info(f"[Redis] REQ - Set State | Key: {key} | TTL: {ttl}s")
        try:
            await self.client.setex(
                key,
                ttl,
                json.dumps(data, ensure_ascii=False, default=str)
            )
            logger.info(f"[Redis] RES - Set State Success | Key: {key}")
        except Exception as e:
            logger.error(f"[Redis] RES - Set State Failed | Key: {key} | Error: {str(e)}")

    async def get_state(self, key: str) -> dict | None:
        """Lấy State chung của ứng dụng từ Redis"""
        logger.info(f"[Redis] REQ - Get State | Key: {key}")
        try:
            data = await self.client.get(key)
            if data:
                logger.info(f"[Redis] RES - State Cache HIT | Key: {key}")
                return json.loads(data)
            else:
                logger.info(f"[Redis] RES - State Cache MISS | Key: {key}")
                return None
        except Exception as e:
            logger.error(f"[Redis] RES - Get State Failed | Key: {key} | Error: {str(e)}")
            return None

    async def delete_key(self, key: str):
        """Xoá một key trong Redis"""
        logger.info(f"[Redis] REQ - Delete Key | Key: {key}")
        try:
            await self.client.delete(key)
            logger.info(f"[Redis] RES - Delete Key Success | Key: {key}")
        except Exception as e:
            logger.error(f"[Redis] RES - Delete Key Failed | Key: {key} | Error: {str(e)}")

    async def init_vto_hash(self, request_id: str, ttl: int):
        """Khởi tạo request VTO dạng Hash (HSET)"""
        redis_key = f"vto:request:{request_id}"
        logger.info(f"[Redis] REQ - Init VTO Hash | Key: {redis_key}")
        try:
            # Lưu các field ban đầu
            await self.client.hset(
                redis_key,
                mapping={
                    "status": "pending",
                    "result_url": "",
                    "error": ""
                }
            )
            # Set thời gian hết hạn
            await self.client.expire(redis_key, ttl)
        except Exception as e:
            logger.error(f"[Redis] RES - Init Hash Failed | Key: {redis_key} | Error: {str(e)}")

    async def update_vto_hash(self, request_id: str, updates: dict) -> dict:
        """Cập nhật 1 vài field và trả về toàn bộ object mới nhất để bắn WebSocket"""
        redis_key = f"vto:request:{request_id}"
        try:
            if updates:
                # Chỉ update những trường được truyền vào (VD: {"status": "completed"})
                await self.client.hset(redis_key, mapping=updates)

            # Lấy toàn bộ data mới nhất ra để làm payload cho WebSocket
            data = await self.client.hgetall(redis_key)
            return data
        except Exception as e:
            logger.error(f"[Redis] RES - Update Hash Failed | Key: {redis_key} | Error: {str(e)}")
            return {}

# Khởi tạo instance dùng chung
redis_service = RedisService()