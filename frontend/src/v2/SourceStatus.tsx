import { CheckCheck, LoaderCircle, TriangleAlert } from 'lucide-react';

export function SourceStatus({pending,error,partial,receivedAt,forecastPending,forecastError}:{pending:boolean;error:string;partial:string;receivedAt:number;forecastPending:boolean;forecastError:string}) {
  const problem=error||partial||forecastError;
  const busy=pending||forecastPending;
  const Icon=busy?LoaderCircle:problem?TriangleAlert:CheckCheck;
  const text=pending?'Получаем данные…':error?'Не удалось обновить данные':partial?'Календарь не получен':forecastPending?'Данные получены · рассчитываем прогноз…':forecastError?'Данные получены · прогноз не обновлён':'Данные получены';
  return <div className={`server-status ${busy?'is-loading':problem?'is-warning':'is-success'}`} role="status" aria-live="polite" title={problem||'Время последнего успешного получения данных в этом браузере; не проверка постоянного соединения.'}><Icon size={17} aria-hidden="true"/><div><strong>{text}</strong><span>С сервера · последнее получение <time dateTime={new Date(receivedAt).toISOString()}>{new Date(receivedAt).toLocaleTimeString('ru-RU')}</time></span></div></div>;
}
