"""JWT auth middleware and user context."""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

PUBLIC_EXACT = {"/", "/health", "/docs", "/redoc", "/openapi.json"}
PUBLIC_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/status",
    "/api/v1/auth/sso",
    "/api/v1/monitoring/webhooks",
)


@dataclass
class AuthUser:
    id: uuid.UUID
    email: str
    role: str
    name: str = ""

    @classmethod
    def dev_user(cls) -> "AuthUser":
        return cls(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            email="dev@qeos.local",
            role="platform_admin",
            name="Development User",
        )


def decode_access_token(token: str) -> AuthUser | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            return None
        return AuthUser(
            id=uuid.UUID(sub),
            email=payload.get("email", ""),
            role=payload.get("role", "tester"),
            name=payload.get("name", ""),
        )
    except (JWTError, ValueError):
        return None


def _is_public(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.qeos_auth_enabled or _is_public(request.url.path):
            if not settings.qeos_auth_enabled:
                request.state.user = AuthUser.dev_user()
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

        user = decode_access_token(auth[7:])
        if not user:
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

        request.state.user = user
        return await call_next(request)


def get_request_user(request: Request) -> AuthUser:
    user = getattr(request.state, "user", None)
    if user:
        return user
    if not settings.qeos_auth_enabled:
        return AuthUser.dev_user()
    raise HTTPException(status_code=401, detail="Authentication required")


def require_roles(*roles: str):
    def checker(request: Request) -> AuthUser:
        user = get_request_user(request)
        if user.role not in roles and user.role != "platform_admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker
