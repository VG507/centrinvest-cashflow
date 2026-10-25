import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { ForecastSummary } from '../../../contracts/types';
import { ScenarioSummary } from '../v2/ScenarioSummary';

const summary:ForecastSummary={closing_balance:1000,end_balance:1200,total_income:500,total_expense:300,minimum_balance:800,minimum_balance_date:'2026-10-25',first_gap_date:null,maximum_shortage:0,any_gap_probability:.1,risk_level:'low'};
const text=(html:string)=>html.replace(/<[^>]*>/g,'').replace(/\u00a0/g,' ');
test('scenario summary shows no estimate for unavailable probability, preserving zero balances',()=>{
  const html=text(renderToStaticMarkup(createElement(ScenarioSummary,{base:{summary:{...summary,any_gap_probability:null}},result:{forecast:{summary:{...summary,end_balance:0,minimum_balance:0,any_gap_probability:null}},delta:{end_balance:-1200}},pending:false})));
  assert.match(html,/Нет оценки/);assert.match(html,/Разница не оценена/);assert.match(html,/0 ₽/);assert.doesNotMatch(html,/0\s?%/);
});
test('probability changes are percentage points and adverse changes are highlighted',()=>{
  const html=renderToStaticMarkup(createElement(ScenarioSummary,{base:{summary},result:{forecast:{summary:{...summary,end_balance:900,minimum_balance:400,any_gap_probability:.35}},delta:{end_balance:-300}},pending:false}));
  assert.match(text(html),/\+25 п\.п\./);assert.equal((html.match(/class="worse"/g)??[]).length,3);
});
test('pending comparison does not fabricate scenario values or deltas',()=>{
  const html=text(renderToStaticMarkup(createElement(ScenarioSummary,{base:{summary},result:null,pending:true})));
  assert.equal((html.match(/Расчёт…/g)??[]).length,3);assert.doesNotMatch(html,/Изменение|п\.п\./);
});
