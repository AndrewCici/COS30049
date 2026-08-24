import { Paper, Tooltip, Typography } from '@mui/material';
import { Fragment } from 'react';
import { BAND_STYLES, sentenceAriaLabel } from '../bands';
import type { SentenceScore } from '../types';

interface Props {
  originalText: string;
  sentences: SentenceScore[];
}

/** Renders the original passage with each scored sentence highlighted in
 *  place (offsets come from the backend, so inter-sentence whitespace is
 *  preserved exactly). Every highlight carries a tooltip and aria-label
 *  with the band name and numeric score — the text/tooltip equivalent
 *  required by WCAG 1.4.1 — and is keyboard-focusable. */
export default function HighlightedText({ originalText, sentences }: Props) {
  const parts: React.ReactNode[] = [];
  let cursor = 0;

  sentences.forEach((s, i) => {
    if (s.start > cursor) {
      parts.push(<Fragment key={`gap-${i}`}>{originalText.slice(cursor, s.start)}</Fragment>);
    }
    const style = BAND_STYLES[s.band];
    const pct = (s.score * 100).toFixed(0);
    parts.push(
      <Tooltip
        key={`s-${i}`}
        title={`${style.label} — AI probability ${pct}% (${s.score.toFixed(2)})`}
        arrow
      >
        <span
          tabIndex={0}
          role="mark"
          aria-label={sentenceAriaLabel(s.band, s.score)}
          style={{
            backgroundColor: style.background,
            textDecoration: style.textDecoration,
            textDecorationColor: style.border,
            textUnderlineOffset: '3px',
            color: '#1a1a1a',
            borderRadius: 3,
            padding: '1px 2px',
            cursor: 'help',
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
