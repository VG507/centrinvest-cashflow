from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.integration_service import IntegrationService
from src.schemas.contracts import IntegrationListResponse, IntegrationSyncResponse
from src.api.deps import PlatformApiException, verify_company_access
from src.models.entities import User

router = APIRouter(prefix="/api/v2/companies/{company_id}", tags=["integrations"])

@router.get("/integrations", response_model=IntegrationListResponse)
async def list_integrations(
    company_id: str,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    return await IntegrationService.get_integrations(db, company_id)

@router.post("/integrations/{integration_id}/sync", response_model=IntegrationSyncResponse)
async def sync_integration(
    company_id: str,
    integration_id: str,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await IntegrationService.sync_integration(db, company_id, integration_id)
    except KeyError as e:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e)
        )
