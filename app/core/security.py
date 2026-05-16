"""
Module xác thực JWT từ Supabase Auth.
Hỗ trợ cả user đã đăng nhập và guest (chưa có token).
"""

import logging
from typing import Optional, Any, Generator
from uuid import UUID

import jwt
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
    Giải mã và xác thực JWT do Supabase Auth cấp.
    Raises HTTPException 401 nếu token không hợp lệ.
    """
    try:
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


def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[UUID]:
    """
    FastAPI Dependency: trích xuất user_id từ Supabase JWT.

    - Nếu không có token → trả về None (Guest).
    - Nếu có token hợp lệ → trả về UUID của user từ claim 'sub'.
    - Nếu token sai/hết hạn → raise 401.
    """
    if not token:
        return None  # Guest user

    payload = _decode_supabase_jwt(token)

    # sub trong Supabase JWT là UUID của user
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
    Session được tự động đóng sau khi endpoint xử lý xong.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
