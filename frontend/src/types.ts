// Mirrors the backend contract in backend/app/schemas.py.

export type Band = 'low' | 'medium' | 'high';
export type DocumentBand = Band | 'mixed';
export type Verdict = 'ai-generated' | 'human-made';

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
  verdict: Verdict;
  confidence: number;
  word_count: number;
  sentence_count: number;
}

export interface NormalisationInfo {
  applied: boolean;
  format_chars_removed: number;
  combining_marks_removed: number;
  confusables_mapped: number;
}

export interface Meta {
  method: string;
  model_name: string;
  version: string;
  fallback_used: boolean;
  bands: { low_below: number; high_at_or_above: number };
  warnings: string[];
  normalisation: NormalisationInfo;
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

export interface InputLimits {
  min_text_chars: number;
  max_text_chars: number;
  max_sentences: number;
}

export interface ModelMetrics {
  accuracy: number;
  precision_ai?: number;
  recall_ai?: number;
  f1_ai: number;
  roc_auc: number;
  brier_score?: number;
  false_positive_rate: number;
  confusion_matrix?: number[][];
  n_test: number;
}

export interface ModelInfoResponse {
  model_name: string;
  version: string;
  dataset: string;
  metrics: ModelMetrics;
  essay_level_metrics: Partial<ModelMetrics>;
  bands: { low_below: number; high_at_or_above: number };
  input_limits: InputLimits;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  request_id: string;
}

export interface ApiErrorBody {
  error: ApiErrorDetail;
}

/** One entry in the session's check history, not part of the backend
 * contract. Stores the full result (not just the document score) so a
 * history point can be "reopened" with its sentence-level breakdown
 * intact, not just its summary number. */
export interface SessionCheck {
  id: string;
  at: string; // ISO timestamp
  text: string;
  wordCount: number;
  result: ScoreResponse;
}
