from uuid import UUID
from datetime import datetime
from typing import List
from pydantic import BaseModel


class UserOut(BaseModel):
    id: UUID
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserRoleUpdate(BaseModel):
    role: str


class UserListResponse(BaseModel):
    items: List[UserOut]
    total: int
    page: int
    limit: int