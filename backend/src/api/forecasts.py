from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.forecaster_service import ForecasterService
from src.services.scenario_service import ScenarioService
from src.services.incremental_service import IncrementalService
from src.services.reconciliation_service import ReconciliationService
from src.services.advisory_service import AdvisoryService
from src.models.entities import ForecastSnapshotRecord, User
from src.schemas.contracts import (
    CreateForecastRequest, ForecastSnapshot, ForecastUpdateRequest, ForecastUpdateResponse,
    ScenarioRequest, ScenarioResponse, PlanActualResponse, AdviceRequest, AdviceResponse
)
from src.api.deps import PlatformApiException, verify_company_access

router = APIRouter(prefix="/api/v2/companies/{company_id}", tags=["forecasts"])

@router.post("/forecasts", response_model=ForecastSnapshot)
async def create_forecast(
    company_id: str,
    req: CreateForecastRequest,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await ForecasterService.create_forecast(db, company_id, req)
    except ValueError as e:
        if "conflict" in str(e):
            raise PlatformApiException(
                status_code=status.HTTP_409_CONFLICT,
                code="conflict",
                message=str(e)
            )
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

@router.get("/forecasts/{forecast_id}", response_model=ForecastSnapshot)
async def get_forecast(
    company_id: str,
    forecast_id: str,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(
        select(ForecastSnapshotRecord).where(
            ForecastSnapshotRecord.company_id == company_id,
            ForecastSnapshotRecord.id == forecast_id
        )
    )
    rec = res.scalar_one_or_none()
    if not rec:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"Forecast {forecast_id} not found"
        )

    return ForecastSnapshot(
        id=rec.id,
        company_id=rec.company_id,
        created_at=rec.created_at.isoformat(),
        as_of_date=rec.as_of_date.strftime("%Y-%m-%d"),
        horizon_days=rec.horizon_days,
        currency=rec.currency,
        data_revision=rec.data_revision,
        model=rec.model,
        model_version=rec.model_version,
        evaluation_id=rec.evaluation_id,
        probability_method=rec.probability_method,
        interval_coverage=rec.interval_coverage,
        simulation_count=rec.simulation_count,
        random_seed=rec.random_seed,
        summary=rec.summary,
        days=rec.days,
        gaps=rec.gaps,
        warnings=rec.warnings,
        data_quality=rec.data_quality
    )

@router.post("/forecasts/{forecast_id}/updates", response_model=ForecastUpdateResponse)
async def update_forecast(
    company_id: str,
    forecast_id: str,
    req: ForecastUpdateRequest,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await IncrementalService.update_forecast(db, company_id, forecast_id, req)
    except ValueError as e:
        if "conflict" in str(e):
            raise PlatformApiException(
                status_code=status.HTTP_409_CONFLICT,
                code="conflict",
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

@router.post("/forecasts/{forecast_id}/scenarios", response_model=ScenarioResponse)
async def create_scenario(
    company_id: str,
    forecast_id: str,
    req: ScenarioRequest,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await ScenarioService.simulate_scenario(db, company_id, forecast_id, req)
    except ValueError as e:
        raise PlatformApiException(
            status_code=422,
            code="validation_error",
            message=str(e)
        )
    except KeyError as e:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e)
        )

@router.get("/plan-actual", response_model=PlanActualResponse)
async def get_plan_actual(
    company_id: str,
    forecast_id: str = Query(...),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    granularity: str = Query("day"),
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await ReconciliationService.get_plan_actual(
            db=db,
            company_id=company_id,
            forecast_id=forecast_id,
            from_date=from_date,
            to_date=to_date,
            granularity=granularity
        )
    except KeyError as e:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e)
        )

@router.post("/forecasts/{forecast_id}/advice", response_model=AdviceResponse)
async def get_forecast_advice(
    company_id: str,
    forecast_id: str,
    req: AdviceRequest,
    user: User = Depends(verify_company_access),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await AdvisoryService.get_advice(
            db=db,
            company_id=company_id,
            forecast_id=forecast_id,
            business_type=req.business_type
        )
    except KeyError as e:
        raise PlatformApiException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(e)
        )
