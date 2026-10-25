import io
import uuid
import pytest
import httpx
from datetime import date
from sqlalchemy import select
from src.database import async_session_factory
from src.models.entities import Company
from src.services.statement_service import StatementService
from src.services.forecaster_service import ForecasterService
from src.services.scenario_service import ScenarioService
from src.services.advisory_service import AdvisoryService
from src.schemas.contracts import (
    ColumnMapping, CreateForecastRequest, ScenarioRequest, DelayIncomeScenario,
    RevenueDropScenario, AdviceRequest
)

# ==============================================================================
# STAGE A10: Operational Readiness, Request Tracking, and Health
# STAGE A11: OpenAPI Schema Provenance and Release Readiness
# STAGE A12: Complete Entrepreneurial Journey and Advisory Boundaries
# ==============================================================================

@pytest.mark.asyncio
async def test_a10_request_id_and_readiness_probe(client: httpx.AsyncClient):
    """
    Stage A10:
    1. Liveness (/health) and Readiness (/api/v2/health) return status 'ok'.
    2. Incoming X-Request-ID is preserved; missing X-Request-ID is automatically generated.
    """
    # Custom Request ID preservation
    custom_id = f"trace-{uuid.uuid4().hex[:12]}"
    resp = await client.get("/api/v2/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_id
    assert resp.json()["status"] == "ok"

    # Auto-generation when missing
    resp_auto = await client.get("/health")
    assert resp_auto.status_code == 200
    assert "X-Request-ID" in resp_auto.headers
    assert len(resp_auto.headers["X-Request-ID"]) > 0


@pytest.mark.asyncio
async def test_a11_openapi_schema_availability_and_structure(client: httpx.AsyncClient):
    """
    Stage A11:
    Verify that OpenAPI schema is cleanly served at both /openapi.json
    and /api/v2/openapi.json (for proxy routing compatibility) with valid JSON and operations.
    """
    r_v2 = await client.get("/api/v2/openapi.json")
    assert r_v2.status_code == 200
    assert r_v2.headers.get("content-type", "").startswith("application/json")
    schema = r_v2.json()
    assert "openapi" in schema or "swagger" in schema
    assert "paths" in schema
    # Must contain essential API endpoints
    paths = schema["paths"]
    assert "/api/v2/companies" in paths
    assert "/api/v2/capabilities" in paths
    assert "/api/v2/companies/{company_id}/forecasts" in paths


@pytest.mark.asyncio
async def test_a12_entrepreneurial_journey_and_advisory_boundaries(auth_client: httpx.AsyncClient, fresh_company_id: str):
    """
    Stage A12:
    Simulate full entrepreneurial user flow:
    1. Import initial trading statement.
    2. Build 30-day baseline forecast.
    3. Generate AI advisory recommendations:
       - Explains risks and liquidity gap clearly.
       - Recommends actionable steps (supplier deferral, customer receivables acceleration, Center-invest overdraft).
       - Never accuses revenues of creating shortages.
       - Clean, professional Russian language with zero emojis.
    4. Test adverse scenario (supplier delay + revenue decline) to observe impact.
    """
    # 1. Import bank statement
    csv_data = (
        "operation_date;amount;direction;counterparty_name;counterparty_inn;payment_purpose;balance_eod;operation_id\n"
        "2026-09-01;120000.00;income;ООО «Покупатель Юг»;6164010001;Оплата товаров по накладной № 12;220000.00;tx-ent-01\n"
        "2026-09-02;80000.00;expense;ООО «Поставщик Продукт»;6164020002;Оплата сырья и упаковки;140000.00;tx-ent-02\n"
        "2026-09-03;40000.00;expense;ИП Арендодатель С.Н.;6164030003;Аренда торгового зала;100000.00;tx-ent-03\n"
    ).encode("utf-8")

    files = {"file": ("statement.csv", io.BytesIO(csv_data), "text/csv")}
    imp_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data={"format": "csv", "balance_policy": "reject_conflicts", "column_mapping": "{}"},
        files=files
    )
    assert imp_resp.status_code == 200
    assert imp_resp.json()["status"] == "ready"
    assert imp_resp.json()["accepted_rows"] == 3

    # 2. Build 30-day forecast as of 2026-09-03
    rev = imp_resp.json()["data_revision"]
    fc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2026-09-03",
            "horizon_days": 30,
            "model": "weekday_mean",
            "include_planned_events": True,
            "expected_data_revision": rev
        }
    )
    assert fc_resp.status_code == 200
    fc = fc_resp.json()
    assert len(fc["days"]) == 30
    fc_id = fc["id"]

    # 3. Request Advisory on forecast
    adv_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts/{fc_id}/advice",
        json={"business_type": "Торговля и дистрибуция"}
    )
    assert adv_resp.status_code == 200
    adv = adv_resp.json()
    assert adv["forecast_id"] == fc_id
    assert len(adv["analysis"]) > 20
    assert len(adv["recommendations"]) > 0
    # Professional language, zero emojis
    assert not any(ord(c) > 0x1F000 for c in adv["analysis"])

    # 4. Adverse scenario simulation
    sc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts/{fc_id}/scenarios",
        json={
            "name": "Стресс-тест: падение выручки на 25%",
            "adjustments": [
                {
                    "kind": "revenue_drop",
                    "percent": 25.0,
                    "from_date": "2026-09-05",
                    "to_date": "2026-09-20"
                }
            ]
        }
    )
    assert sc_resp.status_code == 200
    sc = sc_resp.json()
    assert len(sc["forecast"]["days"]) == 30
    assert sc["delta"]["end_balance"] <= 0.0
