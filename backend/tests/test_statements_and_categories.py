import io
import json
import pytest
import httpx

SAMPLE_CSV = """company_id;operation_id;operation_date;amount;direction;counterparty_inn;counterparty_name;payment_purpose;balance_eod
C001;C001-000001;2024-10-01;990.00;Списание;0068275202;ПАО «Банк»;Комиссия за ведение счета за сентябрь 2024 г. Без НДС;1244821.98
C001;C001-000002;2024-10-02;170892.06;Поступление;0048401219;ООО «Элеватор-242»;Оплата по УПД № 279 от 19.08.2024. НДС не облагается;1527714.04
C001;C001-000003;2024-10-02;112000.00;Поступление;0053443398;ООО «Дистрибьютор-307»;Частичная оплата по УПД № 296 от 02.09.2024. НДС не облагается.;1527714.04
C001;C001-000004;2024-10-04;53000.00;Списание;0056213787;ООО «Система взимания платы-516»;Пополнение расчетной записи (оплата провоза по дорогам федерального значения). НДС не облагается;1474714.04
C001;C001-000005;2024-10-07;275663.75;Поступление;0075510619;ООО «Экспедитор-772»;Оплата по УПД № 272 от 19.08.2024. НДС не облагается.;1518383.14
C001;C001-000006;2024-10-07;204000.00;Списание;0062343230;ООО «Топливная компания-660»;Пополнение лицевого счета по договору № 4620 (топливные карты). В т.ч. НДС 20% - 34 000.00;1518383.14
C001;C001-000007;2024-10-07;27994.65;Списание;0013426607;ООО «Канцтовары-864»;Оплата по счету № 3294 от 02.10.2024 за канцтовары и хозтовары. В т.ч. НДС 20% - 4 665.77;1518383.14
C001;C001-000008;2024-10-08;5881.77;Списание;0052516773;ПАО «Телеком-529»;Оплата услуг связи и доступа в Интернет по лицевому счету 1006059 за октябрь 2024 г. В т.ч. НДС 20% - 981.67;1483532.71
C001;C001-000009;2024-10-08;28968.66;Списание;0045890547;ООО «Бухгалтерия-Аутсорс-842»;Оплата по счету № 3448 от 05.10.2024 за бухгалтерские услуги. в том числе НДС (20%) 4 828.11 руб.;1483532.71
C001;C001-000010;2024-10-15;350000.00;Списание;0000000000;Сотрудники;Зарплата за первую половину месяца (аванс). НДФЛ удержан;1133532.71
C001;C001-000011;2024-10-28;120000.00;Списание;0077000000;УФК по г. Москве;Единый налоговый платеж (ЕНП) за 3 квартал 2024;1013532.71
"""

@pytest.mark.asyncio
async def test_import_statement_and_categories(auth_client: httpx.AsyncClient, fresh_company_id: str):
    # 1. Import CSV
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
    resp = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "ready"
    assert res_data["accepted_rows"] >= 10
    assert res_data["duplicate_rows"] == 0

    # 2. Re-importing same file -> duplicate_rows == accepted_rows
    files2 = {"file": ("statement.csv", io.BytesIO(SAMPLE_CSV.encode("utf-8-sig")), "text/csv")}
    resp2 = await auth_client.post(
        f"/api/v2/companies/{fresh_company_id}/imports",
        data=data,
        files=files2
    )
    assert resp2.status_code == 200
    assert resp2.json()["duplicate_rows"] >= 10
    assert resp2.json()["accepted_rows"] == 0

    # 3. List transactions
    tx_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/transactions?limit=20")
    assert tx_resp.status_code == 200
    txs = tx_resp.json()["items"]
    assert len(txs) >= 10

    # Verify category categorization
    tx_map = {t["external_id"]: t for t in txs if t.get("external_id")}
    assert tx_map["C001-000001"]["category_id"] == "fees"  # комиссия банка
    assert tx_map["C001-000002"]["category_id"] == "sales"  # оплата по упд
    assert tx_map["C001-000010"]["category_id"] == "payroll"  # зарплата аванс
    assert tx_map["C001-000011"]["category_id"] == "taxes"  # ЕНП

    # 4. Manual category override
    tx_to_update = tx_map["C001-000008"]  # телеком
    patch_resp = await auth_client.patch(
        f"/api/v2/companies/{fresh_company_id}/transactions/{tx_to_update['id']}/category",
        json={"category_id": "rent"}
    )
    assert patch_resp.status_code == 200
    updated_tx = patch_resp.json()
    assert updated_tx["category_id"] == "rent"
    assert updated_tx["category_method"] == "manual"
    assert updated_tx["category_confidence"] == 1.0

    # 5. Get Daily Actuals
    act_resp = await auth_client.get(f"/api/v2/companies/{fresh_company_id}/actuals")
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert len(act_data["days"]) > 0
    assert len(act_data["category_totals"]) > 0
