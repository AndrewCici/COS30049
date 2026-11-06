import { Box, Chip, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { forwardRef } from 'react';
import { DOC_BAND_LABEL, VERDICT_STYLES } from '../bands';
import type { DocumentScore, Meta } from '../types';

interface Props {
  document: DocumentScore;
  meta: Meta;
}

const pct = (v: number) => `${(v * 100).toFixed(0)}%`;

/** The primary result: shown above everything else, verdict first and
 * largest (Part B.4). Forwards a ref so the page can move keyboard focus
 * here immediately after a successful analysis, and is itself wrapped by
 * the page in an aria-live region so screen-reader users hear the verdict
 * without having to find it visually. */
const VerdictCard = forwardRef<HTMLDivElement, Props>(function VerdictCard(
  { document: doc, meta },
  ref,
) {
  const verdict = VERDICT_STYLES[doc.verdict];

  return (
    <Paper
      ref={ref}
      tabIndex={-1}
      role="region"
      aria-label="Analysis result"
      variant="outlined"
      sx={{
        p: 3,
        borderWidth: 2,
        borderColor: verdict.color,
        // Focus lands here programmatically (not from a keyboard tab), which
        // many browsers' `:focus-visible` heuristic can suppress, so the
        // indicator is tied to plain `:focus` instead -- it must be visible
        // every time, since this is the moment the result becomes available.
        '&:focus': { outline: '3px solid #1a1a1a', outlineOffset: 2 },
      }}
    >
      <Stack spacing={1.5}>
        <Stack direction="row" sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1.5 }}>
          <Box
            sx={{
              width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
              bgcolor: verdict.color,
            }}
            aria-hidden
          />
          <Typography variant="h4" component="h2" sx={{ fontWeight: 700, color: verdict.color }}>
            {verdict.label}
          </Typography>
        </Stack>

        <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" component="div">
              Confidence
            </Typography>
            <Typography variant="h5" component="div" sx={{ fontWeight: 700 }}>
              {pct(doc.confidence)}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" component="div">
              95% confidence interval
              <Tooltip
                arrow
                title="The true document-level AI-probability score plausibly lies anywhere in this range, estimated by bootstrap resampling of the sentence scores. A wide interval means the result should not be trusted as precise."
              >
                {/* An IconButton (not a bare, tabIndex'd <svg>) so the
                    focusable trigger and its accessible name live on one
                    real interactive element, not a decorative icon axe
                    flags as "focusable but aria-hidden". */}
                <IconButton
                  size="small"
                  aria-label="What does the confidence interval mean?"
                  // Exempt from the 44px touch-target minimum: this trigger
                  // sits inline within a line of caption text, which WCAG
                  // 2.5.8's own "inline" exception covers.
                  sx={{ ml: 0.25, p: 0.25, minWidth: 'auto', minHeight: 'auto' }}
                >
                  <InfoOutlinedIcon fontSize="inherit" />
                </IconButton>
              </Tooltip>
            </Typography>
            <Typography variant="h6" component="div">
              {pct(doc.ci_low)} – {pct(doc.ci_high)}
            </Typography>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" component="div">
              Band
            </Typography>
            <Typography variant="body1" sx={{ fontWeight: 600, pt: 0.5 }}>
              {DOC_BAND_LABEL[doc.band]}
            </Typography>
          </Box>
        </Stack>

        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
          <Chip
            size="small"
            label={`Method: ${meta.fallback_used ? 'statistical fallback' : meta.method}`}
            color={meta.fallback_used ? 'warning' : 'default'}
            variant="outlined"
          />
          <Typography variant="caption" color="text.secondary">
            {doc.sentence_count} sentences · {doc.word_count} words · AI probability {pct(doc.score)}
          </Typography>
        </Stack>

        {/* Score bar: point estimate marker + CI band, a redundant visual
            aid — the numbers above are the primary channel (WCAG 1.4.1). */}
        <Box aria-hidden>
          <Box sx={{ position: 'relative', height: 14, borderRadius: 7, bgcolor: '#e8e8e8', overflow: 'hidden' }}>
            <Box
              sx={{
                position: 'absolute', top: 0, bottom: 0,
                left: `${doc.ci_low * 100}%`,
                width: `${Math.max((doc.ci_high - doc.ci_low) * 100, 1)}%`,
                bgcolor: 'rgba(96, 96, 96, 0.35)',
              }}
            />
            <Box
              sx={{
                position: 'absolute', top: -1, bottom: -1,
                left: `calc(${doc.score * 100}% - 2px)`,
                width: 4, bgcolor: '#1a1a1a', borderRadius: 1,
              }}
            />
          </Box>
          <Stack direction="row" sx={{ justifyContent: 'space-between', mt: 0.25 }}>
            <Typography variant="caption" color="text.secondary">0% — human</Typography>
            <Typography variant="caption" color="text.secondary">100% — AI</Typography>
          </Stack>
        </Box>
      </Stack>
    </Paper>
  );
});

export default VerdictCard;
