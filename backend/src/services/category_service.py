import re
from typing import Literal
from src.schemas.contracts import CategoryId

CATEGORIES_CONFIG = [
    {"id": "sales", "name": "Выручка от продаж", "direction": "income"},
    {"id": "other_income", "name": "Прочие поступления", "direction": "income"},
    {"id": "payroll", "name": "Заработная плата и выплаты персоналу", "direction": "expense"},
    {"id": "rent", "name": "Аренда помещений и оборудования", "direction": "expense"},
    {"id": "suppliers", "name": "Оплата поставщикам и подрядчикам", "direction": "expense"},
    {"id": "taxes", "name": "Налоги, сборы и страховые взносы", "direction": "expense"},
    {"id": "loan", "name": "Кредиты, лизинг и займы", "direction": "expense"},
    {"id": "fees", "name": "Банковские комиссии и эквайринг", "direction": "expense"},
    {"id": "equipment", "name": "Основные средства и оборудование", "direction": "expense"},
    {"id": "transfer", "name": "Переводы между своими счетами", "direction": "both"},
    {"id": "other_expense", "name": "Прочие списания", "direction": "expense"},
    {"id": "uncategorized", "name": "Не распределено", "direction": "both"},
]

# Regex patterns for fast, robust Russian rule-based matching
PATTERNS_PAYROLL = re.compile(
    r"\b(зарплат[а-я]*|заработн[а-я]*|зп|оплат[а-я]* труда|расчет при увольнении|преми[яий]|отпускн[а-я]*|больничн[а-я]*|пособи[яе]|выплат[а-я]* сотрудникам|аванс по зарплате|реестр зарплат[а-я]*)\b",
    re.IGNORECASE
)
PATTERNS_LOAN = re.compile(
    r"\b(кредит[а-я]*|лизинг[а-я]*|займ[а-я]*|заем|процент[а-я]* по кредит[а-я]*|основн[а-я]* долг[а-я]*|тело долга)\b",
    re.IGNORECASE
)
PATTERNS_RENT = re.compile(
    r"\b(аренд[а-я]*|субаренд[а-я]*|коммунал[а-я]*|эксплуатац[а-я]*|электроэнерги[яи]|водоснабжен[а-я]*|отоплен[а-я]*)\b",
    re.IGNORECASE
)
PATTERNS_EQUIPMENT = re.compile(
    r"\b(оборудован[а-я]*|основн[а-я]* средств[а-я]*|спецтехник[а-я]*|станок|автомобил[а-я]*|транспортн[а-я]* средств[а-я]*)\b",
    re.IGNORECASE
)
PATTERNS_TAXES = re.compile(
    r"\b(енп|единый налоговый платеж|единый налоговый платёж|налог[а-я]*|усн|ндфл|страхов[а-я]* взнос[а-я]*|пфр|фсс|фнс|уфк|госпошлин[а-я]*|в бюджет|уплата ндс)\b",
    re.IGNORECASE
)
PATTERNS_FEES = re.compile(
    r"\b(комисси[яи]|ведение счет[а-я]*|обслуживан[а-я]* счет[а-я]*|рко|эквайринг|инкассац[а-я]*|тариф[а-я]* банк[а-я]*|смс-информ[а-я]*)\b",
    re.IGNORECASE
)
PATTERNS_TRANSFER = re.compile(
    r"\b(перевод собственн[а-я]* средств|между своим[а-я]* счетам[а-я]*|пополнен[а-я]* счет[а-я]*|внесен[а-я]* собственн[а-я]*|перемещение средств)\b",
    re.IGNORECASE
)
PATTERNS_SUPPLIERS = re.compile(
    r"\b(поставщик[а-я]*|поставк[а-я]*|товар[а-я]*|материал[а-я]*|закупк[а-я]*|сырь[её]|продукци[яи]|запчаст[а-я]*|топлив[а-я]*|гсм|транспортн[а-я]* услуг[а-я]*|доставк[а-я]*|перевозк[а-я]*|упд|счет|счет-фактур[а-я]*|ремонт|услуг[а-я]*|аванс)\b",
    re.IGNORECASE
)
PATTERNS_SALES = re.compile(
    r"\b(выручк[а-я]*|оплат[а-я]* от покупател[а-я]*|за товар[а-я]*|покупател[а-я]*|за услуг[а-я]*|заказ[а-я]*|чек|эквайринг|поступлен[а-я]* по сч[её]ту|реализац[а-я]*)\b",
    re.IGNORECASE
)

