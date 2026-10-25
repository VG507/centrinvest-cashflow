import test from 'node:test';
import assert from 'node:assert/strict';
import writeExcelFile from 'write-excel-file/node';
import { readSheet } from 'read-excel-file/node';
import { forecastExcelOptions, forecastExcelRows } from './forecastExcel';
import type { ForecastDay } from '../../../contracts/types';

test('Excel export roundtrips dates, numeric amounts, zero probability and unavailable intervals', async () => {
  const days: ForecastDay[] = [
    { date: '2026-10-01', predicted_income: 1234.56, predicted_expense: 2000, predicted_balance: -765.44, balance_lower: -1000, balance_upper: 100, gap_probability: 0, planned_event_ids: [] },
    { date: '2026-10-02', predicted_income: 0, predicted_expense: 0, predicted_balance: -765.44, balance_lower: null, balance_upper: null, gap_probability: null, planned_event_ids: [] },
  ];
  const buffer = await writeExcelFile(forecastExcelRows(days), forecastExcelOptions).toBuffer();
  assert.equal(buffer.subarray(0, 2).toString(), 'PK');
  const rows = await readSheet(buffer);
  assert.equal(rows.length, 3);
  assert.equal(rows[0][0], 'Дата');
  const date: unknown = rows[1][0];
  assert.ok(date instanceof Date);
  assert.equal(date.toISOString().slice(0, 10), days[0].date);
  assert.deepEqual(rows[1].slice(1), [1234.56, 2000, -765.44, -1000, 100, 0]);
  assert.deepEqual(rows[2].slice(1), [0, 0, -765.44, null, null, null]);
});
