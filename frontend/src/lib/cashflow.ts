import type { ForecastResult, TransactionPoint } from '../../../contracts/types';

export const rub = (value: number) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value);
export const shortRub = (value: number) => new Intl.NumberFormat('ru-RU', { notation: 'compact', maximumFractionDigits: 1 }).format(value) + ' ₽';
export const dateLabel = (date: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(`${date}T12:00:00Z`));
export const fullDate = (date: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${date}T12:00:00Z`));
const iso = (date: Date) => date.toISOString().slice(0, 10);
export function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return iso(value);
}
export function validDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && iso(new Date(`${value}T12:00:00Z`)) === value;
}

/** Parses a deliberately small daily-flow CSV format. Raw bank imports belong to v2. */
export function parseDailyCsv(input: string): TransactionPoint[] {
  const lines = input.replace(/^\uFEFF/, '').trim().split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 2) throw new Error('Добавьте заголовок и хотя бы один день операций.');
  if (lines.length > 3661) throw new Error('Для дневного формата доступно не более 3660 строк.');
  const separator = lines[0].includes(';') ? ';' : ',';
  const headers = lines[0].trim().toLowerCase().split(separator).map(s => s.trim());
  if (headers.join(',') !== 'date,income,expense') throw new Error('Нужны три столбца в порядке: date, income, expense. Полную банковскую выписку будет принимать отдельный импорт.');
  const byDate = new Map<string, TransactionPoint>();
  lines.slice(1).forEach((line, index) => {
    const cells = line.split(separator).map(s => s.trim());
    const [date, incomeText, expenseText] = cells;
    const income = Number(incomeText?.replace(',', '.'));
    const expense = Number(expenseText?.replace(',', '.'));
    if (cells.length !== 3 || !validDate(date) || !incomeText || !expenseText
      || !Number.isFinite(income) || !Number.isFinite(expense) || income < 0 || expense < 0
      || income > 1e12 || expense > 1e12) throw new Error(`Строка ${index + 2}: проверьте дату ГГГГ-ММ-ДД и неотрицательные суммы до 1 трлн ₽.`);
    if (byDate.has(date)) throw new Error(`Строка ${index + 2}: дата ${date} повторяется. Сначала объедините операции за день.`);
    byDate.set(date, { date, income, expense });
  });
  const result = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  for (let i = 1; i < result.length; i++) {
    if (addDays(result[i - 1].date, 1) !== result[i].date) throw new Error(`Между ${result[i - 1].date} и ${result[i].date} пропущены дни. Подтвердите отсутствие операций нулевыми строками или добавьте данные.`);
  }
  return result;
}

/** Input fixture only: deterministic daily cashflows, never a forecast response. */
export function exampleHistory(cutoff: string): TransactionPoint[] {
  return Array.from({ length: 90 }, (_, index) => {
    const date = addDays(cutoff, index - 89);
    const day = new Date(`${date}T12:00:00Z`).getUTCDay();
    return {
      date,
      income: Math.round(38000 - index * 130 + (day === 0 || day === 6 ? -6500 : 2500)),
      expense: Math.round(27000 + index * 70 + (index % 30 === 24 ? 80000 : 0)),
    };
  });
}
export const historyCsv = (history: TransactionPoint[]) => 'date,income,expense\n' + history.map(p => `${p.date},${p.income},${p.expense}`).join('\n');
export function historicalBalances(history: TransactionPoint[], closingBalance: number) {
  let balance = closingBalance;
  return [...history].reverse().map(point => {
    const row = { ...point, balance };
    balance -= point.income - point.expense;
    return row;
  }).reverse();
}
export function checkForecast(value: unknown, history: TransactionPoint[], closingBalance: number, horizon: number): ForecastResult {
  if (!value || typeof value !== 'object') throw new Error('Сервер вернул некорректный прогноз.');
  const r = value as Record<string, unknown>;
  const arrays = ['predicted_dates', 'predicted_income', 'predicted_expense', 'predicted_balance'] as const;
  for (const field of arrays) if (!Array.isArray(r[field]) || r[field].length !== horizon) throw new Error('Длина прогноза не совпадает с выбранным периодом.');
  const dates = r.predicted_dates as unknown[];
  const income = r.predicted_income as unknown[];
  const expense = r.predicted_expense as unknown[];
  const balances = r.predicted_balance as unknown[];
  let previous = closingBalance;
  for (let i = 0; i < horizon; i++) {
    if (dates[i] !== addDays(history[history.length - 1].date, i + 1)
      || ![income[i], expense[i], balances[i]].every(v => typeof v === 'number' && Number.isFinite(v))
      || (income[i] as number) < 0 || (expense[i] as number) < 0) throw new Error('Проверьте сервер: некорректные даты или суммы в прогнозе.');
    const expected = previous + (income[i] as number) - (expense[i] as number);
    if (Math.abs(expected - (balances[i] as number)) > 0.03) throw new Error('Остаток сервера не согласован с поступлениями и расходами.');
    previous = balances[i] as number;
  }
  const expectedGaps = dates.filter((_, i) => (balances[i] as number) < 0);
  if (!['low', 'medium', 'critical'].includes(String(r.risk_level))
    || typeof r.cashflow_gap_detected !== 'boolean'
    || r.cashflow_gap_detected !== (expectedGaps.length > 0)
    || JSON.stringify(r.gap_dates) !== JSON.stringify(expectedGaps)
    || typeof r.minimum_expected_balance !== 'number' || !Number.isFinite(r.minimum_expected_balance)
    || Math.abs(r.minimum_expected_balance - Math.min(...balances as number[])) > 0.02) throw new Error('Сводка риска не согласована с дневным прогнозом.');
  return value as ForecastResult;
}
export function downloadCsv(name: string, content: string) {
  const url = URL.createObjectURL(new Blob(['\uFEFF', content], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
