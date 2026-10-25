import asyncio
import re
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.entities import ForecastSnapshotRecord
from src.schemas.contracts import AdviceResponse, RecommendationItem
from src.core.llm import llm_client
from src.config import settings

class AdvisoryService:
    @staticmethod
    async def get_advice(
        db: AsyncSession,
        company_id: str,
        forecast_id: str,
        business_type: str = "Малый бизнес"
    ) -> AdviceResponse:
        # Sanitize business_type against XSS, HTML injection, prompt injection and control directives
        clean_btype = re.sub(r"[^\w\s-]", "", business_type).strip()
        clean_btype = re.sub(r"(?i)(system\s+directive|ignore\s+all|you\s+are\s+an\s+adversary|prompt\s+injection).*", "", clean_btype).strip()[:100]
        if not clean_btype:
            clean_btype = "Малый бизнес"
        snap_res = await db.execute(
            select(ForecastSnapshotRecord).where(
                ForecastSnapshotRecord.company_id == company_id,
                ForecastSnapshotRecord.id == forecast_id
            )
        )
        snap = snap_res.scalar_one_or_none()
        if not snap:
            raise KeyError(f"Forecast {forecast_id} not found")

        summary = snap.summary
        min_bal = float(summary.get("minimum_balance", 0.0))
        max_shortage = float(summary.get("maximum_shortage", 0.0))
        risk_level = summary.get("risk_level", "low")
        first_gap = summary.get("first_gap_date")
        gaps = snap.gaps or []

        contributing_event_ids = []
        for g in gaps:
            contributing_event_ids.extend(g.get("contributing_event_ids", []))

        # 1. Deterministic Rule Recommendations
        rules_analysis = ""
        recs: list[RecommendationItem] = []

        if risk_level == "critical" or max_shortage > 0:
            rules_analysis = (
                f"По результатам стресс-моделирования движения денежных средств для компании сферы «{clean_btype}» "
                f"выявлен критический риск кассового разрыва с {first_gap}. "
                f"Максимальный ожидаемый дефицит ликвидности составляет {max_shortage:,.2f} руб. "
                f"Требуется оперативная корректировка графика платежей."
            )
            recs.append(RecommendationItem(
                title="Отсрочка платежей крупным поставщикам",
                rationale=f"Согласование переноса оплаты кредиторской задолженности на 7-14 дней позволит ликвидировать дефицит {max_shortage:,.2f} руб.",
                related_event_ids=contributing_event_ids[:2],
                priority="high"
            ))
            recs.append(RecommendationItem(
                title="Ускорение инкассации дебиторской задолженности",
                rationale="Предоставление покупателям скидки 2-3% за досрочную оплату счетов обеспечит приток выручки до наступления даты кассового разрыва.",
                related_event_ids=[],
                priority="high"
            ))
            recs.append(RecommendationItem(
                title="Опция кредитования / овердрафта Банка «Центр-инвест»",
                rationale=f"Подача заявки на кредитный лимит овердрафта на сумму {max_shortage * 1.25:,.0f} руб. позволит обеспечить резервную подушку ликвидности для бесперебойных расчетов.",
                related_event_ids=[],
                priority="normal"
            ))
        elif risk_level == "medium":
            rules_analysis = (
                f"Финансовое состояние компании стабильно, однако минимальный остаток снижается до {min_bal:,.2f} руб. "
                f"(ниже безопасного резерва 20%). Рекомендуется усилить контроль кассовой дисциплины."
            )
            recs.append(RecommendationItem(
                title="Формирование неснижаемого резерва ликвидности",
                rationale="Резервирование части выручки на отдельном счете снизит чувствительность бизнеса к задержкам оплат покупателей.",
                related_event_ids=[],
                priority="normal"
            ))
            recs.append(RecommendationItem(
                title="Синхронизация сроков налоговых платежей (ЕНП)",
                rationale="Подготовка к списанию ЕНП 28-го числа заранее путем сглаживания графика закупок.",
                related_event_ids=[],
                priority="normal"
            ))
        else:
            rules_analysis = (
                f"Денежные потоки компании «{clean_btype}» полностью сбалансированы. Рисков дефицита ликвидности на горизонте "
                f"{snap.horizon_days} дней не зафиксировано. Прогнозируется рост остатка на счете."
            )
            recs.append(RecommendationItem(
                title="Размещение свободной ликвидности в овернайт-депозиты",
                rationale="Размещение временно свободных денежных средств в банке Центр-инвест обеспечит дополнительный процентный доход без потери ликвидности.",
                related_event_ids=[],
                priority="normal"
            ))
            recs.append(RecommendationItem(
                title="Планирование инвестиций в оборотный капитал",
                rationale="Стабильный положительный денежный поток позволяет масштабировать закупки со скидками за объем.",
                related_event_ids=[],
                priority="normal"
            ))

        # Try LLM synthesis with strict timeout
        mode = "rules"
        analysis = rules_analysis

        if settings.GEMINI_API_KEYS and settings.api_keys_list:
            prompt = (
                f"Ты старший финансовый советник банка Центр-инвест. Проанализируй агрегированные данные прогноза компании ({clean_btype}):\n"
                f"- Горизонт: {snap.horizon_days} дней\n"
                f"- Уровень риска: {risk_level}\n"
                f"- Минимальный баланс: {min_bal:,.2f} руб.\n"
                f"- Максимальный дефицит (кассовый разрыв): {max_shortage:,.2f} руб.\n"
                f"- Первая дата разрыва: {first_gap}\n\n"
                f"Сформулируй краткое (3-4 предложения) экспертное резюме на чистом профессиональном русском языке для собственника бизнеса. "
                f"Не придумывай фиктивных цифр, опирайся только на указанные факты. Без лишней воды."
            )
            try:
                # Run synchronous llm_client.generate in executor with 5s timeout
                loop = asyncio.get_running_loop()
                llm_text = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: llm_client.generate(prompt)),
                    timeout=5.0
                )
                if llm_text and len(llm_text.strip()) > 30:
                    analysis = llm_text.strip()
                    mode = "llm"
            except Exception:
                # Seamless fallback to rules mode
                mode = "rules"
                analysis = rules_analysis

        return AdviceResponse(
            forecast_id=forecast_id,
            mode=mode,
            analysis=analysis,
            recommendations=recs,
            generated_at=datetime.now(timezone.utc).isoformat()
        )
