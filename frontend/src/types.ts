// Mirrors the backend contract in backend/app/schemas.py.

export type Band = 'low' | 'medium' | 'high';
export type DocumentBand = Band | 'mixed';

export interface SentenceScore {
  text: string;
  start: number;
  end: number;
  score: number;
  band: Band;
  word_count: number;
}

export interface DocumentScore {
  score: number;
  ci_low: number;
  ci_high: number;
  confidence_level: number;
  band: DocumentBand;
  word_count: number;
  sentence_count: number;
}

export interface Meta {
  method: string;
  model_name: string;
  version: string;
  fallback_used: boolean;
  bands: { low_below: number; high_at_or_above: number };
  warnings: string[];
}

export interface ScoreResponse {
  sentences: SentenceScore[];
  document: DocumentScore;
  meta: Meta;
}

export interface HealthResponse {
  status: 'ok';
  active_method: string;
  available_methods: string[];
}
