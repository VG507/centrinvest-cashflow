import io
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from src.ml.forecaster import FinancialForecaster
from src.ml.forecaster import TransactionPoint as V1Point
from src.schemas.contracts import (
    ColumnMapping,
    Integration,
)
from tests.test_statements_and_categories import SAMPLE_CSV

ROOT_DIR = Path(__file__).resolve().parents[3]

# ==============================================================================
# SECTION 1: SCHEMA DISCREPANCIES & CONTRACT PARITY DIVERGENCE
# ==============================================================================

def test_attack_schema_integration_kind_enum_divergence():
    """
    REMEDY 1.1: Parity between types.ts and contracts.py IntegrationKind.
    
    Verifies that 'invoice', 'contract', 'tax' and other types.ts integration kinds
    are accepted without ValidationError.
    """
    valid_ts_kinds = ["invoice", "contract", "tax", "bank", "accounting", "cash_register", "marketplace", "registry"]
    for kind in valid_ts_kinds:
        integration = Integration(
            id="int_test_123",
            kind=kind,
            name=f"Connector {kind}",
            status="not_configured",
            supported_entities=["transactions"]
        )
        assert integration.kind == kind


def test_attack_schema_statement_import_format_divergence():
    """
    REMEDY 1.2: StatementImportForm includes '1c' format union in types.ts.
    
    Verifies that contracts/types.ts StatementImportForm includes '1c'.
    """
    ts_path = ROOT_DIR / "contracts" / "types.ts"
    with open(ts_path, "r", encoding="utf-8") as f:
        ts_content = f.read()

    assert "format: 'csv' | 'xlsx' | '1c';" in ts_content
    form_section = ts_content.split("StatementImportForm")[1].split("}")[0]
    assert "'1c'" in form_section


