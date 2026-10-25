from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from src.schemas.contracts import CapabilitiesResponse, CategoryListResponse, Category, HealthResponse
from src.services.category_service import CategoryService
from src.config import settings

router = APIRouter(prefix="/api/v2", tags=["meta"])

@router.get("/health", response_model=HealthResponse)
async def health_check_v2():
    return HealthResponse(status="ok", app=settings.APP_NAME)

@router.get("/openapi.json", include_in_schema=False)
async def get_openapi_schema(request: Request):
    return JSONResponse(request.app.openapi())

@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities():
    return CapabilitiesResponse(
        contract_version="2.0.0",
        features=[
            "imports",
            "categorization",
            "recurring",
            "forecast_v2",
            "probability",
            "events",
            "scenarios",
            "plan_actual",
            "evaluation",
            "integrations",
            "advice"
        ]
    )

@router.get("/categories", response_model=CategoryListResponse)
async def get_categories():
    cats = CategoryService.get_categories()
    items = [Category(**c) for c in cats]
    return CategoryListResponse(items=items)
