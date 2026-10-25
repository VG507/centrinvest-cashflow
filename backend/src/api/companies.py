from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models.entities import Company, CompanyMembership, User
from src.schemas.contracts import (
    Company as CompanySchema, CompanyListResponse, CompanyCreateRequest
)
from src.api.deps import PlatformApiException, get_current_user, verify_company_access

from src.services.auth_service import AuthService

router = APIRouter(prefix="/api/v2/companies", tags=["companies"])

@router.get("", response_model=CompanyListResponse)
async def list_companies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_company_ids = await AuthService.get_user_company_ids(db, user.id)
    if not user_company_ids:
        return CompanyListResponse(items=[])
    res = await db.execute(
        select(Company).where(Company.id.in_(user_company_ids)).order_by(Company.created_at)
    )
    comps = res.scalars().all()
    items = []
    for c in comps:
        items.append(CompanySchema(
            id=c.id,
            name=c.name,
            business_type=c.business_type,
            currency=c.currency or "RUB",
            timezone=c.timezone or "Europe/Moscow",
            closing_balance=float(c.closing_balance) if c.closing_balance is not None else None,
            balance_date=c.balance_date.strftime("%Y-%m-%d") if c.balance_date else None,
            data_revision=c.data_revision
        ))
    return CompanyListResponse(items=items)

@router.post("", response_model=CompanySchema, status_code=status.HTTP_201_CREATED)
async def create_company(
    req: CompanyCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    comp = Company(
        name=req.name,
        business_type=req.business_type,
        timezone=req.timezone or "Europe/Moscow",
        currency="RUB",
        data_revision=0
    )
    db.add(comp)
    await db.flush()

    # Bind membership
    db.add(CompanyMembership(user_id=user.id, company_id=comp.id))
    await db.commit()
    await db.refresh(comp)

    return CompanySchema(
        id=comp.id,
        name=comp.name,
        business_type=comp.business_type,
        currency=comp.currency or "RUB",
        timezone=comp.timezone or "Europe/Moscow",
        closing_balance=None,
        balance_date=None,
        data_revision=comp.data_revision
    )

@router.get("/{company_id}", response_model=CompanySchema)
async def get_company(
    company_id: str,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Company).where(Company.id == company_id))
    comp = res.scalar_one_or_none()
    if not comp:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"Company {company_id} not found"
        )

    return CompanySchema(
        id=comp.id,
        name=comp.name,
        business_type=comp.business_type,
        currency=comp.currency or "RUB",
        timezone=comp.timezone or "Europe/Moscow",
        closing_balance=float(comp.closing_balance) if comp.closing_balance is not None else None,
        balance_date=comp.balance_date.strftime("%Y-%m-%d") if comp.balance_date else None,
        data_revision=comp.data_revision
    )
