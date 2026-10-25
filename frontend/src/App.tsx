import { Select } from './v2/Select';
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownLeft, ArrowDownToLine, ArrowRight, ArrowUpRight, CalendarDays, ChartNoAxesCombined, Check, CircleHelp, FileSpreadsheet, Landmark, LoaderCircle, Plus, RefreshCw, ShieldCheck, Sparkles, TriangleAlert, Upload, Wallet, X } from 'lucide-react';
import type { AdvisorResponse, ForecastResult, TransactionPoint } from '../../contracts/types';
import * as api from './lib/api';
import { addDays, dateLabel, downloadCsv, exampleHistory, fullDate, historicalBalances, historyCsv, parseDailyCsv, rub } from './lib/cashflow';

const BalanceChart = lazy(() => import('./components/BalanceChart'));

const riskLabels = { low: 'Низкий риск', medium: 'Нужен резерв', critical: 'Возможен кассовый разрыв' };
const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Moscow' }).format(new Date());

export default function App() {
  const [history, setHistory] = useState<TransactionPoint[]>([]);
  const [source, setSource] = useState<'example' | 'file' | null>(null);
  const [sourceName, setSourceName] = useState('');
  const [closing, setClosing] = useState('350000');
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [analysis, setAnalysis] = useState<AdvisorResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [advicePending, setAdvicePending] = useState(false);
  const [error, setError] = useState('');
  const [importError, setImportError] = useState('');
  const [adviceError, setAdviceError] = useState('');
  const [businessType, setBusinessType] = useState('Розничная торговля');
  const [guide, setGuide] = useState(false);
  const [table, setTable] = useState(false);
  const upload = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const advisorRequest = useRef<AbortController | null>(null);
  const importVersion = useRef(0);
  const help = useRef<HTMLDialogElement>(null);
  useEffect(() => () => { request.current?.abort(); advisorRequest.current?.abort(); }, []);
  useEffect(() => { if (guide) help.current?.showModal(); else help.current?.close(); }, [guide]);

  function invalidate() {
    request.current?.abort(); advisorRequest.current?.abort();
    setResult(null); setAnalysis(null); setError(''); setAdviceError(''); setPending(false); setAdvicePending(false);
  }
  function loadExample() {
    importVersion.current++;
    invalidate(); setHistory(exampleHistory(today())); setSource('example'); setSourceName('Учебная розничная компания'); setImportError('');
  }
  async function importFile(file: File) {
    const version = ++importVersion.current;
    setImportError('');
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error('Файл должен быть не больше 2 МБ.');
      const rows = parseDailyCsv(await file.text());
      if (version !== importVersion.current) return;
      invalidate(); setHistory(rows); setSource('file'); setSourceName(file.name);
    } catch (e) {
      if (version === importVersion.current) setImportError(e instanceof Error ? e.message : 'Не удалось прочитать файл.');
    }
  }
  async function calculate() {
    const balance = Number(closing);
    if (!history.length || !closing.trim() || !Number.isFinite(balance) || Math.abs(balance) > 1e12) {
      setError('Загрузите дневную историю и укажите остаток в пределах 1 трлн ₽.'); return;
    }
    request.current?.abort(); advisorRequest.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setPending(true); setError(''); setResult(null); setAnalysis(null); setAdviceError(''); setAdvicePending(false);
    try {
      const next = await api.forecast({ initial_balance: balance, horizon_days: horizon, history }, controller.signal);
      if (!controller.signal.aborted) setResult(next);
    } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Не удалось построить прогноз.'); }
    finally { if (request.current === controller) setPending(false); }
  }
  async function getAdvice() {
    if (!result) return;
    advisorRequest.current?.abort();
    const controller = new AbortController(); advisorRequest.current = controller;
    setAdvicePending(true); setAdviceError('');
    try {
      const next = await api.advice({ forecast: result, business_type: businessType }, controller.signal);
      if (!controller.signal.aborted) setAnalysis(next);
    } catch (e) { if (!controller.signal.aborted) setAdviceError(e instanceof Error ? e.message : 'Не удалось получить рекомендации.'); }
    finally { if (advisorRequest.current === controller) setAdvicePending(false); }
  }
  const closingNumber = Number(closing);
  const cutoff = history.at(-1)?.date;
  const actual = useMemo(() => historicalBalances(history, Number(closing)), [history, closing]);
  const chart = useMemo(() => {
    if (!result || !cutoff) return [];
    const last = actual.slice(-14).map(p => ({ date: p.date, actual: p.balance, forecast: p.date === cutoff ? p.balance : null }));
    return [...last, ...result.predicted_dates.map((date, i) => ({ date, actual: null, forecast: result.predicted_balance[i] }))];
  }, [actual, result, cutoff]);
  const totalIncome = result?.predicted_income.reduce((a, b) => a + b, 0);
  const totalExpense = result?.predicted_expense.reduce((a, b) => a + b, 0);
  const minIndex = result ? result.predicted_balance.indexOf(result.minimum_expected_balance) : -1;
  const firstGap = result?.gap_dates[0];
  const gapIntervals = useMemo(() => {
    const ranges: { from: string; to: string }[] = [];
    for (const date of result?.gap_dates ?? []) {
      const previous = ranges.at(-1);
      if (previous && addDays(previous.to, 1) === date) previous.to = date;
      else ranges.push({ from: date, to: date });
    }
    return ranges;
  }, [result]);
  function exportForecast() {
    if (!result) return;
    downloadCsv('cashflow-forecast.csv', 'date,income,expense,balance\n' + result.predicted_dates.map((d, i) => `${d},${result.predicted_income[i]},${result.predicted_expense[i]},${result.predicted_balance[i]}`).join('\n'));
  }

  return <div className="workspace">
    <a className="skip-link" href="#main">Перейти к содержимому</a>
    <aside className="sidebar">
      <a className="brand" href="#overview" aria-label="УЧЁТ, обзор"><img src="/brand/uchet.svg" width="256" height="67" alt="УЧЁТ — Центр-инвест" /></a>
      <div className="workspace-label"><Landmark size={17} /><span>Малый бизнес<small>Прогноз денежных средств</small></span></div>
      <nav aria-label="Разделы"><a href="#overview"><ChartNoAxesCombined size={19} />Обзор финансов</a><a href="#data"><FileSpreadsheet size={19} />Дневная история</a><a href="#advice"><Sparkles size={19} />Рекомендации</a></nav>
      <div className="sidebar-bottom"><div className="privacy-note"><ShieldCheck size={20} /><p>История остается в этой сессии браузера. Расчет выполняет подключенный сервер.</p></div><button onClick={() => setGuide(true)} className="help-button"><CircleHelp size={18} />Как читать прогноз</button></div>
    </aside>

    <main id="main" className="main">
      <header className="topbar"><span><span className="tiny-logo">п</span>Рабочее пространство</span><span className="version-tag">Дневной прогноз</span></header>
      <section id="overview" className="overview">
        <div className="page-heading"><div><p className="subtitle">Планируйте платежи заранее</p><h1>Обзор финансов</h1><p className="page-description">Посмотрите, хватит ли денег на ближайшие обязательства.</p></div><button className="button button-primary" onClick={() => { document.getElementById('data')?.scrollIntoView({ behavior: 'smooth' }); upload.current?.click(); }}><Plus size={18} />Загрузить историю</button></div>
        <div className="context-strip"><div><CalendarDays size={17} /><span>{cutoff ? <>Данные по <strong>{fullDate(cutoff)}</strong></> : 'Сначала добавьте историю операций'}</span></div>{source && <span className={`source-pill ${source === 'example' ? 'sample' : ''}`}><span className="status-dot" />{source === 'example' ? 'Учебные данные' : 'Ваш CSV'}</span>}</div>

        <div className="metrics">
          <article className="metric"><div className="metric-label"><Wallet size={18} />Остаток на конец истории</div><strong>{history.length && Number.isFinite(closingNumber) ? rub(closingNumber) : 'Нет данных'}</strong><p>{cutoff ? `На ${dateLabel(cutoff)}, указан вручную` : 'Из выписки или учета компании'}</p></article>
          <article className="metric"><div className="metric-label"><ArrowUpRight size={18} />Ожидаемые поступления</div><strong>{totalIncome !== undefined ? rub(totalIncome) : 'Нет прогноза'}</strong><p>{result ? `За следующие ${horizon} дней` : 'Появятся после расчета'}</p></article>
          <article className="metric"><div className="metric-label"><ArrowDownLeft size={18} />Ожидаемые расходы</div><strong>{totalExpense !== undefined ? rub(totalExpense) : 'Нет прогноза'}</strong><p>{result ? `За следующие ${horizon} дней` : 'Появятся после расчета'}</p></article>
        </div>

        <section className="forecast-panel" aria-labelledby="forecast-heading" aria-busy={pending}>
          <div className="panel-heading"><div><h2 id="forecast-heading">Как изменится остаток</h2><p>{result ? `${dateLabel(result.predicted_dates[0])} — ${fullDate(result.predicted_dates.at(-1)!)}` : 'История и прогноз на одном графике'}</p></div><div className="period-control" role="group" aria-label="Горизонт прогноза">{([30, 60, 90] as const).map(days => <button key={days} aria-pressed={horizon === days} onClick={() => { invalidate(); setHorizon(days); }}>{days} дней</button>)}</div></div>
          <div className="chart-and-risk"><div className="chart-column">
            {result ? <><div className="chart-legend"><span><i className="legend-line actual" />Фактический остаток</span><span><i className="legend-line predicted" />Прогноз</span></div><div className="chart" role="img" aria-label={`Прогноз остатка на ${horizon} дней. Минимум ${rub(result.minimum_expected_balance)}. ${firstGap ? `Кассовый разрыв с ${fullDate(firstGap)}.` : 'Отрицательных остатков не обнаружено.'}`}>
              <Suspense fallback={<div className="chart-loading" role="status"><LoaderCircle className="spin" size={23} />Загружаем график</div>}><BalanceChart data={chart} cutoff={cutoff!} gaps={gapIntervals} /></Suspense>
            </div><div className="chart-footnote"><span>Нулевая линия — граница нехватки денег</span><button className="text-button" onClick={() => { setTable(v => !v); if (!table) setTimeout(() => document.getElementById('forecast-table')?.scrollIntoView({ block: 'nearest' }), 0); }} aria-expanded={table} aria-controls="forecast-table">{table ? 'Скрыть таблицу' : 'Посмотреть по дням'}</button></div></>
              : <div className="chart-empty"><span className="empty-icon">{pending ? <LoaderCircle className="spin" size={28} /> : <ChartNoAxesCombined size={28} />}</span><h3>{pending ? 'Рассчитываем движение денег' : 'У вашего бизнеса есть горизонт'}</h3><p>{pending ? 'Строим прогноз на основе загруженной истории.' : 'Добавьте дневную историю, укажите остаток и узнайте, что будет с деньгами в ближайший месяц.'}</p>{!pending && !history.length && <button className="button button-secondary" onClick={loadExample}>Открыть учебный пример<ArrowRight size={17} /></button>}{!pending && !!history.length && <button className="button button-primary" onClick={calculate}>Построить прогноз<ArrowRight size={17} /></button>}</div>}
          </div>
          <aside className={`risk-panel ${result?.risk_level ?? 'empty'}`} aria-label="Предупреждения о рисках">
            <div className="risk-top">{result?.cashflow_gap_detected ? <TriangleAlert size={22} /> : <ShieldCheck size={22} />}<span>{result ? riskLabels[result.risk_level] : 'Заранее знать — проще'}</span></div>
            {result ? <><h3>{firstGap ? `Деньги могут закончиться ${dateLabel(firstGap)}` : result.risk_level === 'medium' ? 'Остаток приближается к резерву' : 'Отрицательных остатков нет'}</h3><p>{firstGap ? 'Проверьте ближайшие расходы и сроки поступлений. Нехватка рассчитана по прогнозу остатка.' : 'Прогноз основан на прошлых поступлениях и расходах. Будущие обязательства в этом режиме не учитываются.'}</p><div className="risk-amount"><span>{firstGap ? 'Максимальная нехватка' : 'Минимальный остаток'}</span><strong>{rub(firstGap ? Math.max(0, -result.minimum_expected_balance) : result.minimum_expected_balance)}</strong><small>{minIndex >= 0 && dateLabel(result.predicted_dates[minIndex])}</small></div><p className="probability-note">Вероятность разрыва не рассчитана текущей моделью.</p></> : <><h3>Не откладывайте кассовый разрыв до последнего дня</h3><p>После расчета здесь появятся дата возможной нехватки и сумма, которую стоит предусмотреть.</p><div className="risk-divider" /><p className="risk-small">Прогноз помогает планировать. Его стоит обновлять по мере новых операций.</p></>}
          </aside></div>
          {table && result && <div id="forecast-table" className="table-scroll"><table><caption>Прогноз по дням, суммы в рублях</caption><thead><tr><th scope="col">Дата</th><th scope="col">Поступления</th><th scope="col">Расходы</th><th scope="col">Остаток</th></tr></thead><tbody>{result.predicted_dates.map((d, i) => <tr key={d}><th scope="row">{fullDate(d)}</th><td>{rub(result.predicted_income[i])}</td><td>{rub(result.predicted_expense[i])}</td><td className={result.predicted_balance[i] < 0 ? 'negative' : ''}>{rub(result.predicted_balance[i])}{result.predicted_balance[i] < 0 && <span className="sr-only"> — нехватка средств</span>}</td></tr>)}</tbody></table></div>}
        </section>

        <div className="forecast-actions"><p><ShieldCheck size={16} />{source === 'example' ? 'Учебный пример. Это синтетическая история, не данные компании.' : 'Расчет по дневным суммам. Категоризация и плановые платежи требуют API v2.'}</p><button className="button button-plain" disabled={!result} onClick={exportForecast}><ArrowDownToLine size={17} />Скачать прогноз</button></div>
      </section>

      <div className="bottom-grid">
        <section id="data" className="panel data-panel" aria-labelledby="data-heading"><div className="panel-heading"><div><h2 id="data-heading">Данные для прогноза</h2><p>Суммы поступлений и расходов за каждый день</p></div><FileSpreadsheet className="muted-icon" size={22} /></div>
          <div className="upload-area"><div><Upload size={22} /><div><strong>{sourceName || 'Загрузите дневную историю'}</strong><p>{history.length ? `${history.length} дней: ${dateLabel(history[0].date)} — ${fullDate(cutoff!)}` : 'CSV до 2 МБ: date, income, expense'}</p></div></div><button className="button button-secondary" onClick={() => upload.current?.click()}>Выбрать CSV</button><input className="sr-only" ref={upload} type="file" accept=".csv,text/csv" aria-label="Загрузить дневную историю CSV" onChange={e => { const file = e.target.files?.[0]; if (file) void importFile(file); e.target.value = ''; }} /></div>
          {importError && <p className="error-message" role="alert"><TriangleAlert size={18} />{importError}</p>}
          <div className="data-tools"><button className="text-button" onClick={loadExample}>Использовать учебный пример</button><button className="text-button" onClick={() => downloadCsv('daily-cashflow-example.csv', historyCsv(exampleHistory(today())))}>Скачать пример CSV<ArrowDownToLine size={14} /></button></div>
          <form onSubmit={e => { e.preventDefault(); void calculate(); }}><label htmlFor="closing-balance">Остаток на конец {cutoff ? dateLabel(cutoff) : 'последнего дня истории'}</label><div className="balance-input"><input id="closing-balance" type="number" step="0.01" min="-1000000000000" max="1000000000000" required value={closing} onChange={e => { invalidate(); setClosing(e.target.value); }} aria-describedby="balance-hint" /><span>₽</span></div><p id="balance-hint" className="field-hint">Прогноз начнется со следующего дня. Укажите фактическую сумму на счете.</p><button type="submit" className="button button-primary calculate-button" disabled={!history.length || pending}>{pending ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />}{pending ? 'Рассчитываем…' : 'Построить прогноз'}<span>{horizon} дней</span></button></form>
          {error && <p className="error-message" role="alert"><TriangleAlert size={18} />{error}</p>}
          {result && <p className="success-message" role="status"><Check size={16} />Прогноз получен от сервера и проверен по дневным суммам.</p>}
          <details className="format-guide"><summary>Как подготовить дневной CSV</summary><p>Три столбца: date, income, expense. Даты в формате ГГГГ-ММ-ДД; суммы неотрицательные. Одна строка на каждый день без пропусков. В дни без операций укажите нули. Разделитель — запятая или точка с запятой. Для десятичной запятой используйте точку с запятой между столбцами.</p><pre>date,income,expense{'\n'}2026-10-21,42000,31000{'\n'}2026-10-22,38000,28000{'\n'}2026-10-23,45000,35000</pre><p>Это дневной формат готового API. Полная банковская выписка с контрагентами и назначениями платежей относится к следующему этапу.</p></details>
        </section>

        <section id="advice" className="panel advice-panel" aria-labelledby="advice-heading"><div className="panel-heading"><div><h2 id="advice-heading">Следующий шаг</h2><p>Разберитесь с прогнозом и подготовьте план</p></div><Sparkles className="muted-icon" size={22} /></div><div className="advice-intro"><span className="advice-icon"><Sparkles size={23} /></span><h3>{analysis ? 'Рекомендации по прогнозу' : 'От цифр — к решениям'}</h3><p>Советник сервера объяснит финансовую динамику и предложит действия по текущему прогнозу.</p></div>
          <label htmlFor="business-type">Сфера бизнеса</label><Select id="business-type" value={businessType} onChange={e => { advisorRequest.current?.abort(); setAnalysis(null); setAdvicePending(false); setAdviceError(''); setBusinessType(e.target.value); }}><option>Розничная торговля</option><option>Кафе и рестораны</option><option>Услуги</option><option>Производство</option></Select>
          <button className="button button-secondary advice-button" disabled={!result || advicePending} onClick={() => void getAdvice()}>{advicePending ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}{advicePending ? 'Готовим рекомендации…' : 'Получить рекомендации'}</button>
          {!result && <p className="field-hint">Сначала постройте прогноз. Тогда рекомендации будут основаны на его результатах.</p>}
          {adviceError && <p className="error-message" role="alert"><TriangleAlert size={18} />{adviceError}</p>}
          {analysis && <div className="advice-result" role="status"><p>{analysis.analysis}</p><ul>{analysis.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
          <div className="model-note"><CircleHelp size={17} /><p>Текущий расчет использует тренд прошлых операций. Вероятности, плановые счета и оценка качества появятся после подключения расширенной модели.</p></div>
        </section>
      </div>
      {!!history.length && <section className="panel history-panel" aria-labelledby="history-heading"><div className="panel-heading"><div><h2 id="history-heading">Последние дни истории</h2><p>Дневные суммы из {source === 'example' ? 'учебного примера' : 'загруженного файла'}</p></div><span className="neutral-tag">{history.length} дней</span></div><div className="table-scroll"><table><caption className="sr-only">Последние семь дней, остаток восстановлен от указанной суммы на конец истории</caption><thead><tr><th scope="col">Дата</th><th scope="col">Поступления</th><th scope="col">Расходы</th><th scope="col">Расчетный остаток</th></tr></thead><tbody>{actual.slice(-7).reverse().map(p => <tr key={p.date}><th scope="row">{fullDate(p.date)}</th><td className="positive">+{rub(p.income)}</td><td>{rub(p.expense)}</td><td>{Number.isFinite(p.balance) ? rub(p.balance) : 'Не указан'}</td></tr>)}</tbody></table></div></section>}
      <footer><span>УЧЁТ</span><span>Прогноз — ориентир для планирования</span></footer>
    </main>
    <dialog ref={help} onCancel={() => setGuide(false)} onClose={() => setGuide(false)} aria-labelledby="help-heading"><button className="dialog-close" onClick={() => setGuide(false)} aria-label="Закрыть справку"><X size={21} /></button><span className="empty-icon"><CircleHelp size={27} /></span><h2 id="help-heading">Как читать прогноз</h2><p>Зеленая линия показывает историю остатка, восстановленную по дневным суммам. Синяя пунктирная линия — прогноз сервера.</p><p>Когда линия опускается ниже нуля, текущих денег может не хватить. В предупреждении указаны первая дата и максимальная сумма нехватки.</p><p>Это детерминированный прогноз по прошлым операциям. Он не дает вероятности события и пока не учитывает выставленные счета или будущие налоги. Обновляйте историю после новых операций.</p><button className="button button-primary" onClick={() => setGuide(false)}>Понятно</button></dialog>
  </div>;
}
