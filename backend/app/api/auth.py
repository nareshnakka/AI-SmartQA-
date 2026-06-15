from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import get_request_user, require_roles
from app.db.session import get_db
from app.services.auth import (
    authenticate,
    create_access_token,
    list_users,
    upsert_sso_user,
    user_to_dict,
)
from app.services.sso import (
    build_sso_authorize_url,
    exchange_oidc_code,
    sso_configured,
    validate_sso_state,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

FRONTEND_LOGIN = "http://localhost:3000/login"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    role: str = "tester"


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    if not settings.qeos_auth_enabled:
        token = create_access_token(
            UUID("00000000-0000-0000-0000-000000000001"),
            body.email,
            "platform_admin",
            "Dev User",
        )
        return {
            "auth_enabled": False,
            "access_token": token,
            "token_type": "bearer",
            "user": {"id": "00000000-0000-0000-0000-000000000001", "email": body.email, "role": "platform_admin"},
        }

    user = await authenticate(db, body.email, body.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token(user.id, user.email, user.role, user.name)
    return {"access_token": token, "token_type": "bearer", "user": user_to_dict(user)}


@router.get("/me")
async def me(request: Request):
    user = get_request_user(request)
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
    }


@router.post("/register")
async def register_user(
    body: RegisterUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_roles("platform_admin")(request)
    from app.services.auth import get_user_by_email, hash_password
    from app.db.models import UserModel

    if await get_user_by_email(db, body.email):
        raise HTTPException(400, "Email already registered")
    if body.role not in ("platform_admin", "project_admin", "tester", "automation_engineer", "business_user"):
        raise HTTPException(400, "Invalid role")

    user = UserModel(
        email=body.email,
        name=body.name or body.email.split("@")[0],
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.flush()
    return user_to_dict(user)


@router.get("/status")
async def auth_status(request: Request, db: AsyncSession = Depends(get_db)):
    users = await list_users(db)
    user = get_request_user(request)
    return {
        "auth_enabled": settings.qeos_auth_enabled,
        "sso_enabled": settings.qeos_sso_enabled,
        "sso_configured": sso_configured(),
        "roles": ["platform_admin", "project_admin", "tester", "automation_engineer", "business_user"],
        "user_count": len(users),
        "default_admin": settings.qeos_default_admin_email if not settings.qeos_auth_enabled else None,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
    }


@router.get("/sso/login")
async def sso_login():
    if not sso_configured():
        raise HTTPException(400, "SSO not configured — set QEOS_SSO_* environment variables")
    url, _state = build_sso_authorize_url()
    return RedirectResponse(url)


@router.get("/sso/callback")
async def sso_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    if not validate_sso_state(state):
        raise HTTPException(400, "Invalid or expired SSO state")
    try:
        profile = await exchange_oidc_code(code)
    except Exception as e:
        raise HTTPException(400, f"SSO token exchange failed: {e}")

    user = await upsert_sso_user(db, profile["email"], profile["name"], profile["external_id"])
    token = create_access_token(user.id, user.email, user.role, user.name)
    return RedirectResponse(f"{FRONTEND_LOGIN}?token={token}")


@router.get("/sso/status")
async def sso_status():
    return {
        "enabled": settings.qeos_sso_enabled,
        "configured": sso_configured(),
        "issuer": settings.qeos_sso_issuer_url or None,
        "redirect_uri": settings.qeos_sso_redirect_uri,
    }
