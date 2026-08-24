import axios from 'axios';
import type { HealthResponse, ScoreResponse } from './types';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1',
  timeout: 120_000, // first transformer inference on CPU can be slow
});

export async function scoreText(text: string): Promise<ScoreResponse> {
  const { data } = await client.post<ScoreResponse>('/score', { text });
  return data;
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/health');
  return data;
}

/** Turn any axios/API failure into one human-readable, actionable message. */
export function describeApiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    if (err.response) {
      const detail = (err.response.data as { detail?: unknown })?.detail;
      if (typeof detail === 'string') return detail;
      if (err.response.status === 422)
        return 'The text could not be analysed. Paste at least one full English sentence.';
      if (err.response.status === 503)
        return 'No detection model is available on the server right now. Try again later.';
      return `The server reported an error (HTTP ${err.response.status}). Try again.`;
    }
    if (err.code === 'ECONNABORTED')
      return 'The analysis timed out. Try a shorter passage, or try again.';
    return 'Could not reach the analysis server. Check that the backend is running, then try again.';
  }
  return 'Something unexpected went wrong. Try again.';
}
