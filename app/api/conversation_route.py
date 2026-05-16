from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from uuid import UUID

# Import 2 hàm xịn bạn vừa viết
from app.core.security import get_db_session
from app.repositories.conversation_repository import ConversationRepository
from app.schema.conversation_schemas import ConversationResponse
from app.schema.page_schema import PageResponse

router = APIRouter(prefix="/conversations", tags=["conversation"])


@router.get("", response_model=PageResponse[ConversationResponse])
async def list_conversations_by_user_id(
        user_id: UUID = Query(..., description="ID người dùng"),

        # Bỏ | None ở những field đã có default value
        limit: int = Query(10, ge=1, description="Số lượng lấy ra"),
        offset: int = Query(0, ge=0, description="Vị trí bắt đầu"),
        sort_by: str = Query("updated_at", description="Trường để sắp xếp"),
        sort_dir: str = Query("desc", description="Hướng sắp xếp (asc/desc)"),

        # Riêng search mặc định là None thì giữ nguyên | None
        search: str | None = Query(None, description="Từ khóa tìm kiếm"),

        db: Session = Depends(get_db_session)
) -> PageResponse[ConversationResponse]:
    repo = ConversationRepository(db)

    items, total = repo.get_conversations_by_user_id(
        user_id=user_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search
    )

    return PageResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_next=(offset + limit) < total
    )