import axios from 'axios';
import type { ApiErrorBody, HealthResponse, ModelInfoResponse, ScoreResponse } from './types';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1',
  timeout: 30_000,
});

export async function scoreText(text: string): Promise<ScoreResponse> {
  const { data } = await client.post<ScoreResponse>('/score', { text });
  return data;
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/health');
  return data;
}

export async function getModelInfo(): Promise<ModelInfoResponse> {
  const { data } = await client.get<ModelInfoResponse>('/model-info');
  return data;
}

export type ApiErrorKind =
  | 'validation'
  | 'payload_too_large'
  | 'service_unavailable'
  | 'network'
  | 'timeout'
  | 'server'
  | 'unknown';

export interface ApiErrorInfo {
  kind: ApiErrorKind;
  message: string;
  code?: string;
  requestId?: string;
  retryAfterSeconds?: number;
}

/** Turn any axios/API failure into a structured, human-readable
 * description. Every branch maps to the backend's `{"error": {code,
 * message, request_id}}` envelope (see backend/app/main.py); only the
 * fallback branches (network down, no response at all) have no such body
 * to read from. */
export function describeApiError(err: unknown): ApiErrorInfo {
  if (axios.isAxiosError(err)) {
    if (err.response) {
      const status = err.response.status;
      const body = err.response.data as ApiErrorBody | undefined;
      const detail = body?.error;
      const retryAfterHeader = err.response.headers?.['retry-after'];
      const retryAfterSeconds = retryAfterHeader ? Number(retryAfterHeader) : undefined;

      if (status === 413) {
        return {
          kind: 'payload_too_large',
          code: detail?.code,
          requestId: detail?.request_id,
          message: 'That passage is too large to send. Shorten it and try again.',
        };
      }
      if (status === 422) {
        return {
          kind: 'validation',
          code: detail?.code,
          requestId: detail?.request_id,
          message: detail?.message ?? 'The text could not be analysed. Check it and try again.',
        };
      }
      if (status === 503) {
        return {
          kind: 'service_unavailable',
          code: detail?.code,
          requestId: detail?.request_id,
          retryAfterSeconds,
          message: retryAfterSeconds
            ? `The server is busy right now. Try again in about ${retryAfterSeconds}s.`
            : 'No detection model is available on the server right now. Try again later.',
        };
      }
      return {
        kind: 'server',
        code: detail?.code,
        requestId: detail?.request_id,
        message: detail?.message ?? `The server reported an error (HTTP ${status}). Try again.`,
      };
    }
    if (err.code === 'ECONNABORTED') {
      return { kind: 'timeout', message: 'The analysis timed out. Try a shorter passage, or try again.' };
    }
    return {
      kind: 'network',
      message: 'Could not reach the analysis server. Check that the backend is running, then try again.',
    };
  }
  return { kind: 'unknown', message: 'Something unexpected went wrong. Try again.' };
}
