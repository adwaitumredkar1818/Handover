"""Repository operations for platform user accounts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import UserStatus
from app.models.rbac import UserRole
from app.models.user import User


class UserRepository:
    """Data-access operations for `users`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
        )
        return self._session.scalars(stmt).unique().first()

    def get_by_email(self, normalised_email: str) -> User | None:
        stmt = (
            select(User)
            .where(User.email == normalised_email)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
        )
        return self._session.scalars(stmt).unique().first()

    def get_by_supabase_auth_id(self, supabase_auth_id: str) -> User | None:
        stmt = (
            select(User)
            .where(User.supabase_auth_id == supabase_auth_id)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
        )
        return self._session.scalars(stmt).unique().first()

    def list_users(self, *, limit: int = 50, offset: int = 0) -> list[User]:
        stmt = (
            select(User)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
            .order_by(User.created_at.desc(), User.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(self._session.scalars(stmt).unique().all())

    def count_users(self) -> int:
        stmt = select(func.count(User.id))
        return int(self._session.scalar(stmt) or 0)

    def create(
        self,
        *,
        full_name: str,
        email: str,
        password_hash: str | None = None,
        supabase_auth_id: str | None = None,
        status: str = UserStatus.ACTIVE.value,
        is_email_verified: bool = False,
        email_verified_at: datetime | None = None,
    ) -> User:
        if password_hash is not None and not password_hash.strip():
            raise ValueError("password_hash must be a non-empty hash string if provided.")
        if password_hash is None and not supabase_auth_id:
            raise ValueError("Either password_hash or supabase_auth_id must be provided.")
        user = User(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            supabase_auth_id=supabase_auth_id,
            status=status,
            is_email_verified=is_email_verified,
            email_verified_at=email_verified_at,
        )
        self._session.add(user)
        self._session.flush()
        return user

    def update_last_login(self, user: User, login_at: datetime) -> None:
        user.last_login_at = login_at
        self._session.flush()

    def link_supabase_auth_id(
        self,
        user: User,
        supabase_auth_id: str,
        *,
        mark_email_verified: bool = False,
        verified_at: datetime | None = None,
    ) -> None:
        user.supabase_auth_id = supabase_auth_id
        if mark_email_verified and not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = verified_at
        self._session.flush()

    def update_status(self, user: User, status: str) -> None:
        user.status = status
        self._session.flush()

    def update_password_hash(self, user: User, password_hash: str) -> None:
        if not password_hash or not password_hash.strip():
            raise ValueError("password_hash must be a non-empty string.")
        user.password_hash = password_hash
        self._session.flush()

