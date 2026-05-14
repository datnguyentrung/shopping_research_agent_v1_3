from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

ENV_FILE = r'D:\Code\Python\Shopping_Research_Agent\.env'


class Settings(BaseSettings):
    PROJECT_NAME: str = "Shopping Research Agent"
    API_V1: str = "/api/v1"

    # --- Các biến Database ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "shopping_research_agent"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DATABASE_URL: str = "postgresql+asyncpg://root:31102005@localhost:5433/version_4"

    # --- Các biến API Keys & Cloud ---
    GOOGLE_API_KEY: str = ""
    HF_TOKEN: str = ""
    ZAI_API_KEY: str = ""
    SERPER_API_KEY: str = ""
    VERTEX_ENGINE_ID: str = ""  # Đã sửa lại lỗi chính tả từ VERTX thành VERTEX
    PROJECT_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    REDIS_URL: str = ""
    NGROK_URL: str = ""

    # --- Các biến bổ sung từ file .env ---
    DEBUG: bool = False
    API_VERSION: str = "v1"
    SEARCH_TIMEOUT: int = 30
    MAX_RESULTS_PER_QUERY: int = 50
    LOG_LEVEL: str = "INFO"
    TRACE_ENABLED: Optional[str] = None  # Có thể để trống hoặc điền giá trị
    TRACE_STREAM: Optional[str] = None  # Có thể để trống hoặc điền giá trị

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


# Khởi tạo một biến settings để import dùng ở mọi nơi
settings = Settings()