def clean_vat_clauses(text: str) -> str:
    cleaned = re.sub(
        r"[,;\s]*\b(в\s+т\.?ч\.?|в\s+том\s+числе)\s+ндс\b[^,;\.]*([,;\.]|$)",
        " ",
        text,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(
        r"[,;\s]*\b(без\s+(налога\s+)?ндс|ндс\s+не\s+облагается)\b[^,;\.]*([,;\.]|$)",
        " ",
        cleaned,
        flags=re.IGNORECASE
    )
    return " ".join(cleaned.split()).strip()

def extract_vat(purpose: str, total_amount: float | None = None) -> tuple[float | None, float | None]:
    if not purpose:
        return None, None
    if re.search(r"\b(без\s+(налога\s+)?ндс|ндс\s+не\s+облагается)\b", purpose, re.IGNORECASE):
        return 0.0, 0.0

    rate_match = re.search(r"\bндс\s*(?:по\s*ставке\s*)?(20|10|0)%?\b", purpose, re.IGNORECASE) or \
                 re.search(r"\b(20|10|0)%\s*(?:в\s*т\.?ч\.?)?\s*ндс\b", purpose, re.IGNORECASE)
    vat_rate = float(rate_match.group(1)) / 100.0 if rate_match else None

    amt_match = re.search(r"\bндс\b[^\d]*(\d+(?:[\s\xa0]\d+)*(?:[,\.]\d{2})?)\s*(?:руб|р\b)", purpose, re.IGNORECASE)
    if amt_match:
        try:
            amt_str = amt_match.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
            vat_amount = round(float(amt_str), 2)
            if vat_rate is None and total_amount and total_amount > 0:
                if abs(vat_amount - (total_amount * 20.0 / 120.0)) < 1.0:
                    vat_rate = 0.20
                elif abs(vat_amount - (total_amount * 10.0 / 110.0)) < 1.0:
                    vat_rate = 0.10
            return vat_rate, vat_amount
        except ValueError:
            pass

    if vat_rate is not None and total_amount and total_amount > 0:
        if vat_rate == 0.20:
            vat_amount = round(total_amount * 20.0 / 120.0, 2)
        elif vat_rate == 0.10:
            vat_amount = round(total_amount * 10.0 / 110.0, 2)
        else:
            vat_amount = 0.0
        return vat_rate, vat_amount

    return vat_rate, None

class CategoryService:
    @staticmethod
    def get_categories() -> list[dict]:
        return CATEGORIES_CONFIG

    @staticmethod
    def categorize(
        direction: Literal["income", "expense"],
        purpose: str,
        counterparty_name: str = "",
        counterparty_inn: str = ""
    ) -> tuple[CategoryId, Literal["rule", "model", "manual", "unknown"], float | None]:
        text = f"{purpose} {counterparty_name}".strip()
        if not text:
            return "uncategorized", "unknown", None

        clean_inn = str(counterparty_inn or "").strip()
        # Systemic Russian tax INNs (FNS / Federal Treasury / Single Tax Account)
        if clean_inn in ("7727406020", "7707442499", "7707442470") or clean_inn.startswith("7727406020"):
            return "taxes", "rule", 0.99

        # Clean trailing standard invoice VAT notes ("В т.ч. НДС...", "Без НДС")
        clean_purpose = clean_vat_clauses(purpose)
        clean_text = f"{clean_purpose} {counterparty_name}".strip()
        c_lower = counterparty_name.lower()

        # Check transfers first (applies to both directions)
        if PATTERNS_TRANSFER.search(text):
            return "transfer", "rule", 0.95

        # If expense:
        if direction == "expense":
            # 1. Payroll: salary/wages take priority over tax mentions (e.g. "Зарплата... НДФЛ удержан")
            if PATTERNS_PAYROLL.search(text):
                return "payroll", "rule", 0.95

            # 2. Taxes: systemic markers or explicit tax keywords
            if PATTERNS_TAXES.search(clean_text) or "уфк" in c_lower or "налог" in c_lower or "ифнс" in c_lower:
                return "taxes", "rule", 0.95

            # 3. Loans and leasing
            if PATTERNS_LOAN.search(text):
                return "loan", "rule", 0.95

            # 4. Rent and utilities
            if PATTERNS_RENT.search(text):
                return "rent", "rule", 0.95

            # 5. Fixed assets and equipment
            if PATTERNS_EQUIPMENT.search(text):
                return "equipment", "rule", 0.90

            # 6. Bank fees and commissions
            if PATTERNS_FEES.search(text):
                return "fees", "rule", 0.95

            # 7. Suppliers, contractors, fuel, parts, goods
            if PATTERNS_SUPPLIERS.search(clean_text):
                return "suppliers", "rule", 0.85

            # 8. Bank counterparty fallback (only if purpose is not payroll/loan/etc.)
            if "банк" in c_lower:
                return "fees", "rule", 0.85

            # Other expense fallback
            return "other_expense", "rule", 0.60

        # If income:
        if direction == "income":
            if PATTERNS_SALES.search(text):
                return "sales", "rule", 0.90
            # Common customer payment markers
            if "упд" in text.lower() or "счет" in text.lower() or "счёт" in text.lower() or "договор" in text.lower():
                return "sales", "rule", 0.85
            return "other_income", "rule", 0.65

        return "uncategorized", "unknown", None
