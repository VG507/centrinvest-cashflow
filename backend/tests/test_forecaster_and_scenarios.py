import io
import json
import pytest
import httpx
from tests.test_statements_and_categories import SAMPLE_CSV

@pytest.mark.asyncio
async def test_forecaster_scenarios_and_events(auth_client: httpx.AsyncClient, fresh_company_id: str):
    # 0. Import initial history
    files = {"file": ("statement.csv", io.BytesIO(SAMPLE_CSV.encode("utf-8-sig")), "text/csv")}
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
    imp_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files
    )
    rev = imp_resp.json()["data_revision"]

    # 1. Create a planned invoice and tax event
    ev_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/events",
        json={
            "title": "Оплата от ключевого заказчика ООО «Логистик-Групп»",
            "kind": "invoice",
            "direction": "income",
            "amount": 400000.0,
            "due_date": "2024-10-20",
            "category_id": "sales",
            "counterparty_name": "ООО «Логистик-Групп»",
            "on_time_probability": 0.85,
            "source": {
                "kind": "invoice",
                "source_id": None,
                "external_id": "INV-1092",
                "label": "Счет на оплату № 1092"
            }
        }
    )
    assert ev_resp.status_code == 201
    created_ev = ev_resp.json()
    assert created_ev["id"] is not None
    event_id = created_ev["id"]

    # 2. Ingest external tax event via batch API
    tax_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/external-events",
        json={
            "source": {"kind": "tax", "source_id": None, "external_id": None, "label": "ФНС РФ"},
            "invoices": [],
            "contracts": [],
            "taxes": [
                {
                    "external_id": "TAX-2024-10-28",
                    "title": "Единый налоговый платеж (ЕНП)",
                    "due_date": "2024-10-28",
                    "amount": 250000.0,
                    "period": "Октябрь 2024",
                    "authority_source_url": "https://nalog.gov.ru",
                    "confirmed_by_user": True
                }
            ]
        }
    )
    assert tax_resp.status_code == 200
    assert len(tax_resp.json()["created_events"]) == 1
    rev = tax_resp.json()["data_revision"]

    # 3. Create 30-day forecast snapshot
    fc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2024-10-15",
            "horizon_days": 30,
            "initial_balance": 500000.0,
            "include_planned_events": True,
            "model": "auto",
            "expected_data_revision": rev
        }
    )
    assert fc_resp.status_code == 200
    fc = fc_resp.json()
    assert len(fc["days"]) == 30
    assert fc["horizon_days"] == 30
    assert fc["summary"]["closing_balance"] == 500000.0
    forecast_id = fc["id"]

    # Invariant: balance continuity check
    curr_bal = fc["summary"]["closing_balance"]
    for day in fc["days"]:
        curr_bal += (day["predicted_income"] - day["predicted_expense"])
        assert abs(curr_bal - day["predicted_balance"]) < 0.05, f"Balance mismatch on {day['date']}"
        if day["balance_lower"] is not None and day["balance_upper"] is not None:
            assert day["balance_lower"] <= day["balance_upper"]

    # 4. Adverse Scenario Simulation (Stress Testing)
    scen_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts/{forecast_id}/scenarios",
        json={
            "name": "Негативный стресс-сценарий (задержка оплат 21 день + падение продаж 15%)",
            "adjustments": [
                {
                    "kind": "delay_income",
                    "event_id": event_id,
                    "delay_days": 21
                },
                {
                    "kind": "revenue_drop",
                    "percent": 15.0,
                    "from_date": "2024-10-16",
                    "to_date": "2024-10-31"
                }
            ]
        }
    )
    assert scen_resp.status_code == 200
    scen = scen_resp.json()
    assert scen["base_forecast_id"] == forecast_id
    assert scen["delta"]["end_balance"] <= 0
    assert len(scen["forecast"]["days"]) == 30

    # 5. Advisory recommendations for forecast
    adv_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts/{forecast_id}/advice",
        json={"business_type": "Грузоперевозки"}
    )
    assert adv_resp.status_code == 200
    adv = adv_resp.json()
    assert len(adv["recommendations"]) >= 2
    assert adv["mode"] in ("llm", "rules")
    assert len(adv["analysis"]) > 20

    # 6. Incremental forecast update
    # Get current company revision
    comp_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}")
    rev = comp_resp.json()["data_revision"]

    upd_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts/{forecast_id}/updates",
        json={
            "changed_from_date": "2024-10-25",
            "expected_data_revision": rev
        }
    )
    assert upd_resp.status_code == 200
    upd = upd_resp.json()
    assert upd["mode"] == "incremental"
    assert len(upd["forecast"]["days"]) == 30
