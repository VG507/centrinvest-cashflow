import uuid
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.auth_service import AuthService
from src.models.entities import User
from src.schemas.contracts import ApiError
from src.config import settings

class AntigravityApiException(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: list = None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.api_message = message
        self.details = details or []

async def get_session_token(request: Request) -> str | None:
    # 1. Check cookie
    token = request.cookies.get(settings.COOKIE_NAME)
    if token:
        return token
    # 2. Check Authorization Bearer header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    token = await get_session_token(request)
    if not token:
        raise AntigravityApiException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Missing or invalid session credentials"
        )
    val = await AuthService.validate_session(db, token)
    if not val:
        raise AntigravityApiException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Session has expired or is invalid"
        )
    user, session = val
    return user

async def verify_company_access(
    company_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    has_access = await AuthService.ensure_user_has_company(db, user.id, company_id)
    if not has_access:
        raise AntigravityApiException(
            status_code=status.HTTP_403_FORBIDDEN,
            code="forbidden",
            message=f"Access denied to company {company_id}"
        )
    return user
