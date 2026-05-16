from sqlalchemy.orm import Session

from app.entities.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session):
        super().__init__(db, User)

    # Thêm các hàm như get_by_email, create_user...