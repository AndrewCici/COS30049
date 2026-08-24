// Fixed legend: one source of truth for band presentation.
//
// WCAG 1.4.1 — colour is never the only cue. Each band pairs its colour
// with (a) a distinct underline treatment, (b) a text label used in
// tooltips/aria-labels, and (c) the numeric score always available on
// hover/focus. Colours also differ in luminance for colour-vision
// deficiency, and all pass ≥4.5:1 contrast with the #1a1a1a text on them.

import type { Band, DocumentBand } from './types';

export interface BandStyle {
  label: string;
  shortLabel: string;
  range: string;
  background: string;
  border: string;
  // Redundant non-colour channel: underline style differs per band.
  textDecoration: string;
  symbol: string; // used in the legend and summary as another text cue
}

export const BAND_STYLES: Record<Band, BandStyle> = {
  low: {
    label: 'Likely human-written',
    shortLabel: 'Human-like',
    range: 'score < 0.35',
    background: '#d8efd8',
    border: '#4c8c4a',
    textDecoration: 'none',
    symbol: '○',
  },
  medium: {
    label: 'Unclear / mixed signals',
    shortLabel: 'Unclear',
    range: '0.35 – 0.64',
    background: '#ffe9b3',
    border: '#b28704',
    textDecoration: 'underline dotted 2px',
    symbol: '◐',
  },
  high: {
    label: 'Likely AI-generated',
    shortLabel: 'AI-like',
    range: 'score ≥ 0.65',
    background: '#f6c8c4',
    border: '#c0392b',
    textDecoration: 'underline solid 2px',
    symbol: '●',
  },
};

export const DOC_BAND_LABEL: Record<DocumentBand, string> = {
  low: 'Likely human-written',
  medium: 'Unclear — treat with caution',
  high: 'Likely AI-generated',
  mixed: 'Mixed — parts look AI-generated, parts human-written',
};

export function sentenceAriaLabel(band: Band, score: number): string {
  return `${BAND_STYLES[band].label}, AI probability ${(score * 100).toFixed(0)}%`;
}
