import { Paper, Tooltip, Typography } from '@mui/material';
import { Fragment, useEffect, useRef } from 'react';
import { BAND_STYLES, sentenceAriaLabel } from '../bands';
import type { SentenceScore } from '../types';

interface Props {
  originalText: string;
  sentences: SentenceScore[];
  /** Index highlighted because the matching chart bar is hovered, or this
   * sentence itself is hovered/focused (bidirectional with the chart). */
  activeIndex: number | null;
  onHoverIndex: (index: number | null) => void;
  /** Bumped (together with the index) whenever the chart is clicked, so the
   * same sentence can be re-focused even if it was already the active one. */
  focusRequest: { index: number; nonce: number } | null;
}

/** Renders the original passage with each scored sentence highlighted in
 *  place (offsets come from the backend, so inter-sentence whitespace is
 *  preserved exactly). Every highlight carries a tooltip and aria-label
 *  with the band name and numeric score — the text/tooltip equivalent
 *  required by WCAG 1.4.1 — and is keyboard-focusable. Hovering or
 *  focusing a sentence here highlights the matching bar in SentenceChart,
 *  and clicking a bar there scrolls to and focuses the sentence here. */
export default function HighlightedText({
  originalText, sentences, activeIndex, onHoverIndex, focusRequest,
}: Props) {
  const refs = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    if (!focusRequest) return;
    const el = refs.current[focusRequest.index];
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest?.nonce]);

  const parts: React.ReactNode[] = [];
  let cursor = 0;

  sentences.forEach((s, i) => {
    if (s.start > cursor) {
      parts.push(<Fragment key={`gap-${i}`}>{originalText.slice(cursor, s.start)}</Fragment>);
    }
    const style = BAND_STYLES[s.band];
    const pct = (s.score * 100).toFixed(0);
    const isActive = activeIndex === i;
    parts.push(
      <Tooltip
        key={`s-${i}`}
        title={`${style.label} — AI probability ${pct}% (${s.score.toFixed(2)})`}
        arrow
      >
        <span
          ref={(el) => {
            refs.current[i] = el;
          }}
          tabIndex={0}
          role="mark"
          aria-label={sentenceAriaLabel(s.band, s.score)}
          onMouseEnter={() => onHoverIndex(i)}
          onMouseLeave={() => onHoverIndex(null)}
          onFocus={() => onHoverIndex(i)}
          onBlur={() => onHoverIndex(null)}
          style={{
            backgroundColor: style.background,
            textDecoration: style.textDecoration,
            textDecorationColor: style.border,
            textUnderlineOffset: '3px',
            color: '#1a1a1a',
            borderRadius: 3,
            padding: '1px 2px',
            cursor: 'help',
            boxShadow: isActive ? '0 0 0 2px #1a1a1a' : 'none',
          }}
        >
          {originalText.slice(s.start, s.end)}
        </span>
      </Tooltip>,
    );
    cursor = s.end;
  });
  if (cursor < originalText.length) {
    parts.push(<Fragment key="tail">{originalText.slice(cursor)}</Fragment>);
  }

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="subtitle2" component="h3" gutterBottom>
        Sentence-level analysis
      </Typography>
      <Typography
        component="div"
        sx={{ lineHeight: 2.1, whiteSpace: 'pre-wrap', fontSize: '1.05rem' }}
      >
        {parts}
      </Typography>
    </Paper>
  );
}
