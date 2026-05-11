


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import URL

from app.core import settings

# 1. KHAI BÁO CÁC THAM SỐ (Tương lai bạn nên đưa các giá trị này vào file .env)
DB_HOST = settings.DB_HOST
DB_PORT = 5432
DB_NAME = settings.DB_NAME
DB_USER = settings.DB_USER
DB_PASSWORD = settings.DB_PASSWORD

# 2. TẠO CHUỖI KẾT NỐI TỰ ĐỘNG
SQLALCHEMY_DATABASE_URL = URL.create(
    drivername="postgresql", # Dùng postgresql cho Supabase
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME
)

# 3. KHỞI TẠO ENGINE
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True  # Rất quan trọng khi dùng Cloud DB để giữ kết nối không bị rớt
)

# 4. KHỞI TẠO SESSION FACTORY
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. BASE CLASS CHO ENTITIES
Base = declarative_base()