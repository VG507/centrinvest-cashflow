from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.auth_service import AuthService
from src.schemas.contracts import (
    LoginRequest, SessionResponse, LogoutResponse, UserSessionInfo
)
from src.api.deps import PlatformApiException, get_current_user, get_session_token
from src.models.entities import User
from src.config import settings

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])

def is_request_secure(request: Request) -> bool:
    if settings.COOKIE_SECURE or (request.url.scheme == "https"):
        return True
    trusted = getattr(settings, "TRUSTED_PROXIES", ["127.0.0.1", "::1", "localhost", "testclient"])
    client_host = request.client.host if request.client else None
    if client_host in trusted:
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto and forwarded_proto.lower() == "https":
            return True
    return False

@router.post("/login", response_model=SessionResponse)
async def login(
    req: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # Ensure demo user exists if demo credentials supplied
    if req.email == "demo@centrinvest.ru":
        await AuthService.get_or_create_demo_user(db)

    user = await AuthService.authenticate(db, req.email, req.password)
    if not user:
        raise PlatformApiException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Invalid email or password"
        )

    session = await AuthService.create_session(db, user.id)
    company_ids = await AuthService.get_user_company_ids(db, user.id)

    # Set HttpOnly session cookie (enforce Secure on HTTPS or via forwarded proxy)
    is_secure = is_request_secure(request)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=session.id,
        httponly=True,
        secure=is_secure,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        path="/"
    )

    return SessionResponse(
        user=UserSessionInfo(
            id=user.id,
            display_name=user.display_name,
            company_ids=company_ids
        ),
        expires_at=session.expires_at.isoformat()
    )

@router.get("/session", response_model=SessionResponse)
async def get_session(
    user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    token = await get_session_token(request)
    val = await AuthService.validate_session(db, token)
    if not val:
        raise PlatformApiException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Invalid session"
        )
    _, session = val
    company_ids = await AuthService.get_user_company_ids(db, user.id)

    return SessionResponse(
        user=UserSessionInfo(
            id=user.id,
            display_name=user.display_name,
            company_ids=company_ids
        ),
        expires_at=session.expires_at.isoformat()
    )

@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    token = await get_session_token(request)
    if token:
        await AuthService.delete_session(db, token)
    is_secure = is_request_secure(request)
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        secure=is_secure
    )
    return LogoutResponse(signed_out=True)
