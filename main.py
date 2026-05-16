"""
Shopping Research Agent API
Main application entry point with FastAPI configuration.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware


from app.core.config import settings
from app.api import chat_router, virtual_try_on_router, websocket_vto_router, conversation_router
from app.services import redis_service

# Import hàm khởi tạo model (điều chỉnh đường dẫn import cho khớp với project của bạn)
from app.tools.query_category_classifier_tool import init_classifier_model

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown events.
    """
    logger.info("🚀 Starting up Shopping Research Agent API...")

    try:
        logger.info("⏳ Initializing Query Category Classifier...")
        init_classifier_model()
        logger.info("✅ All models initialized successfully!")
    except Exception as e:
        logger.error(f"❌ Initialization failed: {str(e)}")
        raise e

    try:
        logger.info("⏳ Connecting to Redis...")
        # LỖI 1 ĐÃ SỬA: Thêm chữ await vào đây
        await redis_service.connect()
        logger.info("✅ Redis connected successfully!")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {str(e)}")
        raise e

    # LỖI 2 ĐÃ SỬA: Đã xóa hoàn toàn khối try-except của WebSocket Manager
    # Vì vto_ws_manager không cần khởi tạo lúc startup server!

    logger.info("✨ API is ready to serve requests")

    yield  # Ứng dụng hoạt động tại điểm này

    logger.info("🛑 Shutting down Shopping Research Agent API...")
    logger.info("✅ Shutdown completed")


# Initialize FastAPI application
app = FastAPI(
    title="Shopping Research Agent",
    description="AI-powered shopping research on Vietnamese e-commerce platforms",
    version="1.3.0",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong production nên giới hạn lại domain frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZIP compression middleware (giúp nén payload trả về, rất tốt cho tốc độ FE)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include routers
app.include_router(chat_router)       # Endpoint chat hiện tại
app.include_router(virtual_try_on_router)   # Endpoint research
app.include_router(websocket_vto_router)
app.include_router(conversation_router)

@app.get("/")
async def root():
    return {"message": "Shopping Research Agent API is running"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

logger.info("✅ Application initialized")