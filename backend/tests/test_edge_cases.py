import io
import json
import pytest
import httpx

@pytest.mark.asyncio
async def test_empty_statement_rejection(auth_client: httpx.AsyncClient, fresh_company_id: str):
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": "{}"
    }
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "rejected"
    assert any(iss["code"] == "empty_file" for iss in res["issues"])

@pytest.mark.asyncio
async def test_conflicting_balances_rejection(auth_client: httpx.AsyncClient, fresh_company_id: str):
    csv_conflict = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C999;OP-1;2024-10-01;1000.00;Списание;001;Тест;Платеж 1;100000.00
C999;OP-2;2024-10-01;2000.00;Списание;001;Тест;Платеж 2;150000.00
"""
    files = {"file": ("conflict.csv", io.BytesIO(csv_conflict.encode("utf-8")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date",
            "amount": "amount",
            "direction": "direction",
            "counterparty_name": "counterparty_name",
            "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose",
            "closing_balance": "balance_eod",
            "external_id": "operation_id"
        })
    }
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "rejected"
    assert any(iss["code"] == "conflicting_daily_balance" for iss in res["issues"])

@pytest.mark.asyncio
async def test_empty_history_forecast_insufficient_data(auth_client: httpx.AsyncClient, fresh_company_id: str):
    # Forecasting on company without imported data returns 422
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-01",
            "horizon_days": 30,
            "initial_balance": 100000.0,
            "include_planned_events": True,
            "model": "auto",
            "expected_data_revision": 0
        }
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "insufficient_data"

@pytest.mark.asyncio
async def test_negative_starting_balance(auth_client: httpx.AsyncClient, fresh_company_id: str):
    # Import minimal valid operation
    csv_valid = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C999;OP-10;2024-10-01;5000.00;Поступление;001;Клиент;Оплата;-50000.00
"""
    files = {"file": ("valid.csv", io.BytesIO(csv_valid.encode("utf-8")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date",
            "amount": "amount",
            "direction": "direction",
            "counterparty_name": "counterparty_name",
            "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose",
            "closing_balance": "balance_eod",
            "external_id": "operation_id"
        })
    }
    imp_resp = await auth_client.post(f"/api/v2/companies/{fresh_company_id}/imports", data=data, files=files)
    rev = imp_resp.json()["data_revision"]

    # Forecast with negative initial balance
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-01",
            "horizon_days": 30,
            "initial_balance": -50000.0,
            "include_planned_events": False,
            "model": "weekday_mean",
            "expected_data_revision": rev
        }
    )
    assert resp.status_code == 200
    fc = resp.json()
    assert fc["summary"]["risk_level"] == "critical"
    assert len(fc["gaps"]) > 0
    assert fc["gaps"][0]["start_date"] == "2024-10-02"

@pytest.mark.asyncio
async def test_stale_data_revision_rejection(auth_client: httpx.AsyncClient, fresh_company_id: str):
    csv_valid = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C999;OP-REV;2024-10-01;5000.00;Поступление;001;Клиент;Оплата;50000.00
"""
    files = {"file": ("valid.csv", io.BytesIO(csv_valid.encode("utf-8")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date",
            "amount": "amount",
            "direction": "direction",
            "counterparty_name": "counterparty_name",
            "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose",
            "closing_balance": "balance_eod",
            "external_id": "operation_id"
        })
    }
    await auth_client.post(f"/api/v2/companies/{fresh_company_id}/imports", data=data, files=files)

    # Forecast with wrong revision -> 409 Conflict
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-01",
            "horizon_days": 30,
            "initial_balance": 50000.0,
            "include_planned_events": False,
            "model": "weekday_mean",
            "expected_data_revision": 9999
        }
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"

@pytest.mark.asyncio
async def test_invalid_scenario_bounds(auth_client: httpx.AsyncClient, fresh_company_id: str):
    # Import history
    csv_valid = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C999;OP-20;2024-10-01;10000.00;Поступление;001;Клиент;Оплата;100000.00
"""
    files = {"file": ("valid.csv", io.BytesIO(csv_valid.encode("utf-8")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date",
            "amount": "amount",
            "direction": "direction",
            "counterparty_name": "counterparty_name",
            "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose",
            "closing_balance": "balance_eod",
            "external_id": "operation_id"
        })
    }
    imp_resp = await auth_client.post(f"/api/v2/companies/{fresh_company_id}/imports", data=data, files=files)
    rev = imp_resp.json()["data_revision"]

    fc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-01",
            "horizon_days": 30,
            "initial_balance": 100000.0,
            "include_planned_events": False,
            "model": "weekday_mean",
            "expected_data_revision": rev
        }
    )
    fc_id = fc_resp.json()["id"]

    # Scenario with revenue drop > 30% (e.g. 50%) should be rejected
    scen_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts/{fc_id}/scenarios",
        json={
            "name": "Invalid scenario",
            "adjustments": [
                {
                    "kind": "revenue_drop",
                    "percent": 50.0,
                    "from_date": "2024-10-02",
                    "to_date": "2024-10-15"
                }
            ]
        }
    )
    assert scen_resp.status_code == 422
    assert scen_resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_atomic_import_rejection_on_malformed_row(auth_client: httpx.AsyncClient, fresh_company_id: str):
    """
    Verify atomic import: if a statement contains any malformed row (e.g. invalid date 2026-02-30),
    the entire import is rejected with status='rejected', 0 rows accepted, and no partial commit.
    """
    csv_mixed = (
        "company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod\n"
        "C999;OP-VALID;2024-10-01;5000.00;Поступление;7701000001;ООО Клиент;Оплата услуг;100000.00\n"
        "C999;OP-INVALID;2026-02-30;2000.00;Списание;7701000002;ООО Поставщик;Оплата товара;98000.00\n"
    )
    files = {"file": ("mixed.csv", io.BytesIO(csv_mixed.encode("utf-8")), "text/csv")}
    data = {
        "format": "csv",
        "balance_policy": "reject_conflicts",
        "column_mapping": json.dumps({
            "date": "operation_date",
            "amount": "amount",
            "direction": "direction",
            "counterparty_name": "counterparty_name",
            "counterparty_inn": "counterparty_inn",
            "purpose": "payment_purpose",
            "closing_balance": "balance_eod",
            "external_id": "operation_id"
        })
    }
    resp = await auth_client.post(f"/api/v2/companies/{fresh_company_id}/imports", data=data, files=files)
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "rejected"
    assert res["accepted_rows"] == 0
    assert res["rejected_rows"] == 2
    assert any(iss["code"] == "invalid_date" for iss in res["issues"])

    # Verify zero transactions were committed in the ledger
    tx_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/transactions")
    assert tx_resp.status_code == 200
    assert tx_resp.json()["total"] == 0
