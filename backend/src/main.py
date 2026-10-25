import re
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.database import init_db, async_session_factory
from src.services.auth_service import AuthService
from src.models.entities import Company, CompanyMembership
from src.api.deps import PlatformApiException
from src.api.auth import router as auth_router
from src.api.companies import router as companies_router
from src.api.statements import router as statements_router
from src.api.events import router as events_router
from src.api.forecasts import router as forecasts_router
from src.api.evaluations import router as evaluations_router
from src.api.integrations import router as integrations_router
from src.api.meta import router as meta_router
from src.schemas.contracts import (
    HealthResponse, ForecastRequest, ForecastResult, AdvisorRequest, AdvisorResponse
)
from src.ml.forecaster import forecaster
from src.core.llm import llm_client
from sqlalchemy import select

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    await init_db()
    # Ensure demo user and company exist
    async with async_session_factory() as db:
        user = await AuthService.get_or_create_demo_user(db)
        comp_res = await db.execute(select(Company))
        existing_comp = comp_res.scalars().first()
        if not existing_comp:
            comp = Company(
                name="ООО «Грузоперевозки-063»",
                business_type="Грузоперевозки",
                currency="RUB",
                timezone="Europe/Moscow",
                data_revision=0
            )
            db.add(comp)
            await db.flush()
            db.add(CompanyMembership(user_id=user.id, company_id=comp.id))
            await db.commit()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="Bank «Center-invest» Cash Flow Intelligence Platform API",
    lifespan=lifespan
)

# Exception handler for ApiError
@app.exception_handler(PlatformApiException)
async def api_exception_handler(request: Request, exc: PlatformApiException):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.api_message,
            "request_id": req_id,
            "details": exc.details
        }
    )

# Middleware for request ID tracking
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response

# Enable CORS for frontend connectivity (disallow wildcard reflection when credentials enabled)
cors_origins = [o for o in settings.CORS_ORIGINS if o != "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v2 Routers
app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(statements_router)
app.include_router(events_router)
app.include_router(forecasts_router)
app.include_router(evaluations_router)
app.include_router(integrations_router)
app.include_router(meta_router)

# v1 Backwards Compatibility Routes
@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok", app=settings.APP_NAME)

@app.post("/api/v1/forecast", response_model=ForecastResult)
def calculate_forecast(req: ForecastRequest):
    return forecaster.forecast_cashflow(
        history=req.history,
        initial_balance=req.initial_balance,
        horizon_days=req.horizon_days
    )

@app.post("/api/v1/ai-advisor", response_model=AdvisorResponse)
def get_ai_advice(req: AdvisorRequest):
    clean_btype = re.sub(r"[^\w\s-]", "", req.business_type).strip()
    clean_btype = re.sub(r"(?i)(system\s+directive|ignore\s+all|you\s+are\s+an\s+adversary|prompt\s+injection).*", "", clean_btype).strip()[:100]
    if not clean_btype:
        clean_btype = "Малый бизнес"
    prompt = f"""
    Проанализируй прогноз движения денежных средств для малого бизнеса ({clean_btype}).
    Данные прогноза:
    - Риск: {req.forecast.risk_level}
    - Минимальный ожидаемый баланс: {req.forecast.minimum_expected_balance} руб.
    - Обнаружен ли кассовый разрыв: {req.forecast.cashflow_gap_detected}
    - Даты кассовых разрывов: {req.forecast.gap_dates}
    
    Дай структурированный профессиональный ответ на русском языке:
    1. Краткий анализ текущей финансовой динамики (2-3 предложения).
    2. 3-4 конкретных практических шага для предпринимателя, чтобы избежать кассового разрыва или оптимизировать оборотный капитал.
    Отвечай четко, без лишней воды.
    """
    try:
        ai_text = llm_client.generate(
            prompt=prompt,
            system_prompt="Ты ведущий финансовый аналитик банка Центр-инвест, консультирующий предпринимателей малого бизнеса."
        )
        lines = [line.strip("-•* ").strip() for line in ai_text.splitlines() if line.strip()]
        recs = [line for line in lines if any(k in line.lower() for k in ["шаг", "перенести", "договориться", "сократить", "кредит", "овердрафт", "факторинг", "ускорить", "скидк"])]
        if not recs:
            recs = [
                "Провести переговоры с поставщиками об отсрочке платежей на 7-10 дней.",
                "Стимулировать дебиторскую задолженность предоставлением скидки 3% за досрочную оплату.",
                "Подключить овердрафт банка Центр-инвест для покрытия локальных разрывов ликвидности."
            ]

        return AdvisorResponse(
            analysis=ai_text,
            recommendations=recs[:4],
            urgent_action_required=req.forecast.cashflow_gap_detected
        )
    except Exception as e:
        return AdvisorResponse(
            analysis=f"Аналитический совет временно недоступен ({str(e)}). По прогнозу: уровень риска {req.forecast.risk_level}.",
            recommendations=[
                "Контролировать график дебиторской и кредиторской задолженности.",
                "Сформировать финансовую подушку безопасности на 14 дней операционных расходов."
            ],
            urgent_action_required=req.forecast.cashflow_gap_detected
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
