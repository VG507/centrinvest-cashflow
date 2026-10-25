import type { SheetData } from 'write-excel-file/browser';
import type { ForecastDay, ForecastSnapshot } from '../../../blackboard/contracts/types';

export const forecastExcelOptions = {
  sheet: 'Прогноз',
  stickyRowsCount: 1,
  columns: [15, 22, 22, 22, 25, 25, 25].map(width => ({ width })),
};

export function forecastExcelRows(days: ForecastDay[]): SheetData {
  const money = (value: number | null) => value === null ? null : { value, type: Number, format: '#,##0.00' };
  return [
    ['Дата', 'Поступления, ₽', 'Расходы, ₽', 'Остаток, ₽', '80% интервал: от, ₽', '80% интервал: до, ₽', 'Вероятность нехватки'].map(value => ({
      value, type: String, fontWeight: 'bold', backgroundColor: '#EAF3EC', textColor: '#173B2B',
    })),
    ...days.map(day => [
      { value: new Date(`${day.date}T00:00:00Z`), type: Date, format: 'dd.mm.yyyy' },
      money(day.predicted_income), money(day.predicted_expense), money(day.predicted_balance),
      money(day.balance_lower), money(day.balance_upper),
      day.gap_probability === null ? null : { value: day.gap_probability, type: Number, format: '0.0%' },
    ]),
  ];
}

export async function downloadForecastExcel(snapshot: ForecastSnapshot): Promise<void> {
  const { default: writeExcelFile } = await import('write-excel-file/browser');
  await writeExcelFile(forecastExcelRows(snapshot.days), forecastExcelOptions).toFile(`forecast-${snapshot.id}.xlsx`);
}
