"""
Module xác thực JWT từ Supabase Auth.
Hỗ trợ cả user đã đăng nhập và guest (chưa có token).
"""

import logging
from typing import Optional, Any, Generator
from uuid import UUID

import jwt  # Sử dụng PyJWT công thức chuẩn
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.database import SessionLocal

logger = logging.getLogger(__name__)

# auto_error=False: cho phép guest (không gửi token) truy cập mà không bị chặn 403
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def _decode_supabase_jwt(token: str) -> dict:
    """
    Giải mã và xác thực JWT do Supabase Auth cấp (Hỗ trợ cả HS256 và ES256).
    """
    try:
        # 1. Đọc thử Header để kiểm tra thuật toán (algorithm)
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "HS256")

        # Lấy cấu hình URL từ settings
        supabase_url = settings.SUPABASE_URL
        if not supabase_url:
            logger.error("❌ Cảnh báo: settings.SUPABASE_URL đang để trống! Hãy kiểm tra file .env")

        if alg == "ES256":
            # 2. Xử lý thuật toán bất đối xứng ES256 bằng PyJWKClient của PyJWT
            jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"

            # Khởi tạo bộ Client lấy và cache key tự động
            jwks_client = jwt.PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
            )
        else:
            # 3. Xử lý thuật toán đối xứng HS256 thông thường
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đã hết hạn.",
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không đúng audience (yêu cầu 'authenticated').",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token không hợp lệ: {e}",
        )
    except jwt.PyJWTError as e:  # FIX lỗi AttributeError: Sử dụng PyJWTError của PyJWT thay vì JWTError
        logger.error(f"❌ Lỗi xác thực JWT tổng quát: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Lỗi xác thực Token: {str(e)}",
        )


def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[UUID]:
    """
    FastAPI Dependency: trích xuất user_id từ Supabase JWT.
    """
    if not token:
        return None  # Guest user

    payload = _decode_supabase_jwt(token)

    sub: str | None = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không chứa claim 'sub'.",
        )

    try:
        return UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Claim 'sub' không phải UUID hợp lệ.",
        )


def get_db_session() -> Generator[Any, Any, None]:
    """
    FastAPI Dependency: cung cấp SQLAlchemy Session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()