import { API_ROUTES } from '../../../blackboard/contracts/types';
import type { ApiOperations } from '../../../blackboard/contracts/types';

export class ApiFailure extends Error {
  constructor(public status: number, message: string, public fields: { field: string; message: string }[] = []) { super(message); }
}
const env = import.meta.env ?? {};
const origin = (env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '');
const base = env.VITE_API_USE_PROXY === 'true' ? '' : origin;
export function messageOf(error: unknown): string {
  if(error instanceof ApiFailure&&error.fields.length) return error.message+' '+error.fields.map(detail=>`${detail.field}: ${detail.message}`).join('; ');
  return error instanceof Error ? error.message : 'Не удалось выполнить запрос.';
}
export async function api<K extends keyof ApiOperations>(operation: K, options: {
  params?: Record<string, string>; data?: ApiOperations[K]['request']; form?: FormData; signal?: AbortSignal; timeout?: number;
} = {}): Promise<ApiOperations[K]['response']> {
  const [verb, template] = API_ROUTES[operation];
  const path = template.replace(/\{([^}]+)\}/g, (_, key: string) => {
    const value = options.params?.[key]; if (!value) throw new Error(`Не указан параметр ${key}.`); return encodeURIComponent(value);
  });
  let url = base + path;
  if (verb === 'get' && options.data) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(options.data)) if (value !== undefined && value !== '') query.set(key, String(value));
    if (query.size) url += '?' + query;
  }
  try {
    const response = await fetch(url, {
      method: verb.toUpperCase(), credentials: 'include',
      headers: options.form ? undefined : { 'Content-Type': 'application/json' },
      body: verb === 'get' ? undefined : options.form ?? (options.data === undefined ? undefined : JSON.stringify(options.data)),
      signal: AbortSignal.any([...(options.signal ? [options.signal] : []), AbortSignal.timeout(options.timeout ?? 60000)]),
    });
    if (!response.ok) {
      let body: { code?: string; message?: string; details?: { field: string; message: string }[] } = {};
      try { body = await response.json(); } catch { /* Non-JSON gateway errors use the safe HTTP message. */ }
      const messages: Record<number, string> = { 401: operation === 'login' ? 'Неверная почта или пароль.' : 'Сессия завершена. Войдите заново.', 403: 'Нет доступа к этой компании.', 404: 'Данные или метод сервера не найдены.', 409: 'Данные изменились. Обновите компанию и повторите расчет.', 413: 'Файл слишком большой.', 422: 'Проверьте параметры запроса.', 429: 'Слишком много запросов. Повторите позже.' };
      if (response.status === 401 && operation !== 'login' && operation !== 'session') window.dispatchEvent(new Event('session-expired'));
      const translated = body.code === 'insufficient_data' ? 'Недостаточно исторических данных для расчета. Загрузите более длинную выписку.' : [401,403,404,409,413,429].includes(response.status) ? messages[response.status] : undefined;
      throw new ApiFailure(response.status, response.status >= 500 ? 'Ошибка сервера. Повторите запрос позже.' : translated || body.message || messages[response.status] || `Ошибка ${response.status}.`, Array.isArray(body.details) ? body.details : []);
    }
    const result = (await response.json()) as unknown;
    if (result === null || typeof result !== 'object') {
      throw new Error('Сервер вернул некорректный формат ответа.');
    }
    if (operation === 'categories') {
      if (!Array.isArray((result as { items?: unknown }).items)) {
        throw new Error('Некорректный формат списка категорий: ожидался массив items.');
      }
    }
    return result as ApiOperations[K]['response'];
  } catch (error) {
    if (options.signal?.aborted) throw new DOMException('Запрос отменен', 'AbortError');
    if (error instanceof ApiFailure) throw error;
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('Сервер не ответил вовремя. Повторите запрос.');
    if (error instanceof TypeError) throw new Error('Нет связи с сервером. Проверьте подключение.');
    if (error instanceof SyntaxError) throw new Error('Сервер вернул ответ в неподдерживаемом формате.');
    throw error;
  }
}