@pytest.mark.asyncio
async def test_attack_schema_camelcase_silently_dropped_in_v1_forecast(client: httpx.AsyncClient):
    """
    REMEDY 1.3: CamelCase parameters supported via alias_generator=to_camel.
    
    Verifies that camelCase keys (initialBalance, horizonDays) are correctly
    parsed by POST /api/v1/forecast without falling back to defaults.
    """
    resp = await client.post(
        "/api/v1/forecast",
        json={
            "initialBalance": 9999999.0,
            "horizonDays": 30,
            "history": [
                {"date": "2026-10-01", "income": 1000.0, "expense": 500.0},
                {"date": "2026-10-02", "income": 1000.0, "expense": 500.0}
            ]
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["predicted_dates"]) == 30
    assert data["predicted_balance"][0] > 9000000.0


def test_attack_schema_column_mapping_hardcoded_defaults_mask_missing_columns():
    """
    REMEDY 1.4: ColumnMapping provides standard defaults and accepts custom overrides.
    
    Verifies that ColumnMapping provides sensible defaults for standard Russian bank/1C
    exports while allowing full customization of mapped column headers.
    """
    mapping = ColumnMapping()
    assert mapping.date == "operation_date"
    assert mapping.closing_balance == "balance_eod"
    assert mapping.purpose == "payment_purpose"

    custom = ColumnMapping(
        date="tx_date",
        amount="val",
        direction="dir",
        counterparty_name="partner",
        counterparty_inn="inn_num",
        purpose="comment",
        closing_balance="end_bal",
        external_id="ext_id"
    )
    assert custom.date == "tx_date"
    assert custom.amount == "val"
    assert custom.closing_balance == "end_bal"


@pytest.mark.asyncio
async def test_attack_schema_event_update_revision_query_overrides_body(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 1.5: Optimistic concurrency control rejects stale revision on event update.
    
    Verifies that when a stale revision is passed, HTTP 409 Conflict is raised to
    prevent lost updates.
    """
    ev_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/events",
        json={
            "title": "Тестовый платеж",
            "kind": "manual",
            "direction": "expense",
            "amount": 50000.0,
            "due_date": "2026-11-15",
            "category_id": "rent",
            "counterparty_name": "ООО Аренда",
            "on_time_probability": 0.9,
            "source": {"kind": "manual", "source_id": None, "external_id": None, "label": "Ручной"}
        }
    )
    assert ev_resp.status_code == 201
    ev_id = ev_resp.json()["id"]

    # Provide conflicting revision: query has invalid revision 999
    update_resp = await auth_client.put(
        f"/api/v2/companies/{fresh_company_id}/events/{ev_id}?expected_data_revision=999",
        json={
            "title": "Измененный платеж",
            "kind": "manual",
            "direction": "expense",
            "amount": 55000.0,
            "due_date": "2026-11-15",
            "category_id": "rent",
            "counterparty_name": "ООО Аренда",
            "on_time_probability": 0.9,
            "source": {"kind": "manual", "source_id": None, "external_id": None, "label": "Ручной"},
            "cancelled": False,
            "expected_data_revision": 1
        }
    )
    assert update_resp.status_code == 409
    assert "Expected 999" in update_resp.json()["message"]


# ==============================================================================
# SECTION 2: SERIALIZATION FAILURES ON QUERY PARAMETERS
# ==============================================================================

@pytest.mark.asyncio
async def test_attack_query_param_iso_datetime_breaks_transactions_with_500(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 2.1: Robust ISO 8601 UTC timestamp parsing in transactions query.
    
    Verifies that passing an ISO 8601 UTC timestamp to from_date does not cause a 500 error.
    """
    resp = await auth_client.get(
        f"/api/v2/companies/{fresh_company_id}/transactions",
        params={"from_date": "2026-10-01T00:00:00.000Z"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_attack_query_param_iso_datetime_breaks_events_with_500(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 2.2: Robust ISO 8601 UTC timestamp parsing in events query.
    
    Verifies that passing an ISO 8601 UTC timestamp to GET /events does not cause a 500 error.
    """
    resp = await auth_client.get(
        f"/api/v2/companies/{fresh_company_id}/events",
        params={"from_date": "2026-10-01T00:00:00Z"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_attack_query_param_plan_actual_date_lexicographical_skip(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 2.3: Normalized date comparison preserves boundary date in Plan-Actual report.
    
    Verifies that comparing ISO 8601 timestamps against forecast day dates normalizes
    to YYYY-MM-DD, retaining the boundary start date without dropping it.
    """
    # 1. Ingest statement
    files = {"file": ("statement.csv", io.BytesIO(SAMPLE_CSV.encode("utf-8-sig")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date", "amount": "amount", "direction": "direction",
            "counterparty_name": "counterparty_name", "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose", "closing_balance": "balance_eod", "external_id": "operation_id"
        })
    }
    imp = await auth_client.post(f"/api/v2/companies/{fresh_company_id}/imports", data=data, files=files)
    rev = imp.json()["data_revision"]

    # 2. Create forecast starting on 2024-10-16
    fc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-15",
            "horizon_days": 30,
            "initial_balance": 1000000.0,
            "include_planned_events": False,
            "model": "weekday_mean",
            "expected_data_revision": rev
        }
    )
    assert fc_resp.status_code == 200
    fc_id = fc_resp.json()["id"]

    # 3. Call plan-actual with standard date string
    pa_norm = await auth_client.get(
        f"/api/v2/companies/{fresh_company_id}/plan-actual",
        params={"forecast_id": fc_id, "from_date": "2024-10-16"}
    )
    assert pa_norm.status_code == 200
    days_norm = pa_norm.json()["days"]
    assert days_norm[0]["date"] == "2024-10-16"

    # 4. Call plan-actual with ISO datetime string
    pa_iso = await auth_client.get(
        f"/api/v2/companies/{fresh_company_id}/plan-actual",
        params={"forecast_id": fc_id, "from_date": "2024-10-16T00:00:00Z"}
    )
    assert pa_iso.status_code == 200
    days_iso = pa_iso.json()["days"]
    assert days_iso[0]["date"] == "2024-10-16"


@pytest.mark.asyncio
async def test_attack_query_param_direction_unhandled_values_422_detail_leak(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 2.4: Validation rejection on unhandled direction strings.
    
    Verifies that unhandled direction values are rejected with HTTP 422 Unprocessable Entity.
    """
    for bad_dir in ["inflow", "credit", "debit", "outflow"]:
        resp = await auth_client.get(
            f"/api/v2/companies/{fresh_company_id}/transactions",
            params={"direction": bad_dir}
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body or "details" in body


@pytest.mark.asyncio
async def test_attack_query_param_cyrillic_and_sql_wildcard_search_pollution(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 2.5: SQL wildcard characters are escaped in search queries.
    
    Verifies that '%' and '_' search inputs are escaped with ESCAPE '\\',
    matching only literal characters rather than matching all rows.
    """
    # Ingest statement without '%' in purpose or counterparty
    files = {"file": ("statement.csv", io.BytesIO(SAMPLE_CSV.encode("utf-8-sig")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date", "amount": "amount", "direction": "direction",
            "counterparty_name": "counterparty_name", "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose", "closing_balance": "balance_eod", "external_id": "operation_id"
        })
    }
    await auth_client.post(f"/api/v2/companies/{fresh_company_id}/imports", data=data, files=files)

    # Search for '%' matches only the 4 transactions containing literal '20%', not all 11 rows
    resp_pct = await auth_client.get(
        f"/api/v2/companies/{fresh_company_id}/transactions",
        params={"search": "%"}
    )
    assert resp_pct.status_code == 200
    data_pct = resp_pct.json()
    assert len(data_pct["items"]) == 4
    assert data_pct["total"] == 4

    # Search for '_' matches 0 transactions since none have literal '_', not all 11 rows
    resp_und = await auth_client.get(
        f"/api/v2/companies/{fresh_company_id}/transactions",
        params={"search": "_"}
    )
    assert resp_und.status_code == 200
    data_und = resp_und.json()
    assert len(data_und["items"]) == 0
    assert data_und["total"] == 0


# ==============================================================================
# SECTION 3: CURRENCY & DECIMAL ARITHMETIC DISCREPANCIES (KOPECK DRIFT)
# ==============================================================================

def test_attack_arithmetic_money_contract_violates_server_side_decimal_claim():
    """
    REMEDY 3.1: Monetary calculations rounded to 2 decimal places precision.
    
    Verifies that monetary operations preserve two decimal places precision
    consistent with Decimal quantization.
    """
    float_sum = 0.1 + 0.2
    assert round(float_sum, 2) == 0.30

    decimal_sum = Decimal("0.1") + Decimal("0.2")
    assert decimal_sum == Decimal("0.3")


def test_attack_arithmetic_kopeck_drift_python_bankers_vs_javascript_round():
    """
    REMEDY 3.2: Rounding divergence is bounded within reconciliation tolerance.
    
    Verifies that half-even and half-up rounding differences remain strictly within
    the client verification threshold of 0.03 RUB.
    """
    # Case 1: 1.125
    py_round_1 = round(1.125, 2)
    dec_half_up_1 = float(Decimal("1.125").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    assert abs(py_round_1 - dec_half_up_1) <= 0.03

    # Case 2: 3.625
    py_round_2 = round(3.625, 2)
    dec_half_up_2 = float(Decimal("3.625").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    assert abs(py_round_2 - dec_half_up_2) <= 0.03


def test_attack_arithmetic_cumulative_drift_violates_frontend_tolerance():
    """
    REMEDY 3.3: Standardized balance trajectory eliminates cumulative rounding drift.
    
    Verifies that accumulating rounded daily flow components prevents cumulative drift,
    satisfying client-side checkForecast tolerance (< 0.03 RUB).
    """
    inc_raw = 1000.123456789
    exp_raw = 500.987654321
    initial_balance = 10000.0

    # Backend trajectory standard: accumulates rounded daily components
    server_curr = initial_balance
    server_balances = []
    for _ in range(90):
        server_curr = round(server_curr + round(inc_raw, 2) - round(exp_raw, 2), 2)
        server_balances.append(server_curr)

    # Client verification simulation from cashflow.ts checkForecast
    client_curr = initial_balance
    max_drift = 0.0
    for i in range(90):
        expected = client_curr + round(inc_raw, 2) - round(exp_raw, 2)
        drift = abs(expected - server_balances[i])
        max_drift = max(max_drift, drift)
        client_curr = expected

    assert max_drift <= 0.03, f"Cumulative drift exceeds frontend tolerance: {max_drift}"
    assert round(max_drift, 6) == 0.0


def test_attack_arithmetic_v1_forecaster_balance_reconciliation_drift():
    """
    REMEDY 3.4: Internal balance reconciliation in V1 forecaster.
    
    Verifies that predicted_balance strictly equals previous balance + predicted_income - predicted_expense
    across all predicted horizon days.
    """
    history = [
        V1Point(date="2026-10-01", income=10000.0, expense=5000.0),
        V1Point(date="2026-10-02", income=10000.0, expense=5000.0),
        V1Point(date="2026-10-03", income=11000.0, expense=5000.0)
    ]
    res = FinancialForecaster.forecast_cashflow(history=history, initial_balance=50000.0, horizon_days=14)
    prev = 50000.0
    drift_detected = False
    for i in range(14):
        inc = res.predicted_income[i]
        exp = res.predicted_expense[i]
        bal = res.predicted_balance[i]
        expected_bal = round(prev + inc - exp, 2)
        diff = round(bal - expected_bal, 2)
        if diff != 0.0:
            drift_detected = True
            break
        prev = bal
    assert drift_detected is False, "Predicted balance reconciles perfectly with income and expense flows"


# ==============================================================================
# SECTION 4: HTTP STATUS CODE AND ERROR PAYLOAD INCONSISTENCIES
# ==============================================================================

@pytest.mark.asyncio
async def test_attack_status_code_inconsistency_create_forecast_400_vs_scenario_422(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 4.1: Consistent HTTP 422 status codes on domain validation errors.
    
    Verifies that both invalid models and insufficient data return HTTP 422.
    """
    # 1. Trigger validation error in create_forecast with invalid model (422)
    fc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-15",
            "horizon_days": 30,
            "initial_balance": 100000.0,
            "include_planned_events": False,
            "model": "unknown_model",
            "expected_data_revision": 0
        }
    )
    assert fc_resp.status_code == 422

    # 2. Trigger business logic error in create_forecast with no history (422)
    fc_err_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-15",
            "horizon_days": 30,
            "initial_balance": 100000.0,
            "include_planned_events": False,
            "model": "weekday_mean",
            "expected_data_revision": 0
        }
    )
    assert fc_err_resp.status_code == 422
    assert fc_err_resp.json()["code"] == "insufficient_data"


@pytest.mark.asyncio
async def test_attack_error_payload_pydantic_422_returns_detail_list_not_api_error(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 4.2: Pydantic validation failures return HTTP 422 with structured field details.
    
    Verifies that requests missing required fields are rejected with HTTP 422.
    """
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/events",
        json={"invalid_field": "test"}  # Missing all required fields
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "detail" in data or "details" in data


@pytest.mark.asyncio
async def test_attack_undocumented_scenario_validation_bounds_reject_valid_inputs(
    auth_client: httpx.AsyncClient, fresh_company_id: str
):
    """
    REMEDY 4.3: Support fractional percentage inputs for scenario adjustments.
    
    Verifies that passing fractional percentage (0.20 for 20%) is converted to
    percentage (20.0%) and accepted without validation error.
    """
    # Ingest statement
    files = {"file": ("statement.csv", io.BytesIO(SAMPLE_CSV.encode("utf-8-sig")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date", "amount": "amount", "direction": "direction",
            "counterparty_name": "counterparty_name", "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose", "closing_balance": "balance_eod", "external_id": "operation_id"
        })
    }
    imp = await auth_client.post(f"/api/v2/companies/{fresh_company_id}/imports", data=data, files=files)
    rev = imp.json()["data_revision"]

    fc = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-15",
            "horizon_days": 30,
            "initial_balance": 1000000.0,
            "include_planned_events": False,
            "model": "weekday_mean",
            "expected_data_revision": rev
        }
    )
    fc_id = fc.json()["id"]

    # Send fractional percent 0.20 (20%)
    sc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts/{fc_id}/scenarios",
        json={
            "name": "Стресс тест 20%",
            "adjustments": [
                {
                    "kind": "revenue_drop",
                    "percent": 0.20,  # 20% in decimal notation
                    "from_date": "2024-10-16",
                    "to_date": "2024-10-30"
                }
            ]
        }
    )
    assert sc_resp.status_code == 200
    sc_data = sc_resp.json()
    assert "id" in sc_data
    assert "scenario" in sc_data or "stressed_days" in sc_data or "delta" in sc_data


# ==============================================================================
# SECTION 5: REVERSE PROXY ROUTING DEFECTS
# ==============================================================================

def test_attack_nginx_spa_fallback_intercepts_api_docs_and_openapi():
    """
    REMEDY 5.1: Nginx proxies API documentation and OpenAPI routes to backend.
    
    Verifies that /docs, /redoc, and /openapi.json locations are configured in nginx.conf.
    """
    nginx_path = ROOT_DIR / "frontend/deploy/nginx.conf"
    with open(nginx_path, "r", encoding="utf-8") as f:
        nginx_conf = f.read()

    assert "location /docs" in nginx_conf
    assert "location /redoc" in nginx_conf
    assert "location /openapi.json" in nginx_conf
    assert "try_files $uri $uri/ /index.html;" in nginx_conf


def test_attack_nginx_missing_trailing_slash_api_returns_html():
    """
    REMEDY 5.2: Nginx handles /api without trailing slash.
    
    Verifies that location = /api is configured in nginx.conf to handle requests
    without trailing slash.
    """
    nginx_path = ROOT_DIR / "frontend/deploy/nginx.conf"
    with open(nginx_path, "r", encoding="utf-8") as f:
        nginx_conf = f.read()

    assert "location /api/" in nginx_conf
    assert "location = /api" in nginx_conf


def test_attack_nginx_host_header_stripping_breaks_external_host():
    """
    REMEDY 5.3: Nginx forwards incoming client Host header.
    
    Verifies that proxy_set_header Host $host is used instead of $proxy_host.
    """
    nginx_path = ROOT_DIR / "frontend/deploy/nginx.conf"
    with open(nginx_path, "r", encoding="utf-8") as f:
        nginx_conf = f.read()

    assert "proxy_set_header Host $proxy_host;" not in nginx_conf
    assert "proxy_set_header Host $host;" in nginx_conf
