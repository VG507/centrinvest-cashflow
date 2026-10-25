import json
from typing import Literal
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.statement_service import StatementService
from src.schemas.contracts import (
    ColumnMapping, ImportResponse, Transaction, TransactionListResponse,
    ActualsResponse, CategoryUpdateRequest
)
from src.api.deps import AntigravityApiException, verify_company_access
from src.models.entities import User

router = APIRouter(prefix="/api/v2/companies/{company_id}", tags=["statements"])

@router.post("/imports", response_model=ImportResponse)
async def import_statement(
    company_id: str,
    file: UploadFile = File(...),
    format: Literal["csv", "xlsx", "1c"] = Form("csv"),
    column_mapping: str = Form("{}"),
    balance_policy: Literal["reject_conflicts", "use_last_row"] = Form("reject_conflicts"),
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        mapping_dict = json.loads(column_mapping) if column_mapping else {}
    except Exception:
        mapping_dict = {}

    mapping = ColumnMapping(**mapping_dict) if mapping_dict else ColumnMapping()

    content = await file.read()
    res = await StatementService.import_file(
        db=db,
        company_id=company_id,
        file_bytes=content,
        format_type=format,
        mapping=mapping,
        balance_policy=balance_policy
    )
    return res

@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    company_id: str,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    direction: Literal["income", "expense"] | None = Query(None),
    category_id: str | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    return await StatementService.list_transactions(
        db=db,
        company_id=company_id,
        limit=limit,
        cursor=cursor,
        from_date=from_date,
        to_date=to_date,
        direction=direction,
        category_id=category_id,
        search=search
    )

@router.get("/transactions/export")
async def export_transactions(
    company_id: str,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    csv_content = await StatementService.export_csv(
        db=db,
        company_id=company_id,
        from_date=from_date,
        to_date=to_date
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="transactions_{company_id}.csv"'}
    )

@router.patch("/transactions/{transaction_id}/category", response_model=Transaction)
async def update_transaction_category(
    company_id: str,
    transaction_id: str,
    req: CategoryUpdateRequest,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await StatementService.update_category(
            db=db,
            company_id=company_id,
            transaction_id=transaction_id,
            category_id=req.category_id
        )
    except KeyError as e:
        raise AntigravityApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e)
        )

@router.get("/actuals", response_model=ActualsResponse)
async def get_actuals(
    company_id: str,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    granularity: Literal["day", "week"] | None = Query("day"),
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    return await StatementService.get_actuals(
        db=db,
        company_id=company_id,
        from_date=from_date,
        to_date=to_date,
        granularity=granularity or "day"
    )
