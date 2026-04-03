from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserOut, UserRoleUpdate, UserListResponse
from app.routers.auth import require_role

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=UserListResponse)
async def list_users(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("super_admin")),
):
    query = select(User)
    if q:
        query = query.where(User.email.ilike(f"%{q}%"))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * limit
    query = query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    users = (await db.execute(query)).scalars().all()

    return UserListResponse(items=list(users), total=total, page=page, limit=limit)


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(
    user_id: UUID,
    body: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("super_admin")),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role.")

    if body.role not in ["user", "moderator"]:
        raise HTTPException(status_code=400, detail="Invalid role. Can only set 'user' or 'moderator'.")

    result = await db.execute(select(User).where(User.id == user_id))
    user_to_update = result.scalar_one_or_none()

    if not user_to_update:
        raise HTTPException(status_code=404, detail="User not found.")

    if user_to_update.role == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot change the role of another super admin.")

    user_to_update.role = body.role
    await db.commit()
    await db.refresh(user_to_update)

    return user_to_update