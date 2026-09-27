"""FastAPI dependencies: authentication, role gates, and shared lookups."""

from __future__ import annotations

from typing import Annotated, Callable, Iterable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db import get_db
from app.models import District, Role, User, Ward

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def user_from_token(token: str | None, db: AsyncSession) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, sign in again")
    except jwt.PyJWTError:
        raise CREDENTIALS_ERROR
    if payload.get("typ") != "access":
        raise CREDENTIALS_ERROR
    user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return user


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    token = credentials.credentials if credentials else None
    user = await user_from_token(token, db)
    if user is None:
        raise CREDENTIALS_ERROR
    return user


async def optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """For endpoints that work anonymously but personalise when signed in."""
    return await user_from_token(credentials.credentials if credentials else None, db)


def require_roles(*roles: str) -> Callable[..., object]:
    """Role gate. Elevation is refused rather than silently downgraded."""

    allowed = {r.value if isinstance(r, Role) else r for r in roles}

    async def _guard(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(sorted(allowed))}",
            )
        return user

    return _guard


# Convenient aliases used across the routers.
#
# These MUST be ``Annotated[User, Depends(...)]`` rather than the bare guard
# function. Passing a callable as the annotation makes FastAPI treat it as an
# implicit dependency and re-evaluate the *guard's own* string annotations
# (``from __future__ import annotations``) in the route module's namespace,
# where ``User`` is not imported — which fails at import time with a NameError.
AnyStaff = Annotated[User, Depends(require_roles(Role.FIELD_RESPONDER, Role.DISTRICT_ADMIN, Role.SYSTEM_ADMIN))]
AdminOnly = Annotated[User, Depends(require_roles(Role.DISTRICT_ADMIN, Role.SYSTEM_ADMIN))]
SystemOnly = Annotated[User, Depends(require_roles(Role.SYSTEM_ADMIN))]

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(current_user)]
MaybeUser = Annotated[User | None, Depends(optional_user)]


async def resolve_ward(db: AsyncSession, code: str) -> Ward:
    rows = await db.execute(select(Ward).where(Ward.code == code.strip().upper()))
    ward = rows.scalars().first()
    if ward is None:
        raise HTTPException(status_code=404, detail=f"Unknown ward '{code}'")
    return ward


async def resolve_district(db: AsyncSession, code: str) -> District:
    rows = await db.execute(select(District).where(District.code == code.strip().upper()))
    district = rows.scalars().first()
    if district is None:
        raise HTTPException(status_code=404, detail=f"Unknown district '{code}'")
    return district


async def get_user_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    rows = await db.execute(
        select(User).where(
            or_(User.email == identifier.lower(), User.phone == identifier)
        )
    )
    return rows.scalars().first()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def scope_wards(wards: Iterable[Ward], user: User) -> list[Ward]:
    """District admins only ever act inside their own district."""
    if user.role == Role.SYSTEM_ADMIN.value:
        return list(wards)
    if user.district_id:
        return [w for w in wards if w.district_id == user.district_id]
    return list(wards)
