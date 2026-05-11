"""
Shopping Research Agent API
Main application entry point with FastAPI configuration.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware


from app.core.config import settings
from app.api.routes import router as chat_router
# from app.api.endpoints import router as research_router

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
    # =========================================
    # STARTUP: Chạy TRƯỚC KHI server nhận request
    # =========================================
    logger.info("🚀 Starting up Shopping Research Agent API...")

    try:
        # Khởi tạo mô hình Classifier tại đây!
        logger.info("⏳ Initializing Query Category Classifier...")
        init_classifier_model()

        # Thêm các logic khởi tạo khác ở đây (ví dụ: kết nối DB, Redis...)

        logger.info("✅ All models initialized successfully!")
        logger.info("✨ API is ready to serve requests")
    except Exception as e:
        logger.error(f"❌ Initialization failed: {str(e)}")
        raise e  # Bắt buộc raise để server KHÔNG khởi động nếu model bị lỗi

    yield  # Ứng dụng hoạt động tại điểm này

    # =========================================
    # SHUTDOWN: Chạy SAU KHI server bị tắt (Ctrl+C)
    # =========================================
    logger.info("🛑 Shutting down Shopping Research Agent API...")
    # Thêm code dọn dẹp tại đây (ví dụ: đóng kết nối Database)
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
# app.include_router(research_router)   # Endpoint research

@app.get("/")
async def root():
    return {"message": "Shopping Research Agent API is running"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

logger.info("✅ Application initialized")