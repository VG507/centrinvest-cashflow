import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { ForecastResult } from '../../../blackboard/contracts/types';
import { addDays, checkForecast, exampleHistory, historicalBalances, historyCsv, parseDailyCsv, validDate } from './cashflow';

test('CSV supports BOM, decimal comma, sorted dates, and rejects ambiguous/missing days', () => {
  assert.deepEqual(parseDailyCsv('\uFEFFdate;income;expense\n2026-02-28;20,50;10\n2026-02-27;0;15'), [
    { date: '2026-02-27', income: 0, expense: 15 }, { date: '2026-02-28', income: 20.5, expense: 10 },
  ]);
  for (const csv of [
    'date,income,expense\n2026-02-30,1,0', 'date,income,expense\n2026-01-01,-1,0',
    'date,income,expense\n2026-01-01,Infinity,0', 'date,income,expense\n2026-01-01,,0',
    'date,income,expense\n2026-01-01,1,0\n2026-01-01,2,0',
    'date,income,expense\n2026-01-01,1,0\n2026-01-03,2,0',
    'date,amount,direction\n2026-01-01,1,income',
  ]) assert.throws(() => parseDailyCsv(csv));
});
test('calendar arithmetic handles leap day and year rollover in UTC', () => {
  assert.equal(addDays('2024-02-28', 1), '2024-02-29');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(validDate('2026-02-29'), false);
  assert.equal(validDate('2024-02-29'), true);
});
test('historical balances use closing EOD balance and reverse net flows once', () => {
  const points = [{ date: '2026-10-22', income: 50, expense: 10 }, { date: '2026-10-23', income: 10, expense: 30 }];
  assert.deepEqual(historicalBalances(points, 100).map(p => p.balance), [120, 100]);
  assert.equal(points[0].date, '2026-10-22');
});
test('example is input only and roundtrips through the same CSV validator', () => {
  const history = exampleHistory('2026-10-23');
  assert.equal(history.length, 90); assert.equal(history.at(-1)?.date, '2026-10-23');
  assert.deepEqual(parseDailyCsv(historyCsv(history)), history);
});
test('forecast rejects invalid dates, inconsistent balances, gap summary and non-finite values', () => {
  const history = [{ date: '2026-10-23', income: 10, expense: 15 }];
  const dates = Array.from({ length: 30 }, (_, i) => addDays('2026-10-23', i + 1));
  const balances = dates.map((_, i) => 100 - 10 * (i + 1));
  const response: ForecastResult = {
    predicted_dates: dates, predicted_income: dates.map(() => 10), predicted_expense: dates.map(() => 20),
    predicted_balance: balances, cashflow_gap_detected: true, gap_dates: dates.filter((_, i) => balances[i] < 0),
    minimum_expected_balance: -200, risk_level: 'critical',
  };
  assert.equal(checkForecast(response, history, 100, 30), response);
  for (const changed of [
    { ...response, predicted_dates: dates.slice(1) }, { ...response, predicted_balance: balances.map(() => 0) },
    { ...response, cashflow_gap_detected: false }, { ...response, gap_dates: [] },
    { ...response, minimum_expected_balance: -100 }, { ...response, predicted_income: dates.map(() => Number.NaN) },
  ]) assert.throws(() => checkForecast(changed, history, 100, 30));
});
