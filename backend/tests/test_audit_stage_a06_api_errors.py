import uuid
import pytest
import httpx
from src.database import async_session_factory
from src.models.entities import Company, CompanyMembership, User
from src.services.auth_service import hash_password

# ==============================================================================
# STAGE A06: API Error Protocols, HTTP Status Code Uniformity, and Provenance
# ==============================================================================

@pytest.mark.asyncio
async def test_a06_api_error_response_conformance(client: httpx.AsyncClient):
    """
    Stage A06:
    Verify that all API errors conform strictly to ApiError contract:
    { "code": str, "message": str, "request_id": str, "details": list }
    and that X-Request-ID header is always present in response.
    """
    # 1. 401 Unauthorized
    r401 = await client.get("/api/v2/companies")
    assert r401.status_code == 401
    assert "X-Request-ID" in r401.headers
    d401 = r401.json()
    assert d401["code"] == "unauthorized"
    assert "request_id" in d401
    assert isinstance(d401.get("details", []), list)

    # 2. 404 Not Found (authenticated demo user requesting non-existent resource)
    login_resp = await client.post(
        "/api/v2/auth/login",
        json={"email": "demo@centrinvest.ru", "password": "password123"}
    )
    assert login_resp.status_code == 200

    # Request non-existent company
    fake_cid = f"fake-{uuid.uuid4()}"
    r403 = await client.get(f"/api/v2/companies/{fake_cid}")
    # User does not have access to non-existent company -> forbidden or not found
    assert r403.status_code in (403, 404)
    d403 = r403.json()
    assert d403["code"] in ("forbidden", "not_found")
    assert "request_id" in d403

    # Create owned company to test 404 for missing child resources
    comp_resp = await client.post("/api/v2/companies", json={
        "name": f"ООО «Ошибки_{uuid.uuid4().hex[:6]}»",
        "business_type": "Услуги",
        "timezone": "Europe/Moscow"
    })
    assert comp_resp.status_code == 201
    cid = comp_resp.json()["id"]

    # Non-existent forecast
    r_fc404 = await client.get(f"/api/v2/companies/{cid}/forecasts/fc-non-existent")
    assert r_fc404.status_code == 404
    d_fc404 = r_fc404.json()
    assert d_fc404["code"] == "not_found"

    # Non-existent evaluation
    r_ev404 = await client.get(f"/api/v2/companies/{cid}/evaluations/eval-non-existent")
    assert r_ev404.status_code == 404
    d_ev404 = r_ev404.json()
    assert d_ev404["code"] == "not_found"

    # 3. 422 Insufficient Data (attempting evaluation with zero transactions)
    r_ev422 = await client.post(f"/api/v2/companies/{cid}/evaluations", json={
        "training_end_date": "2026-09-01",
        "test_days": 30,
        "folds": 2,
        "models": ["weekday_mean"]
    })
    assert r_ev422.status_code == 422
    d_ev422 = r_ev422.json()
    assert d_ev422["code"] == "insufficient_data"


@pytest.mark.asyncio
async def test_a06_optimistic_concurrency_409_conflict(client: httpx.AsyncClient):
    """
    Stage A06:
    Verify that state mutations with stale data revisions return HTTP 409 Conflict.
    """
    # Login demo user
    await client.post(
        "/api/v2/auth/login",
        json={"email": "demo@centrinvest.ru", "password": "password123"}
    )

    # Create company
    comp_resp = await client.post("/api/v2/companies", json={
        "name": f"ООО «Конфликт_{uuid.uuid4().hex[:6]}»",
        "business_type": "Торговля",
        "timezone": "Europe/Moscow"
    })
    cid = comp_resp.json()["id"]

    # Create planned event
    ev_resp = await client.post(f"/api/v2/companies/{cid}/events", json={
        "title": "Оплата серверов",
        "kind": "manual",
        "direction": "expense",
        "amount": 25000.0,
        "due_date": "2026-09-15",
        "category_id": "suppliers",
        "source": {
            "kind": "manual",
            "source_id": None,
            "external_id": None,
            "label": "Ручной ввод"
        }
    })
    assert ev_resp.status_code == 201
    ev_id = ev_resp.json()["id"]

    # Attempt update event with stale expected_data_revision (e.g. revision 999)
    upd_resp = await client.put(
        f"/api/v2/companies/{cid}/events/{ev_id}?expected_data_revision=999",
        json={
            "title": "Оплата серверов Cloud",
            "kind": "manual",
            "direction": "expense",
            "amount": 28000.0,
            "due_date": "2026-09-15",
            "category_id": "suppliers",
            "source": {
                "kind": "manual",
                "source_id": None,
                "external_id": None,
                "label": "Ручной ввод"
            },
            "cancelled": False
        }
    )
    assert upd_resp.status_code == 409
    err = upd_resp.json()
    assert err["code"] == "conflict"
    assert "request_id" in err
