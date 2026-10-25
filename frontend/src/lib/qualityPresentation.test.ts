import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import type {EvaluationResponse} from '../../../contracts/types';
import {QualityResults} from '../v2/Quality';
const result:EvaluationResponse={id:'evaluation-test',company_id:'company-test',created_at:'2026-10-24T12:00:00Z',data_revision:3,split_method:'rolling_origin',test_days:30,folds:[{train_end:'2026-06-01',test_start:'2026-06-02',test_end:'2026-07-01'}],metrics:[{model:'ridge_calendar',mae_balance:0,mae_income:0,mae_expense:0,wape_cashflow:null,interval_empirical_coverage:null,gap_precision:null,gap_recall:null,average_warning_lead_days:null,gap_brier_score:null,evaluated_days:0}],selected_model:'ridge_calendar',selection_reason:'Причина выбора от сервера',limitations:[]};
const plain=(html:string)=>html.replace(/<[^>]*>/g,'').replace(/\u00a0/g,' ');
test('quality result preserves zero errors, unknown WAPE and source revision warning',()=>{
 const html=renderToStaticMarkup(createElement(QualityResults,{result,revision:4})),text=plain(html);
 assert.match(text,/0 ₽/);assert.match(text,/Нет оценки/);assert.doesNotMatch(text,/0\s?%/);
 assert.match(text,/Причина выбора от сервера/);assert.match(text,/текущая версия — 4/);assert.match(text,/Ridge с календарем/);
});
test('quality timeline exposes exact server dates without implying a training start',()=>{
 const text=plain(renderToStaticMarkup(createElement(QualityResults,{result,revision:3})));
 assert.match(text,/Обучение до 1 июня 2026 г\./);assert.match(text,/2 июня 2026 г\. — 1 июля 2026 г\./);
 assert.doesNotMatch(text,/Данные изменились/);assert.doesNotMatch(text,/Начало обучения/);
});
