"""Authentication and account management."""

from __future__ import annotations

from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import or_, select

from app.config import settings
from app.core.deps import (
    AdminOnly,
    CurrentUser,
    DbSession,
    resolve_district,
    resolve_ward,
)
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    password_problems,
    verify_password,
)
from app.models import AuditLog, District, Role, User, Ward
from app.schemas import (
    LoginIn,
    MessageOut,
    RegisterIn,
    TokenOut,
    UserOut,
    UserUpdateIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue(user: User) -> TokenOut:
    access = create_token(user.id, role=user.role, token_type="access")
    refresh = create_token(user.id, role=user.role, token_type="refresh")
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


async def _find(db, identifier: str) -> User | None:
    rows = await db.execute(
        select(User).where(or_(User.email == identifier.lower(), User.phone == identifier))
    )
    return rows.scalars().first()


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, db: DbSession) -> TokenOut:
    """Self-service sign-up.

    Always creates a **citizen**. The role field on the payload is accepted for
    API symmetry but ignored — letting anyone POST `{"role": "district_admin"}`
    and gain broadcast powers would defeat the entire authorisation model.
    Staff accounts are created by an admin through ``POST /auth/staff``.
    """
    if body.role != Role.CITIZEN.value:
        # Not an error: a client that sends it just gets a citizen account.
        pass
    if not body.email and not body.phone:
        raise HTTPException(422, "Provide an email or a phone number")
    if problems := password_problems(body.password):
        raise HTTPException(422, "Weak password: " + "; ".join(problems))

    if body.email and await _find(db, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with those details exists")
    if body.phone and await _find(db, body.phone):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that phone exists")

    ward: Ward | None = None
    district: District | None = None
    if body.ward_code:
        ward = await resolve_ward(db, body.ward_code)
        district = ward.district
    elif body.district_code:
        district = await resolve_district(db, body.district_code)

    user = User(
        email=body.email.lower() if body.email else None,
        phone=body.phone,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role=Role.CITIZEN.value,
        preferred_lang=body.preferred_lang,
        ward_id=ward.id if ward else None,
        district_id=district.id if district else None,
        trust_score=0.5,
    )
    db.add(user)
    await db.flush()
    db.add(
        AuditLog(
            actor_id=user.id,
            actor_label=user.full_name or "self",
            action="auth.register",
            entity="user",
            entity_id=str(user.id),
            detail={"role": user.role},
            ip=request.client.host if request.client else "",
        )
    )
    return _issue(user)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: DbSession) -> TokenOut:
    user = await _find(db, body.identifier.strip())
    # Same error for unknown account and wrong password: do not leak which
    # phone numbers are registered in a disaster system.
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    user.last_login_at = datetime.now(timezone.utc)
    return _issue(user)


@router.post("/refresh", response_model=TokenOut)
async def refresh(refresh_token: str, db: DbSession) -> TokenOut:
    try:
        payload = decode_token(refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if payload.get("typ") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    user = await db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account unavailable")
    return _issue(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserUpdateIn, db: DbSession, user: CurrentUser) -> UserOut:
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.preferred_lang is not None:
        user.preferred_lang = body.preferred_lang
    if body.phone is not None:
        existing = await _find(db, body.phone)
        if existing and existing.id != user.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Phone already in use")
        user.phone = body.phone
    if body.push_token is not None:
        user.push_token = body.push_token
    if body.ward_code:
        ward = await resolve_ward(db, body.ward_code)
        user.ward_id = ward.id
        user.district_id = ward.district_id
    await db.flush()
    return UserOut.model_validate(user)


@router.post("/staff", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_staff(body: RegisterIn, db: DbSession, admin: AdminOnly) -> UserOut:
    """Admin-created responder / district-admin accounts."""
    if body.role == Role.CITIZEN.value:
        raise HTTPException(422, "Use /auth/register for citizen accounts")
    if problems := password_problems(body.password):
        raise HTTPException(422, "Weak password: " + "; ".join(problems))
    if await _find(db, body.email or body.phone or ""):
        raise HTTPException(status.HTTP_409_CONFLICT, "Account exists")

    ward = await resolve_ward(db, body.ward_code) if body.ward_code else None
    district = (
        ward.district if ward else (await resolve_district(db, body.district_code) if body.district_code else None)
    )
    user = User(
        email=body.email.lower() if body.email else None,
        phone=body.phone,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role=body.role,
        preferred_lang=body.preferred_lang,
        ward_id=ward.id if ward else None,
        district_id=district.id if district else None,
        is_verified=True,
        trust_score=0.9,
    )
    db.add(user)
    await db.flush()
    db.add(
        AuditLog(
            actor_id=admin.id,
            actor_label=admin.full_name,
            action="auth.create_staff",
            entity="user",
            entity_id=str(user.id),
            detail={"role": user.role},
        )
    )
    return UserOut.model_validate(user)


@router.get("/users")
async def list_users(
    db: DbSession, admin: AdminOnly, role: str | None = None, limit: int = 100
) -> list[UserOut]:
    stmt = select(User).order_by(User.id).limit(min(limit, 500))
    if role:
        stmt = stmt.where(User.role == role)
    rows = await db.execute(stmt)
    return [UserOut.model_validate(u) for u in rows.scalars()]


@router.patch("/users/{user_id}/verify", response_model=MessageOut)
async def verify_reporter(user_id: int, db: DbSession, admin: AdminOnly) -> MessageOut:
    """Verifying a reporter raises the trust weight their future reports carry."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such user")
    user.is_verified = True
    user.trust_score = max(user.trust_score, 0.85)
    await db.flush()
    return MessageOut(message=f"{user.full_name} verified", detail={"trust_score": user.trust_score})
