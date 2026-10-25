from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import Company, IntegrationRecord, TransactionRecord
from src.schemas.contracts import (
    Integration, IntegrationListResponse, IntegrationSyncResponse
)

DEFAULT_INTEGRATIONS = [
    {
        "id": "int_accounting_1c",
        "kind": "accounting",
        "name": "1C:Бухгалтерия 8.3 / МойСклад",
        "status": "not_configured",
        "supported_entities": ["transactions", "invoices", "contracts", "taxes", "payroll"]
    },
    {
        "id": "int_bank_centrinvest",
        "kind": "bank",
        "name": "Банк Центр-инвест (DirectBank)",
        "status": "not_configured",
        "supported_entities": ["transactions", "loans", "payment_orders"]
    },
    {
        "id": "int_cash_register",
        "kind": "cash_register",
        "name": "ОФД / Онлайн-кассы (Атол, Эвотор)",
        "status": "not_configured",
        "supported_entities": ["transactions"]
    },
    {
        "id": "int_marketplace",
        "kind": "marketplace",
        "name": "Маркетплейсы (Wildberries / Ozon)",
        "status": "not_configured",
        "supported_entities": ["transactions", "invoices"]
    },
    {
        "id": "int_registry_fns",
        "kind": "registry",
        "name": "ФНС / ЕГРЮЛ Реестр рисков контрагентов",
        "status": "not_configured",
        "supported_entities": ["counterparty_status"]
    }
]

class IntegrationService:
    @staticmethod
    async def get_integrations(db: AsyncSession, company_id: str) -> IntegrationListResponse:
        res = await db.execute(
            select(IntegrationRecord).where(IntegrationRecord.company_id == company_id)
        )
        records = res.scalars().all()
        if not records:
            # Seed default integrations for company
            for item in DEFAULT_INTEGRATIONS:
                rec = IntegrationRecord(
                    id=f"{item['id']}_{company_id[:8]}",
                    company_id=company_id,
                    kind=item["kind"],
                    name=item["name"],
                    status=item["status"],
                    supported_entities=item["supported_entities"]
                )
                db.add(rec)
            await db.commit()
            res = await db.execute(
                select(IntegrationRecord).where(IntegrationRecord.company_id == company_id)
            )
            records = res.scalars().all()

        items = []
        for r in records:
            items.append(Integration(
                id=r.id,
                kind=r.kind,
                name=r.name,
                status=r.status,
                last_sync_at=r.last_sync_at.isoformat() if r.last_sync_at else None,
                last_error=r.last_error,
                supported_entities=r.supported_entities or []
            ))
        return IntegrationListResponse(items=items)

    @staticmethod
    async def sync_integration(
        db: AsyncSession,
        company_id: str,
        integration_id: str
    ) -> IntegrationSyncResponse:
        res = await db.execute(
            select(IntegrationRecord).where(
                IntegrationRecord.company_id == company_id,
                IntegrationRecord.id == integration_id
            )
        )
        rec = res.scalar_one_or_none()
        if not rec:
            raise KeyError(f"Integration {integration_id} not found")

        comp_res = await db.execute(select(Company).where(Company.id == company_id))
        comp = comp_res.scalar_one()

        now = datetime.now(timezone.utc)
        rec.last_sync_at = now

        # Invariant: unconfigured connector cannot claim provider sync or become connected without real credentials
        if rec.status != "connected":
            rec.status = "not_configured"
        rec.last_error = None

        # Registry integrations inspect counterparty risk, not monetary transactions
        if rec.kind == "registry":
            await db.commit()
            return IntegrationSyncResponse(
                integration_id=integration_id,
                imported_count=0,
                data_revision=comp.data_revision,
                synced_at=now.isoformat()
            )

        # For accounting and bank sources: deterministic sandbox transactions
        # External IDs are stable per company and batch index to guarantee strict idempotency
        now_date = now.date()
        sync_batch = [
            {
                "ext_id": f"SANDBOX-{rec.kind.upper()}-{company_id[:8]}-001",
                "date": now_date,
                "amount": 84500.0,
                "direction": "income",
                "counterparty_name": "ООО «Оптовик-Трейд»",
                "counterparty_inn": "6164001234",
                "purpose": f"Оплата по договору поставки через интеграцию {rec.name}. В т.ч. НДС 20%",
                "category_id": "sales",
            },
            {
                "ext_id": f"SANDBOX-{rec.kind.upper()}-{company_id[:8]}-002",
                "date": now_date,
                "amount": 32100.0,
                "direction": "expense",
                "counterparty_name": "ООО «ТрансЛогистик»",
                "counterparty_inn": "6164005678",
                "purpose": f"Оплата транспортных услуг через {rec.name}. В т.ч. НДС 20%",
                "category_id": "suppliers",
            },
            {
                "ext_id": f"SANDBOX-{rec.kind.upper()}-{company_id[:8]}-003",
                "date": now_date,
                "amount": 4900.0,
                "direction": "expense",
                "counterparty_name": "ПАО «Центр-инвест»",
                "counterparty_inn": "6163011391",
                "purpose": "Комиссия за расчетно-кассовое обслуживание DirectBank",
                "category_id": "fees",
            }
        ]

        existing_res = await db.execute(
            select(TransactionRecord.external_id).where(
                TransactionRecord.company_id == company_id,
                TransactionRecord.external_id.in_([item["ext_id"] for item in sync_batch])
            )
        )
        existing_ids = set(existing_res.scalars().all())

        imported_count = 0
        running_bal = float(comp.closing_balance) if comp.closing_balance is not None else 1000000.0
        for item in sync_batch:
            if item["ext_id"] not in existing_ids:
                if item["direction"] == "income":
                    running_bal += item["amount"]
                else:
                    running_bal -= item["amount"]
                tx = TransactionRecord(
                    company_id=company_id,
                    import_id=None,
                    date=item["date"],
                    amount=item["amount"],
                    direction=item["direction"],
                    counterparty_name=item["counterparty_name"],
                    counterparty_inn=item["counterparty_inn"],
                    purpose=f"[SANDBOX] {item['purpose']}",
                    closing_balance=round(running_bal, 2),
                    external_id=item["ext_id"],
                    category_id=item["category_id"],
                    category_method="rule",
                    category_confidence=0.95,
                    source_kind="sandbox",
                    source_id=integration_id,
                    source_label=f"Sandbox: {rec.name}"
                )
                db.add(tx)
                imported_count += 1

        # Preserve real data revision and confirmed closing balance; sandbox funds do not alter real production revision
        await db.commit()

        return IntegrationSyncResponse(
            integration_id=integration_id,
            imported_count=imported_count,
            data_revision=comp.data_revision,
            synced_at=now.isoformat()
        )
