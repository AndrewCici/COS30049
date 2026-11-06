import { useCallback, useState } from 'react';
import type { ScoreResponse, SessionCheck } from './types';

const STORAGE_KEY = 'aidetect.session-history.v1';
const MAX_ENTRIES = 50;

/** Best-effort persistence only: sessionStorage can throw (private
 * browsing, quota, disabled storage) and must never break the app, so
 * every access is wrapped and failures are silently ignored — the in-memory
 * React state is the source of truth either way. */
function loadPersisted(): SessionCheck[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as SessionCheck[]) : [];
  } catch {
    return [];
  }
}

function persist(history: SessionCheck[]): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch {
    // Ignored: history still lives in React state for this page view.
  }
}

export function useSessionHistory() {
  const [history, setHistory] = useState<SessionCheck[]>(loadPersisted);

  const addCheck = useCallback((text: string, result: ScoreResponse) => {
    setHistory((prev) => {
      const entry: SessionCheck = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        at: new Date().toISOString(),
        text,
        wordCount: text.trim() ? text.trim().split(/\s+/).length : 0,
        result,
      };
      const next = [...prev, entry].slice(-MAX_ENTRIES);
      persist(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setHistory([]);
    persist([]);
  }, []);

  return { history, addCheck, clear };
}
