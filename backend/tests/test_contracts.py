import pytest
import httpx
from src.main import app

EXPECTED_ROUTES = [
    ("GET", "/health"),
    ("POST", "/api/v1/forecast"),
    ("POST", "/api/v1/ai-advisor"),
    ("GET", "/api/v2/capabilities"),
    ("POST", "/api/v2/auth/login"),
    ("GET", "/api/v2/auth/session"),
    ("POST", "/api/v2/auth/logout"),
    ("GET", "/api/v2/companies"),
    ("POST", "/api/v2/companies"),
    ("GET", "/api/v2/companies/{company_id}"),
    ("GET", "/api/v2/categories"),
    ("POST", "/api/v2/companies/{company_id}/imports"),
    ("GET", "/api/v2/companies/{company_id}/transactions"),
    ("PATCH", "/api/v2/companies/{company_id}/transactions/{transaction_id}/category"),
    ("GET", "/api/v2/companies/{company_id}/actuals"),
    ("GET", "/api/v2/companies/{company_id}/recurring"),
    ("GET", "/api/v2/companies/{company_id}/events"),
    ("POST", "/api/v2/companies/{company_id}/events"),
    ("PUT", "/api/v2/companies/{company_id}/events/{event_id}"),
    ("POST", "/api/v2/companies/{company_id}/external-events"),
    ("POST", "/api/v2/companies/{company_id}/forecasts"),
    ("GET", "/api/v2/companies/{company_id}/forecasts/{forecast_id}"),
    ("POST", "/api/v2/companies/{company_id}/forecasts/{forecast_id}/updates"),
    ("POST", "/api/v2/companies/{company_id}/forecasts/{forecast_id}/scenarios"),
    ("GET", "/api/v2/companies/{company_id}/plan-actual"),
    ("POST", "/api/v2/companies/{company_id}/evaluations"),
    ("GET", "/api/v2/companies/{company_id}/evaluations/{evaluation_id}"),
    ("POST", "/api/v2/companies/{company_id}/forecasts/{forecast_id}/advice"),
    ("GET", "/api/v2/companies/{company_id}/integrations"),
    ("POST", "/api/v2/companies/{company_id}/integrations/{integration_id}/sync"),
]

def test_api_routes_coverage():
    schema = app.openapi()
    paths = schema["paths"]
    registered = set()
    for path, methods in paths.items():
        for m in methods.keys():
            registered.add((m.upper(), path))

    for method, path in EXPECTED_ROUTES:
        assert (method, path) in registered, f"Route ({method}, {path}) is missing from OpenAPI schema"

@pytest.mark.asyncio
async def test_capabilities(client: httpx.AsyncClient):
    resp = await client.get("/api/v2/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["contract_version"] == "2.0.0"
    assert "imports" in data["features"]
    assert "forecast_v2" in data["features"]
    assert "scenarios" in data["features"]

@pytest.mark.asyncio
async def test_categories(client: httpx.AsyncClient):
    resp = await client.get("/api/v2/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 11
    ids = [c["id"] for c in data["items"]]
    assert "sales" in ids
    assert "payroll" in ids
    assert "taxes" in ids

@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_v1_forecast(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/v1/forecast",
        json={
            "initial_balance": 100000.0,
            "horizon_days": 14,
            "history": [
                {"date": "2026-10-01", "income": 50000.0, "expense": 20000.0},
                {"date": "2026-10-02", "income": 30000.0, "expense": 40000.0}
            ]
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["predicted_dates"]) == 14
    assert len(data["predicted_balance"]) == 14
