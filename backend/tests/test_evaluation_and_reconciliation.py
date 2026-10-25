import os
import io
import json
import pytest
import httpx

@pytest.mark.asyncio
async def test_benchmark_dataset_evaluation_and_reconciliation(auth_client: httpx.AsyncClient, fresh_company_id: str):
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    csv_path = repo_root / "fixtures" / "statements" / "C001_logistics.csv"
    if not os.path.exists(csv_path):
        csv_path = repo_root / "data" / "statements" / "C001.csv"
    if not os.path.exists(csv_path):
        pytest.skip(f"Benchmark dataset C001 not present at {csv_path}")

    with open(csv_path, "rb") as f:
        file_bytes = f.read()

    data = {
        "format": "csv",
        "balance_policy": "use_last_row",
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
    files = {"file": ("C001.csv", io.BytesIO(file_bytes), "text/csv")}

    import_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files
    )
    assert import_resp.status_code == 200
    res = import_resp.json()
    assert res["status"] == "ready"
    assert res["accepted_rows"] > 500

    # 2. Test recurring detection on 2-year history
    rec_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/recurring")
    assert rec_resp.status_code == 200
    recurring_pats = rec_resp.json()["items"]
    assert len(recurring_pats) > 0
    # Check cadence and sample counts
    for p in recurring_pats:
        assert p["cadence"] in ("weekly", "monthly", "quarterly")
        assert p["sample_count"] >= 3
        assert 0.0 <= p["confidence"] <= 1.0

    # 3. Model Evaluation (Rolling Origin 3 folds)
    eval_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/evaluations",
        json={
            "training_end_date": "2026-09-01",
            "test_days": 30,
            "folds": 3,
            "models": ["seasonal_naive", "weekday_mean", "ridge_calendar"]
        }
    )
    assert eval_resp.status_code == 200
    ev_data = eval_resp.json()
    assert len(ev_data["folds"]) >= 2
    assert len(ev_data["metrics"]) == 3
    assert ev_data["selected_model"] in ("seasonal_naive", "weekday_mean", "ridge_calendar")
    assert len(ev_data["selection_reason"]) > 10

    # Verify metric sanity
    for m in ev_data["metrics"]:
        assert m["mae_balance"] > 0
        assert m["evaluated_days"] >= 30
        if m["wape_cashflow"] is not None:
            assert m["wape_cashflow"] >= 0

    eval_id = ev_data["id"]
    get_eval_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/evaluations/{eval_id}")
    assert get_eval_resp.status_code == 200

    # 4. Create Forecast and Plan-Actual Reconciliation
    fc_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/forecasts",
        json={
            "as_of_date": "2026-08-01",
            "horizon_days": 30,
            "initial_balance": None,  # automatic closing balance
            "include_planned_events": True,
            "model": ev_data["selected_model"],
            "expected_data_revision": res["data_revision"]
        }
    )
    assert fc_resp.status_code == 200
    fc = fc_resp.json()
    fc_id = fc["id"]

    pa_resp = await auth_client.get(
        f"/api/v2/companies/{fresh_company_id}/plan-actual?forecast_id={fc_id}"
    )
    assert pa_resp.status_code == 200
    pa = pa_resp.json()
    assert len(pa["days"]) == 30

    # 5. Integrations listing and sync
    int_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/integrations")
    assert int_resp.status_code == 200
    integrations = int_resp.json()["items"]
    assert len(integrations) >= 4

    int_id = integrations[0]["id"]
    sync_resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/integrations/{int_id}/sync"
    )
    assert sync_resp.status_code == 200
    assert sync_resp.json()["imported_count"] > 0
