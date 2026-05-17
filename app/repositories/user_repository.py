from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.entities.user import User
from app.repositories.base import BaseRepository, ModelType


class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session):
        super().__init__(db, User)

    def get(self, id: UUID) -> Optional[ModelType]:
        return self.db.query(self.model).filter(self.model.id == id).first()

