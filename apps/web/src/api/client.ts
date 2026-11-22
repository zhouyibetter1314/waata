import { ApiError } from './errors';
import type { ApiErrorEnvelope } from './types';

export const API_BASE = '/api/v1';

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== 'object' || !('error' in value)) return false;
  const error = (value as { error?: unknown }).error;
  return Boolean(
    error &&
    typeof error === 'object' &&
    typeof (error as Record<string, unknown>).code === 'string' &&
    typeof (error as Record<string, unknown>).message === 'string' &&
    typeof (error as Record<string, unknown>).request_id === 'string',
  );
}

async function parseError(response: Response): Promise<ApiError> {
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    return new ApiError({
      status: response.status,
      code: 'INVALID_ERROR_RESPONSE',
      message: `请求失败（HTTP ${response.status}）`,
    });
  }
  if (isErrorEnvelope(value)) {
    return new ApiError({
      status: response.status,
      code: value.error.code,
      message: value.error.message,
      requestId: value.error.request_id,
    });
  }
  return new ApiError({
    status: response.status,
    code: 'INVALID_ERROR_RESPONSE',
    message: `请求失败（HTTP ${response.status}）`,
  });
}

export async function requestRaw(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  let response: Response;
  try {
    const url = new URL(`${API_BASE}${path}`, window.location.origin);
    response = await fetch(url, {
      ...init,
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        ...init.headers,
      },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError')
      throw cause;
    throw new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: '无法连接到 WAATA API，请检查服务状态',
    });
  }
  if (!response.ok) throw await parseError(response);
  return response;
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await requestRaw(path, init);
  return (await response.json()) as T;
}

export function jsonRequest(
  method: 'POST' | 'PUT' | 'PATCH',
  value: unknown,
): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  };
}

export function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}
