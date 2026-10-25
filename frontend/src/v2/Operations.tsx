import { canEditQueryResult, decodeStatementBytes } from '../lib/requestSafety';
import { DatePicker } from './DatePicker';
import { CategoryBreakdown } from './CategoryBreakdown';
import { TableViewport } from './TableViewport';
import { Select } from './Select';
import { useMemo, useRef, useState } from 'react';
import { ChevronRight, FileSpreadsheet, Search, Upload } from 'lucide-react';
import type { Category, CategoryId, CategoryTotal, ColumnMapping, ImportResponse, TransactionQuery } from '../../../contracts/types';
import { dateLabel, rub } from '../lib/cashflow';
import { api, messageOf } from './client';
import { Empty, ErrorBox, Loading, useResource } from './shared';
import { inferMapping, mappingLabels, parseStatementText, previewFromRows, validateStatement } from './statement';

import type { StatementPreview } from './statement';

export default function Operations({ companyId, categories, totals, revision, onChange }: { companyId: string; categories: Category[]; totals: CategoryTotal[]; revision: number; onChange: () => Promise<void> }) {
  const [file,setFile]=useState<File|null>(null), [preview,setPreview]=useState<StatementPreview|null>(null), [mapping,setMapping]=useState<ColumnMapping|null>(null);
  const [fileError,setFileError]=useState(''), [reading,setReading]=useState(false), [drag,setDrag]=useState(false), [uploading,setUploading]=useState(false), [report,setReport]=useState<ImportResponse|null>(null), [policy,setPolicy]=useState<'reject_conflicts'|'use_last_row'>('reject_conflicts');
  const fileInput=useRef<HTMLInputElement>(null), readId=useRef(0);
  const [filters,setFilters]=useState<TransactionQuery>({ limit: 50 }), [cursors,setCursors]=useState<string[]>(['']), [page,setPage]=useState(0), [search,setSearch]=useState(''), [busy,setBusy]=useState(''), [rowError,setRowError]=useState('');
  const params={ company_id: companyId };
  const [listRevision,setListRevision]=useState(0);
  const queryKey=JSON.stringify([companyId,filters,cursors[page]??'',revision,listRevision]);
  const listResource=useResource(async signal=>({key:queryKey,value:await api('listTransactions',{params,data:{...filters,cursor:cursors[page] || undefined},signal})}),[queryKey]);
  const list={...listResource,data:listResource.data?.value??null,reload:()=>setListRevision(value=>value+1)};
  const rowsEditable=canEditQueryResult(queryKey,listResource.data?.key,listResource.loading,listResource.isStale);
  const currentQuery=useRef(queryKey);currentQuery.current=queryKey;
  const validation=useMemo(()=>preview&&mapping?validateStatement(preview,mapping):[],[preview,mapping]);
  async function choose(next: File) {
    const token=++readId.current; setReading(true); setFileError(''); setPreview(null); setMapping(null); setReport(null); setFile(null);
    try {
      if(next.size>10*1024*1024) throw new Error('Файл больше 10 МБ. Разделите выписку.');
      if(!/\.(csv|xlsx|txt|1c)$/i.test(next.name)) throw new Error('Выберите CSV, XLSX или выписку 1C (TXT/1C).');
      let parsed: StatementPreview;
      if(/\.xlsx$/i.test(next.name)) {
        const { readSheet }=await import('read-excel-file/browser');
        const rows=await readSheet(next); parsed=previewFromRows(rows.map(row=>row.map(cell=>cell instanceof Date?cell.toISOString().slice(0,10):String(cell??''))));
      } else {
        const buffer = await next.arrayBuffer();
        const text = decodeStatementBytes(buffer);
        parsed = parseStatementText(text);
      }

      if(token!==readId.current) return;
      setFile(next); setPreview(parsed); setMapping(inferMapping(parsed.headers));
    } catch(e) { if(token===readId.current) setFileError(messageOf(e)); }
    finally { if(token===readId.current) setReading(false); }
  }
  async function send() {
    if(!file||!mapping||validation.length||uploading) return;
    setUploading(true); setFileError(''); setReport(null);
    const form=new FormData(); form.set('file',file); form.set('format',/\.xlsx$/i.test(file.name)?'xlsx':'csv');
    form.set('column_mapping',JSON.stringify(Object.fromEntries(Object.entries(mapping).filter(([,v])=>v)))); form.set('balance_policy',policy);
    try { const result=await api('importStatement',{params,form,timeout:90000}); setReport(result); if(result.status==='ready') { await onChange(); list.reload(); } }
    catch(e) { setFileError(messageOf(e)); } finally { setUploading(false); }
  }
  function filter<K extends keyof TransactionQuery>(key: K,value: TransactionQuery[K]) { setFilters(f=>({...f,[key]:value})); setPage(0); setCursors(['']); }
  return <div className="screen-stack"><section className="panel screen-panel"><div className="section-title"><div><h2>Загрузить банковскую выписку</h2><p>CSV, XLSX, TXT/1C — до 10 МБ. Проверьте файл перед загрузкой.</p></div><FileSpreadsheet size={24}/></div>
    <div className={`bank-dropzone ${drag?'dragging':''}`} onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);if(!uploading&&e.dataTransfer.files[0]) void choose(e.dataTransfer.files[0]);}}>
      <Upload size={28}/><h3>{file?.name??'Перетащите выписку сюда'}</h3><p>{preview?`${preview.rows.length} операций, ${preview.headers.length} столбцов`:'Или выберите файл на компьютере'}</p><button className="button button-secondary" disabled={uploading||reading} onClick={()=>fileInput.current?.click()}>Выбрать выписку</button><input ref={fileInput} className="sr-only" aria-label="Файл банковской выписки" type="file" accept=".csv,.xlsx,.txt,.1c" onChange={e=>{if(e.target.files?.[0]) void choose(e.target.files[0]);e.target.value='';}}/>
    </div>{reading&&<Loading text="Читаем файл и проверяем строки…"/>}<ErrorBox message={fileError}/>

    {mapping&&preview&&<><div className="mapping-grid">{(Object.keys(mappingLabels) as (keyof ColumnMapping)[]).map(key=><label key={key}>{mappingLabels[key]}<Select value={mapping[key]??''} onChange={e=>setMapping({...mapping,[key]:e.target.value})}><option value="">{key==='external_id'?'Не использовать':'Выберите столбец'}</option>{preview.headers.map(h=><option key={h}>{h}</option>)}</Select></label>)}</div>
      {validation.length>0&&<div className="error-message" role="alert"><ul>{validation.map((error,i)=><li key={i}>{error}</li>)}</ul></div>}
      <div className="table-scroll"><table><caption>Предпросмотр: первые {Math.min(5,preview.rows.length)} операций</caption><thead><tr>{preview.headers.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{preview.rows.slice(0,5).map((row,i)=><tr key={i}>{row.map((value,j)=><td key={j}>{value}</td>)}</tr>)}</tbody></table></div>
      <label className="policy-label">Если остатки за один день различаются<Select value={policy} onChange={e=>setPolicy(e.target.value as typeof policy)}><option value="reject_conflicts">Отклонить файл и показать ошибки</option><option value="use_last_row">Использовать последнюю строку и предупредить</option></Select></label>
      <button className="button button-primary" onClick={()=>void send()} disabled={uploading||validation.length>0}>{uploading?'Загружаем и проверяем…':`Импортировать ${preview.rows.length} операций`}</button></>}
    {report&&<div className={`import-report ${report.status==='rejected'?'rejected':''}`} role="status"><h3>{report.status==='ready'?'Выписка обработана':'Файл отклонен целиком'}</h3><p>Принято: {report.accepted_rows}. Повторы: {report.duplicate_rows}. Ошибки: {report.rejected_rows}.</p>{report.period_start&&report.period_end&&<p>{dateLabel(report.period_start)} — {dateLabel(report.period_end)}</p>}{report.issues.map((issue,i)=><p key={i}>{issue.row!==null?`Строка ${issue.row}: `:''}{issue.field?`${issue.field}: `:''}{issue.message}</p>)}</div>}
</section><section className="panel screen-panel operations-panel"><div className="section-title"><div><h2>Операции и категории</h2><p>Исправления категории сохраняются на сервере.</p></div></div>
    <form className="filter-bar operations-filters" onSubmit={e=>{e.preventDefault();filter('search',search);}}><label>Поиск<input value={search} onChange={e=>setSearch(e.target.value)} type="search" placeholder="Контрагент или назначение"/></label><button className="button button-secondary" aria-label="Найти операции"><Search size={17}/><span>Найти</span></button><label>С даты<DatePicker value={filters.from_date??''} onChange={value=>filter('from_date',value||undefined)}/></label><label>По дату<DatePicker value={filters.to_date??''} onChange={value=>filter('to_date',value||undefined)}/></label><label>Направление<Select value={filters.direction??''} onChange={e=>filter('direction',e.target.value as TransactionQuery['direction']||undefined)}><option value="">Все</option><option value="income">Поступления</option><option value="expense">Расходы</option></Select></label><label>Категория<Select value={filters.category_id??''} onChange={e=>filter('category_id',e.target.value as CategoryId||undefined)}><option value="">Все категории</option>{categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Select></label></form>
    <ErrorBox message={list.error} retry={list.reload}/><ErrorBox message={rowError}/>
    {list.data&&<><div className="operations-ledger"><TableViewport visibleRows={5} label="Операции: пять строк, остальные доступны при прокрутке"><table><colgroup><col className="ledger-date"/><col/><col className="ledger-category"/><col className="ledger-amount"/></colgroup><caption><span className="ledger-caption-title">Операции <b>{list.data.total.toLocaleString('ru-RU')}</b></span><span className="ledger-caption-hint">5 строк на экране · прокрутка внутри таблицы</span></caption><thead><tr><th>Дата</th><th>Контрагент / назначение</th><th>Категория</th><th>Сумма</th></tr></thead><tbody>{list.data.items.map(t=><tr key={t.id}><th scope="row">{dateLabel(t.date)}</th><td className="operation-description"><strong>{t.counterparty_name}</strong><small className="operation-source"><FileSpreadsheet size={12} aria-hidden="true"/><span>{t.source.label}</span></small><details><summary><ChevronRight size={13} aria-hidden="true"/><span>{t.purpose}</span></summary><p>{t.purpose}</p><p>ИНН: {t.counterparty_inn}</p></details></td><td><Select aria-label={`Категория операции ${t.id}`} value={t.category_id} disabled={!!busy||!rowsEditable} aria-disabled={!!busy||!rowsEditable} onChange={async e=>{if(!rowsEditable||currentQuery.current!==listResource.data?.key)return;setBusy(t.id);setRowError('');try{await api('updateCategory',{params:{...params,transaction_id:t.id},data:{category_id:e.target.value as CategoryId}});await onChange();list.reload();}catch(e){setRowError(messageOf(e));}finally{setBusy('');}}}>{categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Select><small className={`category-origin ${t.category_id==='uncategorized'?'needs-review':t.category_method==='manual'?'is-manual':'is-automatic'}`}>{t.category_method==='manual'?'Назначено вручную':t.category_id==='uncategorized'?'Нужна проверка':'Определено сервером'}</small></td><td className={`operation-amount ${t.direction==='income'?'positive':''}`}>{t.direction==='income'?'+':'−'}{rub(t.amount)}</td></tr>)}</tbody></table></TableViewport></div>{!list.data.items.length&&<Empty>Нет операций по выбранным фильтрам.</Empty>}<div className="pagination operations-pagination"><button className="button button-secondary" disabled={page===0||!rowsEditable} onClick={()=>setPage(p=>p-1)}>Назад</button><span className="pagination-state" role="status" aria-live="polite">{!rowsEditable?<Loading text="Загружаем…"/>:<>Страница {page+1}</>}</span><button className="button button-secondary" disabled={!list.data.next_cursor||!rowsEditable} onClick={()=>{setCursors(c=>[...c.slice(0,page+1),list.data!.next_cursor!]);setPage(p=>p+1);}}>Далее</button></div></>}
  </section><CategoryBreakdown categories={categories} totals={totals}/></div>;

}
