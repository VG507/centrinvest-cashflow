from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.evaluation_service import EvaluationService
from src.schemas.contracts import EvaluationRequest, EvaluationResponse
from src.api.deps import PlatformApiException, verify_company_access
from src.models.entities import User

router = APIRouter(prefix="/api/v2/companies/{company_id}", tags=["evaluations"])

@router.post("/evaluations", response_model=EvaluationResponse)
async def evaluate_models(
    company_id: str,
    req: EvaluationRequest,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await EvaluationService.evaluate_models(db, company_id, req)
    except ValueError as e:
        if "insufficient_data" in str(e):
            raise PlatformApiException(
                status_code=422,
                code="insufficient_data",
                message=str(e)
            )
        raise PlatformApiException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation_error",
            message=str(e)
        )
    except KeyError as e:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e)
        )

@router.get("/evaluations/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation(
    company_id: str,
    evaluation_id: str,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await EvaluationService.get_evaluation(db, company_id, evaluation_id)
    except KeyError as e:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e)
        )
