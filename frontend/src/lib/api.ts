import { API_ROUTES } from '../../../blackboard/contracts/types';
import type { AdvisorRequest, AdvisorResponse, ForecastRequest, ForecastResult } from '../../../blackboard/contracts/types';
import { checkForecast } from './cashflow';

const base = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '');
if (base && !/^https?:\/\//.test(base)) throw new Error('VITE_API_BASE_URL must be an http(s) origin.');
export async function requestJson(route: string, body: unknown, signal: AbortSignal, timeoutMs = 15000): Promise<unknown> {
  try {
    const response = await fetch(base + route, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]),
    });
    if (!response.ok) {
      const messages: Record<number, string> = {
        401: 'Сессия завершена. Войдите в сервис заново.', 403: 'Нет доступа к данным компании.',
        404: 'Метод сервера недоступен. Проверьте адрес подключения.', 409: 'Данные изменились. Обновите прогноз.',
        422: 'Сервер отклонил данные. Проверьте историю и остаток.', 429: 'Слишком много запросов. Повторите чуть позже.',
        503: 'Сервис временно недоступен. Повторите запрос.',
      };
      throw new Error(messages[response.status] ?? `Не удалось получить ответ сервера (${response.status}).`);
    }
    return await response.json();
  } catch (error) {
    if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('Сервер не ответил за отведенное время. Повторите запрос.');
    if (error instanceof TypeError) throw new Error('Нет связи с сервером. Проверьте подключение и адрес API в настройках проекта.');
    if (error instanceof SyntaxError) throw new Error('Ответ сервера не удалось прочитать. Проверьте адрес API.');
    throw error;
  }
}
export async function forecast(request: ForecastRequest, signal: AbortSignal): Promise<ForecastResult> {
  return checkForecast(await requestJson(API_ROUTES.forecastV1[1], request, signal), request.history, request.initial_balance, request.horizon_days);
}
export async function advice(request: AdvisorRequest, signal: AbortSignal): Promise<AdvisorResponse> {
  const response = await requestJson(API_ROUTES.advisorV1[1], request, signal, 12000);
  if (!response || typeof response !== 'object') throw new Error('Не удалось прочитать рекомендации.');
  const value = response as Record<string, unknown>;
  if (typeof value.analysis !== 'string' || !Array.isArray(value.recommendations)
    || !value.recommendations.every(v => typeof v === 'string') || typeof value.urgent_action_required !== 'boolean') throw new Error('Ответ советника не соответствует формату.');
  return response as AdvisorResponse;
}
