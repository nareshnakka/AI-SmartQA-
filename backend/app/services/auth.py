"""Optional RBAC — disabled by default in development."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import ProjectMemberModel, UserModel

ROLES = ("platform_admin", "project_admin", "tester", "automation_engineer", "business_user")


async def seed_default_admin(db: AsyncSession) -> None:
    result = await db.execute(select(UserModel).limit(1))
    if result.scalar_one_or_none():
        return
    admin = UserModel(
        email=settings.qeos_default_admin_email,
        name="Platform Admin",
        password_hash=hash_password(settings.qeos_default_admin_password),
        role="platform_admin",
    )
    db.add(admin)
    await db.flush()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(user_id: uuid.UUID, email: str, role: str, name: str = "") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "name": name,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


async def authenticate(db: AsyncSession, email: str, password: str) -> UserModel | None:
    result = await db.execute(select(UserModel).where(UserModel.email == email, UserModel.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


async def list_users(db: AsyncSession) -> list[UserModel]:
    result = await db.execute(select(UserModel).order_by(UserModel.created_at.desc()))
    return list(result.scalars().all())


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> UserModel | None:
    return await db.get(UserModel, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> UserModel | None:
    result = await db.execute(select(UserModel).where(UserModel.email == email))
    return result.scalar_one_or_none()


async def upsert_sso_user(
    db: AsyncSession,
    email: str,
    name: str,
    external_id: str,
    default_role: str = "tester",
) -> UserModel:
    user = await get_user_by_email(db, email)
    if user:
        user.name = name or user.name
        user.auth_provider = "oidc"
        user.external_id = external_id
        await db.flush()
        return user

    user = UserModel(
        email=email,
        name=name or email.split("@")[0],
        password_hash=hash_password(uuid.uuid4().hex),
        role=default_role,
        auth_provider="oidc",
        external_id=external_id,
    )
    db.add(user)
    await db.flush()
    return user


def user_to_dict(user: UserModel) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "auth_provider": user.auth_provider,
    }


async def add_project_member(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, role: str = "tester"
) -> ProjectMemberModel:
    member = ProjectMemberModel(project_id=project_id, user_id=user_id, role=role)
    db.add(member)
    await db.flush()
    return member
